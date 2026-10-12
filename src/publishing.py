"""Offline publishing checks. Warnings are editorial guides, not platform rules."""
import argparse
import json
import math

from .media import audio_duration
from .scene_builder import load_episode
from .series_tools import reference_errors
from .settings import settings_for, card_durations
from .timeline import total_duration, prepare_waveform, silent_ranges
from .video_renderer import asset_errors, episode_captions


def publishing_check(episode, *, progress=None, cancel=None):
    issues = []
    def add(level, code, message, seconds=None):
        issues.append({'level': level, 'code': code, 'message': message, 'seconds': seconds})
    def notify(value, text):
        if progress:
            progress(value, text)
    settings = settings_for(episode)
    duration = total_duration(episode)
    notify(.05, 'Checking media, narration and captions')
    errors = asset_errors(episode)
    for error in errors:
        add('error', 'asset', error)
    for error in reference_errors(episode):
        add('warning', 'continuity', error)
    if not settings['publish_min_duration'] <= duration <= settings['publish_max_duration']:
        add('warning', 'duration', f'{duration:.2f}s is outside your {settings["publish_min_duration"]:g}–{settings["publish_max_duration"]:g}s publishing range.')
    title, end = card_durations(settings)
    for label, length in [*( (f'Scene {s.scene_id}', s.duration_seconds) for s in episode.scenes), ('Title', title), ('End', end)]:
        if length and abs(length * settings['fps'] - round(length * settings['fps'])) > .001:
            add('error', 'frame_timing', f'{label} duration is not aligned to a video frame.')
    for effect in settings['sound_effects']:
        try:
            start, volume = effect['start_seconds'], effect['volume']
            if type(start) not in (int, float) or not math.isfinite(start) or start < 0:
                raise ValueError('Invalid sound effect start time.')
            if type(volume) not in (int, float) or not math.isfinite(volume) or not 0 <= volume <= 1:
                raise ValueError('Sound effect volume must be 0–1.')
            if start + audio_duration(episode.resolve_asset(effect['asset'])) > duration + .025:
                raise ValueError(f'Sound effect {effect["asset"]} ends beyond the episode.')
        except (ValueError, RuntimeError, KeyError, TypeError) as error:
            add('error', 'effect', str(error))
    cues = []
    try:
        cues = episode_captions(episode)
    except (ValueError, RuntimeError, OSError) as error:
        add('error', 'captions', str(error))
    if not cues and any(scene.narration.strip() for scene in episode.scenes):
        add('warning', 'captions_empty', 'Narration is present but no captions are enabled.')
    # Conservative, editable composition guide; platforms can change their UI.
    if cues and (settings['margin_bottom'] < 320 or settings['margin_right'] < 170 or settings['margin_left'] < 80):
        add('warning', 'safe_area', 'Captions enter the overlay guide. Suggested 1080p margins: bottom ≥320, right ≥170, left ≥80. Review the video on your target platform.')
    if cues and settings['font_size'] < 42:
        add('warning', 'small_text', 'Caption font is below 42 in 1080p units; check mobile readability.')
    for index, cue in enumerate(cues, 1):
        if len(cue.text.replace('\n', '')) / (cue.end - cue.start) > 22:
            add('warning', 'reading_speed', f'Caption {index} exceeds 22 characters per second.', cue.start)
        if len(cue.text.splitlines()) > 2 or any(len(line) > settings['wrap_chars'] for line in cue.text.splitlines()):
            add('warning', 'caption_wrap', f'Caption {index} exceeds the chosen line length or two lines. Shorten or rewrap it.', cue.start)
        # Approximate horizontal fit, explicitly advisory: font metrics vary.
        if max(map(len, cue.text.splitlines()), default=0) * settings['font_size'] * .55 > 1080 - settings['margin_left'] - settings['margin_right']:
            add('warning', 'caption_width', f'Caption {index} may exceed the usable width at this font size; inspect its preview.', cue.start)
    if not errors:
        notify(.3, 'Measuring narration pauses from local audio')
        envelope = prepare_waveform(episode, cancel=cancel,
                                    progress=lambda value: notify(.3 + .6 * value, 'Analyzing narration waveform'))
        for start, stop in silent_ranges(envelope, minimum=settings['pause_warning_seconds']):
            # Intentional silent title/end cards do not trigger pause warnings.
            start, stop = max(title, start), min(duration-end, stop)
            if stop - start >= settings['pause_warning_seconds']:
                add('warning', 'pause', f'Low narration level for {stop-start:.2f}s ({start:.2f}–{stop:.2f}s). Review this pause.', start)
    report = {'ready': not any(i['level'] == 'error' for i in issues),
              'duration_seconds': duration, 'issues': issues,
              'guide': 'Advisory mobile composition/readability checks; no platform certification or speech alignment.'}
    notify(1, 'Publishing check complete')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenes')
    args = parser.parse_args()
    report = publishing_check(load_episode(args.scenes))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report['ready'] else 1)


if __name__ == '__main__':
    main()
