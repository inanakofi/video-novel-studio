"""Frame-snapped timeline edits and decoded narration waveforms, without AI."""
from array import array
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import wave

from .audio_manager import inspect_narration, prepare_voice
from .media import atomic_json, audio_duration, ffmpeg, RenderCancelled
from .render_cache import digest
from .settings import settings_for, card_durations
from .subtitle_generator import validate_cues


def cue_windows(episode, spans=None):
    spans = inspect_narration(episode) if spans is None else spans
    title, end = card_durations(settings_for(episode))
    return [(title + timed.start_seconds,
             title + timed.start_seconds + (span.duration if span.path else timed.scene.duration_seconds))
            for timed, span in zip(episode.timeline(), spans)]


def total_duration(episode):
    title, end = card_durations(settings_for(episode))
    return title + episode.timeline()[-1].end_seconds + end


def edit_timeline(episode, cues, kind, index, start, end):
    """Return a validated edit; errors leave the caller's episode/cues untouched.

    Scene end edits ripple subsequent caption positions. A continuous episode
    recording cannot be rippled safely without also editing/splitting its audio.
    """
    if not all(math.isfinite(n) for n in (start, end)):
        raise ValueError('Timeline times must be finite.')
    fps = settings_for(episode)['fps']
    # Audio/caption boundaries can fall between frames; preserve their exact
    # millisecond positions. Visual durations and SFX placement snap to frames.
    if kind != 'caption':
        start, end = round(start * fps) / fps, round(end * fps) / fps
    updated, changed = episode, list(cues)
    title, _ = card_durations(settings_for(episode))
    if kind == 'caption':
        changed[index] = replace(cues[index], start=round(start, 3), end=round(end, 3))
    elif kind in ('scene', 'transition'):
        scenes = list(episode.scenes)
        timed = episode.timeline()[index]
        if kind == 'scene':
            if any(s.narration.strip() and not s.narration_audio for s in scenes):
                raise ValueError('Scene trimming needs separate scene recordings. Split the continuous episode recording first.')
            length = end - title - timed.start_seconds
            if length < 1 / fps - .00001:
                raise ValueError('A scene must last at least one frame.')
            delta = length - scenes[index].duration_seconds
            boundary = title + timed.end_seconds
            changed = [replace(cue, start=round(cue.start + delta, 3), end=round(cue.end + delta, 3))
                       if cue.start >= boundary - .002 else cue for cue in cues]
            scenes[index] = replace(scenes[index], duration_seconds=length)
            effects = [dict(effect) for effect in settings_for(episode)['sound_effects']]
            for effect in effects:
                if effect['start_seconds'] >= boundary - .002:
                    effect['start_seconds'] = round(effect['start_seconds'] + delta, 3)
            updated = replace(episode, settings={**episode.settings, 'sound_effects': effects})
        else:
            length = end - title - timed.start_seconds
            if not 1 / fps - .00001 <= length <= scenes[index].duration_seconds / 2 + .00001:
                raise ValueError('Transition must be at least one frame and at most half the scene.')
            scenes[index] = replace(scenes[index], transition_seconds=length,
                                    transition='crossfade' if scenes[index].transition == 'cut' else scenes[index].transition)
        updated = replace(updated, scenes=tuple(scenes))
    elif kind == 'effect':
        effects = [dict(effect) for effect in settings_for(episode)['sound_effects']]
        length = audio_duration(episode.resolve_asset(effects[index]['asset']))
        if start < 0 or start + length > total_duration(episode) + .002:
            raise ValueError('The complete sound effect must fit inside the episode.')
        effects[index]['start_seconds'] = round(start, 3)
        updated = replace(episode, settings={**episode.settings, 'sound_effects': effects})
    else:
        raise ValueError('Unknown timeline track.')
    windows = cue_windows(updated)  # Also refuses to cut narration short.
    validate_cues(changed, total_duration(updated), windows)
    # A trim must not silently cut an existing effect at the end.
    for effect in settings_for(updated)['sound_effects']:
        if effect['start_seconds'] + audio_duration(updated.resolve_asset(effect['asset'])) > total_duration(updated) + .025:
            raise ValueError('This trim would cut a sound effect. Move it earlier first.')
    return updated, changed


def waveform(path: Path, *, bins_per_second=100, cancel=None):
    """Peak/RMS envelopes of PCM, streamed in 10ms blocks (bounded memory)."""
    peaks, levels = [], []
    with wave.open(str(path), 'rb') as handle:
        if handle.getsampwidth() != 2:
            raise ValueError('Waveform input must be 16-bit PCM.')
        step = max(1, round(handle.getframerate() / bins_per_second))
        duration = handle.getnframes() / handle.getframerate()
        while raw := handle.readframes(step):
            if cancel and cancel.is_set():
                raise RenderCancelled('Waveform analysis cancelled.')
            samples = array('h', raw)
            if sys.byteorder != 'little':
                samples.byteswap()
            peaks.append(round(max(abs(n) for n in samples) / 32768, 5))
            levels.append(round(math.sqrt(sum(n*n for n in samples) / len(samples)) / 32768, 5))
    return {'peaks': peaks, 'rms': levels, 'bin_seconds': step / handle.getframerate(), 'duration': duration}


def prepare_waveform(episode, *, progress=None, cancel=None):
    """Build current narration audition from the same timing/normalization as export."""
    settings = settings_for(episode)
    spans = inspect_narration(episode)
    title, end = card_durations(settings)
    signature = {'version': digest(Path(__file__).with_name('audio_manager.py')),
                 'cards': [title, end], 'volume': settings['narration_volume'],
                 'clips': [(digest(s.path) if s.path else None, s.offset, s.duration, scene.duration_seconds)
                           for s, scene in zip(spans, episode.scenes)]}
    key = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    root = episode.directory / '.vns-cache' / 'waveforms'
    root.mkdir(parents=True, exist_ok=True)
    target, info = root / f'{key}.wav', root / f'{key}.json'
    try:
        data = json.loads(info.read_text(encoding='utf-8'))
        if data['sha256'] == digest(target):
            return {**data, 'path': str(target), 'key': key}
    except (OSError, ValueError, KeyError):
        pass
    with tempfile.TemporaryDirectory(prefix='.wave-', dir=root) as folder:
        work = Path(folder)
        voice = prepare_voice(episode, spans, work, cancel=cancel, progress=progress)
        mono = work / 'audition.wav'
        ffmpeg(['-i', str(voice), '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', str(mono)], cancel=cancel)
        data = waveform(mono, cancel=cancel)
        data['sha256'] = digest(mono)
        os.replace(mono, target)
        atomic_json(info, data)
    return {**data, 'path': str(target), 'key': key}


def silent_ranges(envelope, minimum=1.5, threshold=.008):
    """Advisory pauses, not a speech detector; thresholds are user-adjustable."""
    step = envelope['bin_seconds']
    result, start = [], None
    for i, value in enumerate([*envelope['rms'], 1.0]):
        if value < threshold and start is None:
            start = i * step
        elif value >= threshold and start is not None:
            end = min(i * step, envelope['duration'])
            if end - start >= minimum:
                result.append((start, end))
            start = None
    return result
