"""Imported recordings and optional installed Windows speech, entirely offline."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile

from .media import MediaError, audio_duration, ffmpeg, run
from .settings import settings_for, card_durations


@dataclass(frozen=True)
class AudioSpan:
    scene_id: int
    path: Path | None
    offset: float
    duration: float


def inspect_narration(episode) -> list[AudioSpan]:
    settings = settings_for(episode)
    durations = {}
    spans = []
    for timed in episode.timeline():
        scene = timed.scene
        if not scene.narration.strip() and not scene.narration_audio:
            spans.append(AudioSpan(scene.scene_id, None, 0, 0))
            continue
        path = episode.resolve_asset(scene.narration_audio or settings['narration_asset'])
        if path not in durations:
            durations[path] = audio_duration(path)
        length = durations[path]
        offset = 0.0 if scene.narration_audio else timed.start_seconds
        if scene.narration_audio:
            if length > scene.duration_seconds + 0.025:
                raise MediaError(f'Scene {scene.scene_id}: narration is {length:.2f}s but the scene is {scene.duration_seconds:.2f}s. Use Fit to audio or increase its duration.')
            length = min(length, scene.duration_seconds)
        else:
            if length + 0.025 < timed.end_seconds:
                raise MediaError(f'Scene {scene.scene_id}: episode recording ends at {length:.2f}s; it must cover {timed.end_seconds:.2f}s. Import a complete recording or use separate scene clips.')
            length = min(scene.duration_seconds, length - offset)
        spans.append(AudioSpan(scene.scene_id, path, offset, length))
    return spans


def installed_voices() -> list[str]:
    if sys.platform != 'win32' or not shutil.which('powershell'):
        return []
    command = "Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; @($s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }) | ConvertTo-Json -Compress; $s.Dispose()"
    try:
        value = json.loads(run(['powershell', '-NoProfile', '-NonInteractive', '-Command', command]))
        return [value] if isinstance(value, str) else value
    except (MediaError, ValueError):
        return []


def synthesize_local(text: str, output: Path, *, voice: str = '', rate: int = -1, cancel=None) -> Path:
    if not text.strip():
        raise MediaError('Enter narration text before creating a local voice recording.')
    if sys.platform != 'win32' or not shutil.which('powershell'):
        raise MediaError('Installed Windows speech is unavailable. Import a recorded WAV, MP3, or other FFmpeg-supported audio file.')
    if not -10 <= rate <= 10:
        raise ValueError('Speech rate must be -10 to 10')
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.speech-', dir=output.parent) as folder:
        folder = Path(folder)
        (folder / 'text.txt').write_text(text, encoding='utf-8')
        (folder / 'speak.ps1').write_text('''param([string]$TextPath, [string]$OutputPath, [string]$VoiceName, [int]$Rate)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  if ($VoiceName) { $speaker.SelectVoice($VoiceName) }
  $speaker.Rate = $Rate
  $speaker.SetOutputToWaveFile($OutputPath)
  $speaker.Speak((Get-Content -LiteralPath $TextPath -Raw -Encoding UTF8))
  $speaker.SetOutputToNull()
} finally { $speaker.Dispose() }
''', encoding='utf-8')
        temporary = folder / 'speech.wav'
        run(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
             '-File', str(folder / 'speak.ps1'), '-TextPath', str(folder / 'text.txt'),
             '-OutputPath', str(temporary), '-VoiceName', voice, '-Rate', str(rate)], cancel=cancel)
        audio_duration(temporary)
        os.replace(temporary, output)
    return output


def prepare_voice(episode, spans: list[AudioSpan], work: Path, *, cancel=None, progress=None) -> Path:
    settings = settings_for(episode)
    title, end = card_durations(settings)
    slots = [(title, None)] if title else []
    slots += [(scene.duration_seconds, span) for scene, span in zip(episode.scenes, spans)]
    if end:
        slots.append((end, None))
    paths = []
    for index, (duration, span) in enumerate(slots):
        output = work / f'voice_{index:04}.wav'
        if span is None or span.path is None:
            args = ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-t', str(duration)]
        else:
            args = ['-i', str(span.path),
                    '-af', f'atrim=start={span.offset}:duration={span.duration},asetpts=PTS-STARTPTS,loudnorm=I=-18:TP=-2:LRA=11,aresample=48000,asetpts=N/SR/TB,volume={settings["narration_volume"]},apad,atrim=end_sample={round(duration * 48000)},asetpts=N/SR/TB']
        ffmpeg([*args, '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', str(output)], cancel=cancel)
        paths.append(output)
        if progress:
            progress((index + 1) / len(slots))
    (work / 'voice_list.txt').write_text(''.join(f"file '{p.name}'\n" for p in paths), encoding='utf-8')
    voice = work / 'voice.wav'
    ffmpeg(['-f', 'concat', '-safe', '1', '-i', 'voice_list.txt', '-c:a', 'pcm_s16le', str(voice)], cwd=work, cancel=cancel)
    return voice


def mix_audio(episode, voice: Path, work: Path, duration: float, *, cancel=None) -> Path:
    settings = settings_for(episode)
    args = ['-i', str(voice)]
    graph = []
    mix = ['voice']
    clips = [t for t in episode.timeline() if t.scene.media_type == 'video' and t.scene.video_audio_volume > 0]
    chains = (['sidechain'] if settings['music_asset'] and settings['duck_music'] else []) + [f'clipchain{i}' for i in range(len(clips))]
    graph.append(f'[0:a]asplit={1 + len(chains)}[voice]' + ''.join(f'[{c}]' for c in chains) if chains else '[0:a]anull[voice]')
    index = 1
    if settings['music_asset']:
        music = episode.resolve_asset(settings['music_asset'])
        audio_duration(music)
        args += ['-stream_loop', '-1', '-i', str(music)]
        graph.append(f'[{index}:a]atrim=duration={duration},asetpts=PTS-STARTPTS,volume={settings["music_volume"]}[music]')
        if settings['duck_music']:
            graph.append('[music][sidechain]sidechaincompress=threshold=0.025:ratio=8:attack=15:release=350[ducked]')
            mix.append('ducked')
        else:
            mix.append('music')
        index += 1
    title, _ = card_durations(settings)
    for clip_index, timed in enumerate(clips):
        scene = timed.scene
        args += ['-i', str(episode.resolve_asset(scene.visual_asset))]
        graph.append(f'[{index}:a]atrim=start={scene.video_start_seconds}:duration={scene.duration_seconds},'
                     f'asetpts=PTS-STARTPTS,volume={scene.video_audio_volume},'
                     f'adelay={round((title + timed.start_seconds) * 1000)}:all=1,apad,atrim=duration={duration}[clip{clip_index}]')
        graph.append(f'[clip{clip_index}][clipchain{clip_index}]sidechaincompress=threshold=0.025:ratio=8:attack=15:release=350[clipduck{clip_index}]')
        mix.append(f'clipduck{clip_index}')
        index += 1
    for effect in settings['sound_effects']:
        if not isinstance(effect, dict) or not {'asset', 'start_seconds', 'volume'}.issubset(effect):
            raise MediaError('Each sound effect needs asset, start_seconds, and volume.')
        start, volume = effect['start_seconds'], effect['volume']
        if type(start) not in (int, float) or not math.isfinite(start) or not 0 <= start < duration:
            raise MediaError('Sound effect start must fall inside the video.')
        if type(volume) not in (int, float) or not math.isfinite(volume) or not 0 <= volume <= 1:
            raise MediaError('Sound effect volume must be 0–1.')
        asset = episode.resolve_asset(effect['asset'])
        length = audio_duration(asset)
        if start + length > duration + 0.025:
            raise MediaError(f'Sound effect {asset.name} extends beyond the video. Move it earlier or shorten the audio.')
        args += ['-i', str(asset)]
        graph.append(f'[{index}:a]volume={volume},adelay={round(start * 1000)}:all=1[fx{index}]')
        mix.append(f'fx{index}')
        index += 1
    graph.append(''.join(f'[{name}]' for name in mix) + f'amix=inputs={len(mix)}:duration=first:normalize=0,alimiter=limit=0.89:level=false:latency=true,atrim=duration={duration}[mixed]')
    output = work / 'mixed.wav'
    ffmpeg([*args, '-filter_complex', ';'.join(graph), '-map', '[mixed]', '-ar', '48000', '-ac', '2',
            '-c:a', 'pcm_s16le', str(output)], cancel=cancel)
    return output
