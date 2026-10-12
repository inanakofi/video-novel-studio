"""Render and verify offline H.264/AAC episodes with FFmpeg."""

import argparse
import json
import os
from pathlib import Path
import tempfile
import threading
from datetime import datetime, timezone
from typing import Any

from .scene_builder import Episode, load_episode
from .settings import settings_for, card_durations
from .media import MediaError, RenderCancelled, ffmpeg, verify_export, atomic_json, audio_duration
from .audio_manager import inspect_narration, prepare_voice, mix_audio
from .subtitle_generator import make_cues, parse_srt, validate_cues, cues_to_srt, write_ass
from .visuals import prepare_image, card
from .render_cache import ShotCache, shot_key, digest
from .exports import source_inputs_sha256


def asset_errors(episode: Episode) -> list[str]:
    """Return every missing/invalid visual, rather than only the first one."""
    from PIL import Image
    errors = []
    for scene in episode.scenes:
        for label, asset in (('image', scene.visual_asset), ('foreground', scene.foreground_asset)):
            if not asset:
                continue
            path = episode.resolve_asset(asset)
            if not path.is_file():
                errors.append(f'Scene {scene.scene_id}: missing {label}: {path}')
            else:
                try:
                    if label == 'image' and scene.media_type == 'video':
                        from .video_assets import video_info
                        info = video_info(path)
                        if scene.video_start_seconds + scene.duration_seconds > info['duration'] + .002:
                            raise MediaError(f'video trim ends at {scene.video_start_seconds + scene.duration_seconds:.3f}s, beyond its {info["duration"]:.3f}s duration')
                        if scene.video_audio_volume and not info['has_audio']:
                            raise MediaError('video has no audio track; set original audio volume to 0')
                    else:
                        with Image.open(path) as image:
                            image.verify()
                except Exception as error:
                    errors.append(f'Scene {scene.scene_id}: cannot read {label} {path.name}: {error}')
    try:
        inspect_narration(episode)
    except (MediaError, ValueError) as error:
        errors.append(str(error))
    settings = settings_for(episode)
    extra_audio = [settings['music_asset']] if settings['music_asset'] else []
    extra_audio += [effect.get('asset', '') for effect in settings['sound_effects'] if isinstance(effect, dict)]
    for asset in extra_audio:
        try:
            audio_duration(episode.resolve_asset(asset))
        except (MediaError, ValueError) as error:
            errors.append(str(error))
    return errors


def _publish_files(pairs: list[tuple[Path, Path]], work: Path):
    """Roll back all sidecars and video if any publication step fails."""
    backups = []
    published = []
    parent = work.parent.resolve()
    try:
        for index, (source, target) in enumerate(pairs):
            if target.parent.resolve() != parent or source.parent.resolve() != work.resolve():
                raise MediaError('Publication paths must stay inside this render output directory.')
            if target.exists():
                backup = work / f'backup_{index}{target.suffix}'
                os.replace(target, backup)
                backups.append((backup, target))
            os.replace(source, target)
            published.append(target)
    except BaseException:
        for target in reversed(published):
            target.unlink(missing_ok=True)
        for backup, target in reversed(backups):
            os.replace(backup, target)
        raise


def episode_captions(episode: Episode, spans=None):
    settings = settings_for(episode)
    spans = inspect_narration(episode) if spans is None else spans
    title, end = card_durations(settings)
    duration = title + episode.timeline()[-1].end_seconds + end
    if settings['subtitle_mode'] == 'manual':
        path = episode.directory / 'subtitles.srt'
        if not path.is_file():
            raise MediaError('Manual subtitle mode needs subtitles.srt. Generate captions first.')
        cues = parse_srt(path.read_text(encoding='utf-8-sig'))
    else:
        cues = make_cues(episode, spans)
    windows = [(title + timed.start_seconds,
                title + timed.start_seconds + (span.duration if span.path else timed.scene.duration_seconds))
               for timed, span in zip(episode.timeline(), spans)]
    validate_cues(cues, duration, windows)
    if settings['subtitle_mode'] == 'manual':
        from dataclasses import replace
        cues = [replace(cue, style=next((timed.scene.subtitle_style for timed, (start, stop) in zip(episode.timeline(), windows)
                                        if cue.start >= start - .002 and cue.end <= stop + .002), cue.style)) for cue in cues]
    return cues


def _motion_filter(motion, frames, width, height, fps):
    denominator = max(1, frames - 1)
    fraction = f'on/{denominator}'
    zoom = {'static': '1', 'slow_zoom_in': f'1+0.10*{fraction}',
            'slow_zoom_out': f'1.10-0.10*{fraction}',
            'pan_left': '1.12', 'pan_right': '1.12', 'parallax': f'1.03+0.04*{fraction}'}[motion]
    x = '(iw-iw/zoom)/2'
    if motion == 'pan_right':
        x = f'(iw-iw/zoom)*{fraction}'
    elif motion == 'pan_left':
        x = f'(iw-iw/zoom)*(1-{fraction})'
    return f"zoompan=z='{zoom}':x='{x}':y='(ih-ih/zoom)/2':d=1:s={width}x{height}:fps={fps}"


def _segment(source: Path, output: Path, duration: float, motion: str, settings: dict,
             work: Path, *, previous: Path | None = None, transition='cut', transition_seconds=.5,
             foreground: Path | None = None, media_type='image', video_start_seconds=0, cancel=None, progress=None):
    width, height, fps = settings['width'], settings['height'], settings['fps']
    frames = round(duration * fps)
    if frames < 1:
        raise MediaError('Every scene/card must last at least one video frame.')
    if media_type == 'video':
        args = ['-ss', str(video_start_seconds), '-i', str(source)]
        graph = [f'[0:v]setpts=PTS-STARTPTS,fps={fps},scale=iw*sar:ih,setsar=1,'
                 f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},'
                 f'trim=duration={duration},setpts=PTS-STARTPTS[base]']
    else:
        prepared = output.with_suffix('.png')
        prepare_image(source, prepared, (width * 2, height * 2))
        args = ['-loop', '1', '-framerate', str(fps), '-i', str(prepared)]
        graph = [f'[0:v]{_motion_filter(motion, frames, width, height, fps)},setsar=1[base]']
    current = 'base'
    input_index = 1
    if foreground:
        fg = output.with_name(output.stem + '_fg.png')
        prepare_image(foreground, fg, (width, height), foreground=True)
        args += ['-loop', '1', '-framerate', str(fps), '-i', str(fg)]
        graph.append(f'[{input_index}:v]format=rgba[fg]')
        graph.append(f"[{current}][fg]overlay=x='{width}*0.035*(1-2*t/{duration})':y=0:shortest=1[layered]")
        current = 'layered'
        input_index += 1
    fade = min(transition_seconds, duration / 2)
    if previous and transition == 'crossfade':
        args += ['-loop', '1', '-framerate', str(fps), '-i', str(previous)]
        graph.append(f'[{input_index}:v]scale={width}:{height},setsar=1,format=yuv420p[prev]')
        graph.append(f'[{current}]format=yuva420p,fade=t=in:st=0:d={fade}:alpha=1[incoming]')
        graph.append('[prev][incoming]overlay=shortest=1[transitioned]')
        current = 'transitioned'
    elif transition == 'fade_black':
        graph.append(f'[{current}]fade=t=in:st=0:d={fade}[transitioned]')
        current = 'transitioned'
    # Save the raw final frame before H.264 prediction/quantization. Otherwise a
    # changed incoming crossfade can change compressed final pixels and needlessly
    # invalidate every later scene's transition dependency.
    graph.append(f'[{current}]format=yuv420p,split=2[out][tail]')
    graph.append(f"[tail]select='eq(n,{frames-1})'[last]")
    ffmpeg([*args, '-filter_complex', ';'.join(graph), '-map', '[out]', '-frames:v', str(frames),
            '-an', '-c:v', 'libx264', '-preset', settings['preset'], '-crf', str(settings['crf']),
            '-threads', '2', '-r', str(fps), str(output),
            '-map', '[last]', '-frames:v', '1', '-threads', '2', str(output.with_suffix('.last.png'))],
           cwd=work, cancel=cancel, progress=progress, duration=duration)


def render_episode(scenes_path: str | Path, output: str | Path, *, cancel: threading.Event | None = None,
                   progress=None, overrides: dict | None = None, use_cache: bool = True) -> dict:
    """Publish an MP4 only after stream checks and a successful full decode."""
    from dataclasses import replace
    source_sha256 = digest(Path(scenes_path))
    episode = load_episode(scenes_path)
    if overrides:
        episode = replace(episode, settings={**episode.settings, **overrides})
    settings = settings_for(episode)
    output = Path(output).resolve()
    if output.suffix.lower() != '.mp4':
        raise MediaError('Output filename must end with .mp4')
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.with_suffix('.mp4.lock')
    try:
        lock_handle = lock.open('x', encoding='utf-8')
    except FileExistsError as error:
        raise MediaError(f'This export is locked: {lock}. Another render may be running. If its process has stopped, remove only this lock file and rerun.') from error
    def notify(fraction, message):
        if cancel and cancel.is_set():
            raise RenderCancelled('Render cancelled; previous export preserved.')
        if progress:
            progress(max(0, min(1, fraction)), message)
    try:
        with lock_handle:
            lock_handle.write(json.dumps({'pid': os.getpid(), 'started': datetime.now(timezone.utc).isoformat()}))
        notify(0, 'Validating images and narration')
        errors = asset_errors(episode)
        if errors:
            raise MediaError('\n'.join(errors))
        inputs_sha256 = source_inputs_sha256(Path(scenes_path))
        spans = inspect_narration(episode)
        title_duration, end_duration = card_durations(settings)
        # Snap scene slots to frame boundaries so audio and transitions share exact times.
        for scene in episode.scenes:
            if abs(scene.duration_seconds * settings['fps'] - round(scene.duration_seconds * settings['fps'])) > 0.001:
                raise MediaError(f'Scene {scene.scene_id}: duration must align to {settings["fps"]} FPS. Use Fit to audio or round to a video frame.')
        for label, duration in (('Title', title_duration), ('End', end_duration)):
            if duration and (round(duration * settings['fps']) < 1 or abs(duration * settings['fps'] - round(duration * settings['fps'])) > .001):
                raise MediaError(f'{label} card duration must align to a video frame.')
        duration = title_duration + episode.timeline()[-1].end_seconds + end_duration
        cues = episode_captions(episode, spans)
        with tempfile.TemporaryDirectory(prefix='.vns-render-', dir=output.parent) as folder:
            work = Path(folder)
            notify(.03, 'Normalizing narration')
            voice = prepare_voice(episode, spans, work, cancel=cancel, progress=lambda p: notify(.03 + p * .09, 'Preparing narration'))
            mixed = mix_audio(episode, voice, work, duration, cancel=cancel)
            jobs = []
            if title_duration:
                title = work / 'title.png'
                card(settings['title_card'], title, (settings['width'], settings['height']),
                     background=settings['card_background'], accent=settings['card_accent'], text_color=settings['card_text'])
                jobs.append((title, title_duration, 'static', 'cut', .5, None, 'image', 0))
            for scene in episode.scenes:
                jobs.append((episode.resolve_asset(scene.visual_asset), scene.duration_seconds, scene.camera_motion,
                             scene.transition, scene.transition_seconds,
                             episode.resolve_asset(scene.foreground_asset) if scene.foreground_asset else None,
                             scene.media_type, scene.video_start_seconds))
            if end_duration:
                end = work / 'end.png'
                card(settings['end_card'], end, (settings['width'], settings['height']), kicker='TO BE CONTINUED',
                     background=settings['card_background'], accent=settings['card_accent'], text_color=settings['card_text'])
                jobs.append((end, end_duration, 'static', 'crossfade', .5, None, 'image', 0))
            segments = []
            previous = None
            cache = ShotCache(episode.directory / '.vns-cache' / 'shots') if use_cache else None
            cache_hits = 0
            for index, (source, length, motion, transition, fade, foreground, media_type, video_start) in enumerate(jobs):
                segment = work / f'segment_{index:04}.mp4'
                notify(.15 + .55 * index / len(jobs), f'Rendering shot {index + 1} of {len(jobs)}')
                key = shot_key(source, length, motion, settings, previous, transition, fade, foreground,
                               media_type=media_type, video_start_seconds=video_start) if cache else ''
                if cache and cache.restore(key, segment):
                    cache_hits += 1
                    notify(.15 + .55 * (index + 1) / len(jobs), f'Reused cached shot {index + 1} of {len(jobs)}')
                else:
                    _segment(source, segment, length, motion, settings, work, previous=previous,
                             transition=transition, transition_seconds=fade, foreground=foreground, cancel=cancel,
                             media_type=media_type, video_start_seconds=video_start,
                             progress=lambda p, i=index: notify(.15 + .55 * (i + p) / len(jobs), f'Rendering shot {i + 1} of {len(jobs)}'))
                    if cache:
                        cache.store(key, segment)
                previous = segment.with_suffix('.last.png')
                if not previous.is_file():
                    raise MediaError('Could not extract the final scene frame for transitions.')
                segments.append(segment)
            (work / 'video_list.txt').write_text(''.join(f"file '{p.name}'\n" for p in segments), encoding='utf-8')
            srt = work / 'captions.srt'
            srt.write_text(cues_to_srt(cues), encoding='utf-8')
            write_ass(cues, work / 'captions.ass', settings)
            staged = work / 'final.mp4'
            notify(.72, 'Encoding captions and final audio')
            ffmpeg(['-f', 'concat', '-safe', '1', '-i', 'video_list.txt', '-i', str(mixed),
                    '-vf', 'ass=captions.ass', '-map', '0:v:0', '-map', '1:a:0',
                    '-c:v', 'libx264', '-preset', settings['preset'], '-crf', str(settings['crf']),
                    '-threads', '2', '-pix_fmt', 'yuv420p', '-r', str(settings['fps']),
                    '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
                    '-t', str(duration), '-movflags', '+faststart', str(staged)], cwd=work,
                   cancel=cancel, progress=lambda p: notify(.72 + .22 * p, 'Encoding final MP4'), duration=duration)
            notify(.95, 'Verifying codecs, timing and full playback decode')
            report = verify_export(staged, width=settings['width'], height=settings['height'], fps=settings['fps'],
                                   duration=duration, subtitle_end=max((cue.end for cue in cues), default=0), cancel=cancel)
            if digest(Path(scenes_path)) != source_sha256 or source_inputs_sha256(Path(scenes_path)) != inputs_sha256:
                raise MediaError('Project, captions or media changed during rendering. Save the project and rerender; the previous export was preserved.')
            report.update({'output': str(output), 'episode_id': episode.episode_id,
                           'completed_utc': datetime.now(timezone.utc).isoformat(),
                           'source': str(Path(scenes_path).resolve()),
                           'source_sha256': source_sha256,
                           'source_inputs_sha256': inputs_sha256,
                           'target_duration_seconds': settings['target_duration'],
                           'within_default_60_90_seconds': 60 <= duration <= 90,
                           'caption_count': len(cues),
                           'scene_cache': {'enabled': use_cache, 'hits': cache_hits, 'misses': len(jobs) - cache_hits}})
            report['ffprobe']['format']['filename'] = str(output)
            report['output_sha256'] = digest(staged)
            staged_report = work / 'verification.json'
            atomic_json(staged_report, report)
            notify(.99, 'Publishing verified export')
            _publish_files([(staged, output), (srt, output.with_suffix('.srt')),
                            (staged_report, output.with_suffix('.verification.json'))], work)
            # All publication operations have finished before reporting success.
            if progress:
                progress(1.0, f'Verified export: {output}')
            return report
    finally:
        lock.unlink(missing_ok=True)


def build_render_plan(episode: Episode, *, check_assets: bool = False) -> dict[str, Any]:
    """Schedule visuals, narration slices, motion, and styled captions.

    Scene-specific narration clips play from zero. Scenes without a clip use
    the corresponding segment of the episode's narration.wav file.
    """
    timeline = episode.timeline()
    settings = settings_for(episode)
    title, end = card_durations(settings)
    planned = []
    for timed in timeline:
        scene = timed.scene
        visual = episode.resolve_asset(scene.visual_asset)
        audio = (episode.resolve_asset(scene.narration_audio or settings['narration_asset'])
                 if scene.narration.strip() or scene.narration_audio else None)
        foreground = episode.resolve_asset(scene.foreground_asset) if scene.foreground_asset else None
        if check_assets:
            for asset in (visual, audio, foreground):
                if asset is not None and not asset.is_file():
                    raise FileNotFoundError(f"Scene {scene.scene_id}: missing asset {asset}")
        planned.append({
            "scene_id": scene.scene_id,
            "start_seconds": title + timed.start_seconds,
            "end_seconds": title + timed.end_seconds,
            "duration_seconds": scene.duration_seconds,
            "visual_asset": str(visual),
            "media_type": scene.media_type,
            "video_start_seconds": scene.video_start_seconds,
            "video_audio_volume": scene.video_audio_volume,
            "camera_motion": scene.camera_motion,
            "narration": scene.narration,
            "narration_audio": str(audio) if audio is not None else None,
            "audio_offset_seconds": 0.0 if scene.narration_audio or audio is None else timed.start_seconds,
            "subtitle": scene.subtitle_text,
            "subtitle_style": scene.subtitle_style,
            "transition": scene.transition,
            "transition_seconds": scene.transition_seconds,
            "foreground_asset": str(foreground) if foreground else None,
        })
    return {
        "episode_id": episode.episode_id,
        "title": episode.title,
        "duration_seconds": title + (timeline[-1].end_seconds if timeline else 0.0) + end,
        "title_card": {"text": settings['title_card'], "duration_seconds": title},
        "end_card": {"text": settings['end_card'], "duration_seconds": end},
        "scenes": planned,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenes", type=Path, help="Path to the episode's scenes.json")
    parser.add_argument("--output", type=Path, help="Write the JSON plan to this file")
    parser.add_argument("--check-assets", action="store_true", help="Require all referenced media files to exist")
    parser.add_argument('--render', action='store_true', help='Encode and verify a real MP4 instead of writing a plan')
    parser.add_argument('--preview', action='store_true', help='Render a faster 360 × 640 draft')
    parser.add_argument('--no-cache', action='store_true', help='Rebuild all scene encodes')
    args = parser.parse_args()
    if args.render:
        output = args.output or Path('exports') / f'{args.scenes.parent.name}.mp4'
        try:
            report = render_episode(args.scenes, output, use_cache=not args.no_cache, overrides={'width': 360, 'height': 640, 'preset': 'ultrafast'} if args.preview else None,
                                    progress=lambda p, message: print(f'{p:6.1%} {message}', flush=True))
            print(json.dumps({k: v for k, v in report.items() if k != 'ffprobe'}, indent=2))
        except (ValueError, OSError, MediaError) as error:
            parser.error(str(error))
        return
    try:
        plan = build_render_plan(load_episode(args.scenes), check_assets=args.check_assets)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    serialized = json.dumps(plan, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()
