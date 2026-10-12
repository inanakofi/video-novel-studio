"""Locate moved exports and detect changes to all of their source inputs."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path, PurePosixPath

from .render_cache import digest
from .scene_builder import load_episode
from .settings import settings_for


def export_source(report, workspace: Path) -> Path:
    source = report['source']
    if not isinstance(source, str) or not source:
        raise ValueError('Export report needs a source path.')
    # Resolve the stable workspace layout before consulting the original path:
    # the original checkout may still exist after this copy has been edited.
    parts = PurePosixPath(source.replace('\\', '/')).parts
    if len(parts) >= 5 and parts[-5] == 'stories' and parts[-3] == 'episodes' and parts[-1] == 'scenes.json':
        candidate = workspace.joinpath(*parts[-5:]).resolve()
        if candidate.is_relative_to(workspace.resolve()) and candidate.is_file():
            return candidate
    return Path(source)


@lru_cache(maxsize=512)
def _cached_digest(path, size, modified_ns, changed_ns):
    return digest(Path(path))


def source_inputs_sha256(source: Path, *, cached=False) -> str:
    """Content signature independent of the workspace's absolute location.

    UI checks reuse hashes only while the path, size and timestamps match.
    Rendering always hashes inputs freshly, before and after producing the MP4.
    """
    episode = load_episode(source)
    settings = settings_for(episode)
    assets = {s.visual_asset for s in episode.scenes}
    assets.update(s.foreground_asset for s in episode.scenes if s.foreground_asset)
    assets.update(s.narration_audio or settings['narration_asset'] for s in episode.scenes
                  if s.narration.strip() or s.narration_audio)
    if settings['music_asset']:
        assets.add(settings['music_asset'])
    assets.update(effect['asset'] for effect in settings['sound_effects'])
    paths = {'project': Path(source).resolve()}
    paths.update({'asset:' + name: episode.resolve_asset(name) for name in assets})
    if settings['subtitle_mode'] == 'manual':
        paths['captions'] = episode.directory / 'subtitles.srt'
    checksums = {}
    for name, path in paths.items():
        if cached:
            stat = path.stat()
            checksums[name] = _cached_digest(str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        else:
            checksums[name] = digest(path)
    return hashlib.sha256(json.dumps(checksums, sort_keys=True).encode()).hexdigest()


def export_changed(report, workspace: Path) -> bool:
    try:
        source = export_source(report, workspace)
        if report.get('source_inputs_sha256'):
            return source_inputs_sha256(source, cached=True) != report['source_inputs_sha256']
        # Historical reports contain only the scene-file checksum.
        return digest(source) != report.get('source_sha256')
    except (OSError, ValueError, KeyError, TypeError):
        return True
