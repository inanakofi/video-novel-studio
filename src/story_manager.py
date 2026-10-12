"""Local story library, atomic saves, asset import and editable script breakdowns."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import unicodedata

from .media import atomic_json, audio_duration
from .scene_builder import Episode, Scene, load_episode, save_episode


BIBLES = ('series_bible.md', 'character_bible.md', 'location_bible.md', 'continuity_log.md')


def atomic_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.save-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def slug(text: str) -> str:
    ascii_text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '_', ascii_text.lower()).strip('_')[:70] or 'story'


class StoryLibrary:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        for directory in ('stories', 'assets/characters', 'assets/backgrounds', 'assets/music', 'assets/sound_effects', 'exports'):
            (self.root / directory).mkdir(parents=True, exist_ok=True)

    def stories(self) -> list[Path]:
        return sorted(path for path in (self.root / 'stories').iterdir() if path.is_dir())

    def episodes(self, story: Path) -> list[Path]:
        return sorted(story.glob('episodes/episode_*/scenes.json'))

    def story_title(self, story: Path) -> str:
        path = story / 'story.json'
        fallback = story.name.replace('_', ' ').title()
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(data, dict) and isinstance(data.get('title'), str) and data['title'].strip():
                    return data['title']
            except (OSError, ValueError):
                pass
            # A damaged library entry must not prevent access to healthy stories.
            return fallback + ' (invalid story.json)'
        return fallback

    def create_story(self, title: str, premise: str = '') -> Path:
        if not title.strip():
            raise ValueError('Enter a story title.')
        base = slug(title)
        path = self.root / 'stories' / base
        index = 2
        while path.exists():
            path = self.root / 'stories' / f'{base}_{index}'
            index += 1
        path.mkdir()
        (path / 'episodes').mkdir()
        (path / 'characters').mkdir()
        (path / 'locations').mkdir()
        atomic_json(path / 'story.json', {'title': title.strip(), 'premise': premise.strip(), 'format_version': 1})
        documents = {
            'series_bible.md': f'# {title.strip()}\n\n## Premise\n\n{premise.strip()}\n\n## Genre and tone\n\n## Series arc\n',
            'character_bible.md': '# Character bible\n\nRecord names, appearance, relationships, motivations and reusable art paths.\n',
            'location_bible.md': '# Location bible\n\nRecord locations, recurring details and background art paths.\n',
            'continuity_log.md': '# Continuity log\n\nRecord established facts and unresolved threads after each episode.\n',
        }
        for name, text in documents.items():
            atomic_text(path / name, text)
        return path

    def create_episode(self, story: Path, title: str = '') -> Episode:
        numbers = [int(match[1]) for path in (story / 'episodes').glob('episode_*')
                   if (match := re.fullmatch(r'episode_(\d+)', path.name))]
        number = max(numbers, default=0) + 1
        directory = story / 'episodes' / f'episode_{number:03}'
        directory.mkdir(parents=True)
        (directory / 'assets').mkdir()
        existing = self.episodes(story)
        previous = load_episode(existing[-1]) if existing else None
        episode = Episode(directory.name, title.strip() or f'Episode {number:03}', directory,
                          (Scene(1, 6.0, 'assets/scene_001.png', '', 'slow_zoom_in', 'cinematic'),),
                          {}, {'number': number, 'hook': '', 'cliffhanger': '',
                               'previous_episode': previous.episode_id if previous else None,
                               'previous_recap': previous.metadata.get('cliffhanger', previous.scenes[-1].narration) if previous else ''})
        from .series_tools import apply_style
        episode = apply_style(episode, self.story_title(story))
        save_episode(episode)
        atomic_text(directory / 'script.md', f'# {episode.title}\n\n## Scene 1\n\n')
        self.write_outline(episode)
        self.refresh_continuity(episode)
        return episode

    def refresh_continuity(self, episode: Episode):
        story = episode.directory.parent.parent
        content = '# Previous episode continuity\n\n'
        prior = [p for p in self.episodes(story) if p.parent.name < episode.episode_id]
        if prior:
            previous = load_episode(prior[-1])
            content += f'## {previous.episode_id}: {previous.title}\n\n'
            content += f'Cliffhanger: {previous.metadata.get("cliffhanger", "")}\n\n'
            content += '\n\n'.join(s.narration for s in previous.scenes if s.narration)
        else:
            content += 'This is the first episode.\n'
        continuity = story / 'continuity_log.md'
        if continuity.is_file():
            content += '\n\n## Series continuity log\n\n' + continuity.read_text(encoding='utf-8')
        from .series_tools import continuity_notes
        content += continuity_notes(episode)
        atomic_text(episode.directory / 'continuity_context.md', content)

    def write_outline(self, episode: Episode):
        text = f'# {episode.title}\n\nEpisode: {episode.episode_id}\n\n'
        text += f'## Hook\n\n{episode.metadata.get("hook", "")}\n\n'
        text += f'## Cliffhanger\n\n{episode.metadata.get("cliffhanger", "")}\n\n'
        text += f'Previous episode: {episode.metadata.get("previous_episode") or "None"}\n'
        atomic_text(episode.directory / 'episode_outline.md', text)
        breakdown = '# Scene breakdown\n\n'
        for timed in episode.timeline():
            scene = timed.scene
            breakdown += f'## Scene {scene.scene_id} · {timed.start_seconds:.2f}–{timed.end_seconds:.2f}s\n\nVisual: {scene.visual_asset}\n\nMotion: {scene.camera_motion}; transition: {scene.transition}\n\n{scene.narration}\n\n'
        atomic_text(episode.directory / 'scene_breakdown.md', breakdown.rstrip() + '\n')

    def import_asset(self, episode: Episode, source: str | Path, *, category: str = 'episode') -> str:
        source = Path(source).resolve()
        if not source.is_file():
            raise FileNotFoundError(f'Cannot import missing file: {source}')
        if category not in ('episode', 'characters', 'backgrounds', 'music', 'sound_effects'):
            raise ValueError('Unknown asset category')
        destination = episode.directory / 'assets' if category == 'episode' else self.root / 'assets' / category
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / source.name
        if target.resolve() == source:
            return Path(os.path.relpath(source, episode.directory)).as_posix()
        if target.exists():
            digest = hashlib.sha256(source.read_bytes()).hexdigest()[:10]
            target = destination / f'{source.stem}-{digest}{source.suffix}'
        if not target.exists():
            fd, temporary = tempfile.mkstemp(prefix='.import-', dir=destination)
            os.close(fd)
            try:
                shutil.copyfile(source, temporary)
                os.replace(temporary, target)
            finally:
                Path(temporary).unlink(missing_ok=True)
        return Path(os.path.relpath(target, episode.directory)).as_posix()

    def breakdown_script(self, episode: Episode, script: str) -> Episode:
        """Deterministic editorial scaffolding from user-written paragraphs/headings."""
        if re.search(r'^##\s+Scene\b', script, re.MULTILINE | re.IGNORECASE):
            pieces = re.split(r'^##\s+Scene[^\n]*\n', script, flags=re.MULTILINE | re.IGNORECASE)[1:]
        else:
            cleaned = '\n'.join(line for line in script.splitlines() if not line.lstrip().startswith('#'))
            pieces = re.split(r'\n\s*\n', cleaned)
        pieces = [re.sub(r'^#+[^\n]*\n?', '', p, flags=re.MULTILINE).strip() for p in pieces]
        pieces = [p for p in pieces if p]
        if not pieces:
            raise ValueError('Write at least one scene paragraph or use ## Scene headings.')
        scenes = []
        fps = episode.settings.get('fps', 30)
        for index, narration in enumerate(pieces):
            duration = math.ceil(max(3, len(narration.split()) / 2.3) * fps) / fps
            existing = episode.scenes[index] if index < len(episode.scenes) else None
            scenes.append(Scene(index+1, duration, existing.visual_asset if existing else f'assets/scene_{index+1:03}.png',
                                narration, existing.camera_motion if existing else 'slow_zoom_in', 'cinematic',
                                transition=existing.transition if existing else 'crossfade',
                                foreground_asset=existing.foreground_asset if existing else None,
                                characters=existing.characters if existing else (),
                                location=existing.location if existing else None,
                                media_type=existing.media_type if existing else 'image',
                                video_start_seconds=existing.video_start_seconds if existing else 0,
                                video_audio_volume=existing.video_audio_volume if existing else 0))
        metadata = dict(episode.metadata)
        metadata['hook'] = re.split(r'(?<=[.!?])\s+', pieces[0])[0]
        metadata['cliffhanger'] = re.split(r'(?<=[.!?])\s+', pieces[-1])[-1]
        updated = replace(episode, scenes=tuple(scenes), metadata=metadata,
                          settings={**episode.settings, 'subtitle_mode': 'auto',
                                    'narration_asset': 'narration_required.wav'})
        save_episode(updated)
        atomic_text(episode.directory / 'script.md', script)
        self.write_outline(updated)
        self.refresh_continuity(updated)
        return updated


def fit_scene_to_audio(episode: Episode, index: int) -> Episode:
    scene = episode.scenes[index]
    if not scene.narration_audio:
        raise ValueError('Import or create a separate recording for this scene first.')
    fps = episode.settings.get('fps', 30)
    duration = math.ceil((audio_duration(episode.resolve_asset(scene.narration_audio)) + .2) * fps) / fps
    scenes = list(episode.scenes)
    scenes[index] = replace(scene, duration_seconds=duration)
    return replace(episode, scenes=tuple(scenes))


def fit_episode_to_target(episode: Episode) -> Episode:
    from .settings import settings_for, card_durations
    settings = settings_for(episode)
    title, end = card_durations(settings)
    fps = settings['fps']
    frames = round((settings['target_duration'] - title - end) * fps)
    minimums = []
    for scene in episode.scenes:
        if scene.narration.strip() and not scene.narration_audio:
            raise ValueError('Fit to target requires separate scene recordings so narration stays synchronized. Split or re-record the episode track first.')
        length = audio_duration(episode.resolve_asset(scene.narration_audio)) + .2 if scene.narration_audio else 1.0
        minimums.append(math.ceil(length * fps))
    remaining = frames - sum(minimums)
    if remaining < 0:
        required = sum(minimums) / fps + title + end
        raise ValueError(f'The narration needs at least {required:.2f}s including cards. Increase the target or shorten/re-record the text.')
    scenes = [replace(scene, duration_seconds=(minimums[index] + remaining // len(minimums) + (index < remaining % len(minimums))) / fps)
              for index, scene in enumerate(episode.scenes)]
    return replace(episode, scenes=tuple(scenes))
