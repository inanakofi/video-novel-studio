"""Bounded, content-addressed local shot cache. Final exports are still verified."""
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from .media import atomic_json, run, tool


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


@lru_cache(maxsize=1)
def renderer_version():
    directory = Path(__file__).parent
    return {'code': [digest(directory / name) for name in ('video_renderer.py', 'visuals.py')],
            'ffmpeg': run([tool('ffmpeg'), '-version']).splitlines()[0]}


def shot_key(source, duration, motion, settings, previous=None, transition='cut',
             transition_seconds=.5, foreground=None, *, media_type='image', video_start_seconds=0):
    data = {'version': renderer_version(), 'image': digest(source),
            'duration': duration, 'motion': motion, 'transition': transition,
            'fade': transition_seconds,
            'media_type': media_type, 'video_start_seconds': video_start_seconds,
            'previous': digest(previous) if previous and transition == 'crossfade' else None,
            'foreground': digest(foreground) if foreground else None,
            'settings': {k: settings[k] for k in ('width', 'height', 'fps', 'preset', 'crf')}}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


class ShotCache:
    def __init__(self, root: Path, budget=1024 ** 3):
        self.root = root
        self.budget = budget
        root.mkdir(parents=True, exist_ok=True)

    def restore(self, key: str, output: Path) -> bool:
        video, manifest = self.root / f'{key}.mp4', self.root / f'{key}.json'
        frame = self.root / f'{key}.png'
        try:
            record = json.loads(manifest.read_text(encoding='utf-8'))
            if record['sha256'] != digest(video) or record['frame_sha256'] != digest(frame):
                return False
            shutil.copyfile(video, output)
            shutil.copyfile(frame, output.with_suffix('.last.png'))
            video.touch()
            return True
        except (OSError, ValueError, KeyError):
            return False

    def store(self, key: str, source: Path):
        # Cache writes are optional; a full disk/locked cache must not invalidate
        # an otherwise valid export. No partial entry ever counts as a hit.
        temporary = frame_temp = None
        try:
            fd, name = tempfile.mkstemp(prefix='.shot-', suffix='.mp4', dir=self.root)
            os.close(fd)
            temporary = Path(name)
            shutil.copyfile(source, temporary)
            checksum = digest(temporary)
            fd, name = tempfile.mkstemp(prefix='.shot-', suffix='.png', dir=self.root)
            os.close(fd)
            frame_temp = Path(name)
            shutil.copyfile(source.with_suffix('.last.png'), frame_temp)
            frame_checksum = digest(frame_temp)
            os.replace(temporary, self.root / f'{key}.mp4')
            os.replace(frame_temp, self.root / f'{key}.png')
            atomic_json(self.root / f'{key}.json', {'sha256': checksum, 'frame_sha256': frame_checksum})
            self.prune()
        except OSError:
            pass
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
            if frame_temp:
                frame_temp.unlink(missing_ok=True)

    def prune(self):
        # Only our exact SHA-256 filenames; never recurse or follow arbitrary paths.
        entries = [p for p in self.root.glob('*.mp4')
                   if len(p.stem) == 64 and all(c in '0123456789abcdef' for c in p.stem)]
        entries.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        total = 0
        for path in entries:
            total += path.stat().st_size
            frame = path.with_suffix('.png')
            if frame.is_file():
                total += frame.stat().st_size
            if total > self.budget:
                try:
                    path.unlink(missing_ok=True)
                    path.with_suffix('.json').unlink(missing_ok=True)
                    frame.unlink(missing_ok=True)
                except OSError:
                    pass
