"""Generate one timed SRT cue per captioned scene."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import textwrap

from .scene_builder import Episode, load_episode


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str
    style: str = 'cinematic'


def make_cues(episode, spans) -> list[Cue]:
    from .settings import settings_for, card_durations
    settings = settings_for(episode)
    offset, _ = card_durations(settings)
    cues = []
    for timed, span in zip(episode.timeline(), spans):
        text = timed.scene.subtitle_text.strip()
        if not text:
            continue
        available = span.duration if span.path else timed.scene.duration_seconds
        words = text.split()
        chunks = []
        chunk = []
        for word in words:
            candidate = ' '.join([*chunk, word])
            if chunk and (len(chunk) >= settings['caption_words'] or len(textwrap.wrap(candidate, width=settings['wrap_chars'], break_long_words=True)) > 2):
                chunks.append(' '.join(chunk))
                chunk = []
            chunk.append(word)
        if chunk:
            chunks.append(' '.join(chunk))
        weight = sum(len(item) for item in chunks)
        start = offset + timed.start_seconds
        elapsed = 0
        for chunk in chunks:
            end = offset + timed.start_seconds + available * (elapsed + len(chunk)) / weight
            wrapped = '\n'.join(textwrap.wrap(chunk, width=settings['wrap_chars'], break_long_words=True))
            cues.append(Cue(round(start, 3), round(end, 3), wrapped, timed.scene.subtitle_style))
            elapsed += len(chunk)
            start = end
    validate_cues(cues, offset + episode.timeline()[-1].end_seconds)
    return cues


def validate_cues(cues: list[Cue], duration: float, windows=None) -> None:
    import math
    last_end = 0.0
    for index, cue in enumerate(cues, 1):
        if not math.isfinite(cue.start) or not math.isfinite(cue.end) or cue.start < 0 or cue.end <= cue.start:
            raise ValueError(f'Caption {index}: start/end must be finite and end must be after start')
        if cue.start < last_end - 0.001 or cue.end > duration + 0.001:
            raise ValueError(f'Caption {index}: overlaps another caption or exceeds the audio/video duration')
        if windows and not any(cue.start >= start - 0.002 and cue.end <= end + 0.002 for start, end in windows):
            raise ValueError(f'Caption {index}: timing is outside its scene narration. Correct its start/end or regenerate captions.')
        if not cue.text.strip():
            raise ValueError(f'Caption {index}: text is empty')
        last_end = cue.end


def cues_to_srt(cues: list[Cue]) -> str:
    return '\n\n'.join(f'{index}\n{_timestamp(round(cue.start * 1000))} --> {_timestamp(round(cue.end * 1000))}\n{cue.text}'
                       for index, cue in enumerate(cues, 1)) + ('\n' if cues else '')


def parse_srt(text: str) -> list[Cue]:
    def seconds(value):
        hours, minutes, secs, millis = map(int, re.split('[:,.]', value))
        if minutes >= 60 or secs >= 60:
            raise ValueError('Invalid SRT minute or second value')
        return hours * 3600 + minutes * 60 + secs + millis / 1000
    cues = []
    for block in re.split(r'\n\s*\n', text.replace('\r\n', '\n').strip()):
        if not block.strip():
            continue
        lines = block.splitlines()
        if len(lines) < 3 or not lines[0].strip().isdigit():
            raise ValueError('Each SRT cue needs an index, timestamps, and text')
        match = re.fullmatch(r'(\d+:\d{2}:\d{2}[,.]\d{3})\s+-->\s+(\d+:\d{2}:\d{2}[,.]\d{3})', lines[1].strip())
        if not match:
            raise ValueError(f'Invalid SRT timing: {lines[1]}')
        cues.append(Cue(seconds(match[1]), seconds(match[2]), '\n'.join(lines[2:])))
    return cues


def write_ass(cues: list[Cue], path: Path, settings: dict) -> None:
    def stamp(seconds):
        centiseconds = round(seconds * 100)
        hours, rest = divmod(centiseconds, 360000)
        minutes, rest = divmod(rest, 6000)
        sec, fraction = divmod(rest, 100)
        return f'{hours}:{minutes:02}:{sec:02}.{fraction:02}'
    header = '[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\n'
    header += 'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
    rgb = settings.get('caption_color', '#FFFFFF').lstrip('#')
    colour = '&H00' + rgb[4:6] + rgb[2:4] + rgb[0:2]
    for name in ('cinematic', 'standard'):
        size = settings['font_size'] if name == 'cinematic' else round(settings['font_size'] * .9)
        bold = -1 if name == 'cinematic' else 0
        header += f'Style: {name},{settings["font"]},{size},{colour},{colour},&H00101116,&H80000000,{bold},0,0,0,100,100,0,0,1,{settings["outline"]},{settings["shadow"]},2,{settings["margin_left"]},{settings["margin_right"]},{settings["margin_bottom"]},1\n'
    header += '\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
    events = []
    for cue in cues:
        text = cue.text.replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\n', '\\N')
        events.append(f'Dialogue: 0,{stamp(cue.start)},{stamp(cue.end)},{cue.style},,0,0,0,,{text}\n')
    path.write_text(header + ''.join(events), encoding='utf-8-sig')


def _timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def generate_subtitles(episode: Episode) -> str:
    """Create draft timing from scene slots before recordings are available.

    Rendering and the CLI use make_cues with probed audio durations instead.
    This pure helper remains useful for planning and backward compatibility.
    """
    cues = []
    for timed in episode.timeline():
        text = timed.scene.subtitle_text.strip()
        if not text:
            continue
        start = round(timed.start_seconds * 1000)
        end = round(timed.end_seconds * 1000)
        if end <= start:
            raise ValueError(f"Scene {timed.scene.scene_id} is too short for an SRT cue")
        caption = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        cues.append(f"{len(cues) + 1}\n{_timestamp(start)} --> {_timestamp(end)}\n{caption}\n")
    return "\n".join(cues)


def main() -> None:
    from .audio_manager import inspect_narration
    from .media import MediaError
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenes", type=Path, help="Path to the episode's scenes.json")
    parser.add_argument("--output", type=Path, help="Defaults to subtitles.srt beside scenes.json")
    args = parser.parse_args()
    try:
        episode = load_episode(args.scenes)
        subtitles = cues_to_srt(make_cues(episode, inspect_narration(episode)))
        output = args.output or args.scenes.with_name("subtitles.srt")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(subtitles, encoding="utf-8")
    except (ValueError, OSError, MediaError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
