"""Create original local sample art and installed-Windows-voice recordings."""
from __future__ import annotations

import argparse
from dataclasses import replace
import math
from pathlib import Path
import random
import wave
import struct

from PIL import Image, ImageDraw

from .audio_manager import synthesize_local
from .media import audio_duration
from .scene_builder import Episode, Scene, save_episode
from .visuals import font


NARRATION = [
    'On the night Ama returned to Accra, every window in her family mansion was dark. At the gate, a young courier held a letter addressed in her mother\'s handwriting. Her mother had been gone for twelve years. Yet the ink on the envelope was still fresh.',
    'Inside the courtyard, Ama broke the seal. The letter contained a photograph of a boy wearing her father\'s signet ring. On the back were five words: Keep him away from home. Before she could turn the photograph over again, footsteps sounded behind the locked garden door.',
    'The courier stepped into the lamplight and raised his hand. The same silver ring caught the light. Ama asked him who he was. He looked past her at the mansion, where one upstairs window had suddenly brightened. Ask your father, he said. He knows why I came back.',
]


def create_sample_score(root: Path) -> tuple[Path, Path]:
    """Original procedural ambience and paper sound; both dedicated to CC0."""
    music = root / 'assets' / 'music' / 'Studio ambience.wav'
    effect = root / 'assets' / 'sound_effects' / 'Paper rustle.wav'
    music.parent.mkdir(parents=True, exist_ok=True)
    effect.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 48000
    if not music.exists():
        frames = bytearray()
        for index in range(sample_rate * 24):
            t = index / sample_rate
            local = t % 6
            root_note = (164.8138, 196.0, 130.8128, 146.8324)[int(t // 6)]
            envelope = min(1, local / .8, (6-local) / 1.2)
            value = sum(math.sin(2 * math.pi * root_note * ratio * t) for ratio in (1, 1.25, 1.5)) / 3
            frames.extend(struct.pack('<h', round(value * envelope * 4000)))
        with wave.open(str(music), 'wb') as output:
            output.setparams((1, 2, sample_rate, 0, 'NONE', 'not compressed'))
            output.writeframes(frames)
    if not effect.exists():
        rng = random.Random(724)
        frames = bytearray()
        filtered = 0.0
        for index in range(round(sample_rate * .45)):
            t = index / sample_rate
            filtered = .7 * filtered + .3 * rng.uniform(-1, 1)
            envelope = math.sin(math.pi * t / .45) ** 2
            frames.extend(struct.pack('<h', round(filtered * envelope * 9000)))
        with wave.open(str(effect), 'wb') as output:
            output.setparams((1, 2, sample_rate, 0, 'NONE', 'not compressed'))
            output.writeframes(frames)
    return music, effect


def draw_sample_art(directory: Path) -> list[Path]:
    """Original geometric illustrations, drawn locally; no downloaded/AI assets."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for index in range(3):
        width, height = 720, 1280
        image = Image.new('RGB', (width, height))
        draw = ImageDraw.Draw(image)
        for y in range(height):
            t = y / height
            draw.line((0, y, width, y), fill=(int(12 + 20*t), int(22 + 24*t), int(45 + 22*t)))
        rng = random.Random(42)
        for _ in range(55):
            x, y = rng.randrange(width), rng.randrange(540)
            draw.ellipse((x, y, x+2, y+2), fill='#b9c8d8')
        draw.ellipse((510, 115, 590, 195), fill='#f0dfa9')
        draw.rectangle((0, 880, width, height), fill='#1d2a36')
        draw.polygon([(0, 1030), (360, 860), (720, 1030), (720, 1280), (0, 1280)], fill='#38444a')
        draw.rectangle((100, 450, 620, 895), fill='#766e65')
        draw.polygon([(70, 460), (360, 310), (650, 460)], fill='#333945')
        draw.rectangle((80, 650, 640, 680), fill='#b3a187')
        for x in (145, 265, 385, 505):
            draw.rectangle((x, 510, x+66, 605), fill='#202633')
            draw.rectangle((x, 730, x+66, 825), fill='#d6ad62' if index == 2 and x == 505 else '#202633')
        for x in (115, 580):
            draw.rectangle((x, 680, x+30, 900), fill='#b8a990')
        draw.rectangle((316, 730, 407, 905), fill='#283137')
        for x in (40, 650):
            draw.rectangle((x, 710, x+18, 1040), fill='#1b2430')
            draw.ellipse((x-18, 690, x+36, 745), fill='#f4d58b')
        # Ama and the courier, deliberately simple editorial silhouettes.
        draw.ellipse((205, 870, 263, 932), fill='#412d2e')
        draw.polygon([(206, 923), (262, 923), (300, 1115), (175, 1115)], fill='#bf6f54')
        draw.rectangle((211, 1105, 225, 1180), fill='#382c2d')
        draw.rectangle((253, 1105, 266, 1180), fill='#382c2d')
        draw.ellipse((455, 858, 511, 917), fill='#3a2d30')
        draw.polygon([(450, 917), (515, 917), (535, 1070), (437, 1070)], fill='#4b7778')
        draw.rectangle((455, 1060, 473, 1185), fill='#202b38')
        draw.rectangle((497, 1060, 515, 1185), fill='#202b38')
        if index == 1:
            draw.rounded_rectangle((208, 465, 510, 700), radius=8, fill='#e6d4aa', outline='#c8ad79', width=4)
            for y in (520, 545, 570, 595):
                draw.line((245, y, 475, y), fill='#82755f', width=3)
            draw.ellipse((332, 625, 386, 679), fill='#a34f48')
        if index == 2:
            draw.ellipse((455, 972, 480, 997), outline='#e0d5ac', width=6)
        draw.text((54, 62), ['THE LETTER', 'THE WARNING', 'THE RETURN'][index], font=font(21), fill='#b9c8d8')
        path = directory / f'Scene {index+1:02} – Accra.png'
        image.save(path)
        paths.append(path)
    foreground = Image.new('RGBA', (720, 1280))
    draw = ImageDraw.Draw(foreground)
    for x in (16, 100, 580, 665):
        draw.rectangle((x, 500, x+15, 1280), fill='#111b29')
        draw.polygon([(x-5, 505), (x+8, 470), (x+22, 505)], fill='#111b29')
    draw.rectangle((0, 960, 720, 980), fill='#111b29')
    foreground.save(directory / 'Gate foreground.png')
    return paths


def create_sample(root: Path, *, short=False, progress=print) -> Path:
    slug = 'studio_prototype' if short else 'the_letter_at_the_gate'
    story = root / 'stories' / slug
    directory = story / 'episodes' / 'episode_001'
    path = directory / 'scenes.json'
    if path.is_file():
        progress(f'Sample already exists: {path}')
        return path
    assets = directory / 'assets'
    images = draw_sample_art(assets)
    scenes = []
    for index, text in enumerate(NARRATION):
        if short:
            text = text.split('. ')[0] + '.'
        progress(f'Creating installed-voice recording {index + 1}/3')
        recording = synthesize_local(text, assets / f'Ama scène {index+1:02}.wav')
        duration = math.ceil((audio_duration(recording) + .3) * 30) / 30
        scenes.append(Scene(index+1, duration, images[index].relative_to(directory).as_posix(), text,
                            ['slow_zoom_in', 'pan_right', 'slow_zoom_out'][index], 'cinematic',
                            recording.relative_to(directory).as_posix(), transition='crossfade'))
    settings = {'title_card': 'The Letter at the Gate', 'end_card': 'Who is the boy with the silver ring?', 'target_duration': 75.0}
    if not short:
        remaining = max(0, round((75 - 4 - sum(s.duration_seconds for s in scenes)) * 30))
        scenes = [replace(scene, duration_seconds=scene.duration_seconds + (remaining // 3 + (i < remaining % 3)) / 30) for i, scene in enumerate(scenes)]
        create_sample_score(root)
        settings.update({'music_asset': '../../../../assets/music/Studio ambience.wav', 'music_volume': .22,
                         'sound_effects': [{'asset': '../../../../assets/sound_effects/Paper rustle.wav',
                                            'start_seconds': 2 + scenes[0].duration_seconds, 'volume': .3}]})
        scenes[2] = replace(scenes[2], camera_motion='parallax', foreground_asset='assets/Gate foreground.png')
    episode = Episode('episode_001', 'The Letter at the Gate', directory, tuple(scenes), settings,
                      {'number': 1, 'hook': NARRATION[0].split('. ')[0] + '.', 'cliffhanger': 'Who is the boy with the silver ring?', 'previous_episode': None,
                       'sample_audio': 'Windows System.Speech installed voice; synthetic, offline, not a human recording.'})
    save_episode(episode)
    (directory / 'script.md').write_text('# The Letter at the Gate\n\n' + '\n\n'.join(f'## Scene {s.scene_id}\n\n{s.narration}' for s in scenes), encoding='utf-8')
    for name, content in {
        'series_bible.md': '# The Letter at the Gate\n\nA family mystery in Accra. Ama returns home to find a letter in her late mother\'s handwriting.\n',
        'character_bible.md': '# Characters\n\n## Ama\nAn observant young woman returning home. Terracotta dress.\n\n## The courier\nA guarded young man with a silver signet ring. Teal shirt.\n',
        'location_bible.md': '# Locations\n\n## Family mansion\nA quiet Accra courtyard, iron gate, warm lamps and a single illuminated upstairs window.\n',
        'continuity_log.md': '# Continuity\n\nEpisode 001: Ama sees her father\'s ring on the courier. Her mother died twelve years before this episode. The father\'s whereabouts remain unresolved.\n',
    }.items():
        (story / name).write_text(content, encoding='utf-8')
    (assets / 'PROVENANCE.md').write_text('# Sample provenance\n\nThe story text and geometric illustrations were created for this project using Python/Pillow and are dedicated to the public domain under CC0 1.0. No photographs, music libraries, or AI image service were used.\n\nThe WAV narration was synthesized locally using an installed Windows System.Speech voice. It is explicitly synthetic demo narration. Voice software remains subject to its operating-system license; use your own recordings for a wholly self-authored soundtrack.\n', encoding='utf-8')
    progress(f'Created {path}')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--short', action='store_true')
    args = parser.parse_args()
    create_sample(args.root.resolve(), short=args.short)


if __name__ == '__main__':
    main()
