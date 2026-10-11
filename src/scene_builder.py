"""Load and validate episode scenes and calculate their playback timeline."""

from dataclasses import dataclass, field, asdict
import json
import math
from pathlib import Path
from typing import Any


CAMERA_MOTIONS = frozenset(
    {"static", "slow_zoom_in", "slow_zoom_out", "pan_left", "pan_right", "parallax"}
)
SUBTITLE_STYLES = frozenset({"cinematic", "standard"})
SCENE_FIELDS = frozenset(
    {
        "scene_id", "duration_seconds", "visual_asset", "narration",
        "camera_motion", "subtitle_style",
    }
)


@dataclass(frozen=True)
class Scene:
    scene_id: int
    duration_seconds: float
    visual_asset: str
    narration: str
    camera_motion: str
    subtitle_style: str
    narration_audio: str | None = None
    subtitle: str | None = None
    transition: str = "cut"
    transition_seconds: float = 0.5
    foreground_asset: str | None = None
    characters: tuple[str, ...] = ()
    location: str | None = None
    media_type: str = 'image'
    video_start_seconds: float = 0.0
    video_audio_volume: float = 0.0

    @property
    def subtitle_text(self) -> str:
        return self.narration if self.subtitle is None else self.subtitle


@dataclass(frozen=True)
class TimedScene:
    scene: Scene
    start_seconds: float
    end_seconds: float


@dataclass(frozen=True)
class Episode:
    episode_id: str
    title: str
    directory: Path
    scenes: tuple[Scene, ...]
    settings: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def timeline(self) -> tuple[TimedScene, ...]:
        """Play scenes in array order, with no gaps between scenes."""
        result = []
        start = 0.0
        for scene in self.scenes:
            end = start + scene.duration_seconds
            if not math.isfinite(end):
                raise ValueError("Total episode duration must be finite")
            result.append(TimedScene(scene, start, end))
            start = end
        return tuple(result)

    def resolve_asset(self, relative_path: str) -> Path:
        """Resolve an asset relative to the directory containing scenes.json."""
        return (self.directory / relative_path).resolve()


def _text(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{label} must be {'a string' if allow_empty else 'a non-empty string'}")
    return value


def _asset(value: Any, label: str) -> str:
    value = _text(value, label)
    if Path(value).is_absolute() or Path(value).drive:
        raise ValueError(f"{label} must be a relative asset path")
    return value


def load_episode(scenes_path: str | Path) -> Episode:
    """Read scenes.json; invalid data raises ValueError with a field location.

    Asset existence is checked separately when preparing a render plan.
    """
    path = Path(scenes_path).resolve()
    with path.open(encoding="utf-8") as source:
        data = json.load(source)
    if not isinstance(data, dict):
        raise ValueError("Episode data must be an object")
    expected = {"episode_id", "title", "scenes"}
    if not expected.issubset(data) or data.keys() - (expected | {"settings", "metadata"}):
        raise ValueError("Episode data requires episode_id, title, scenes; optional settings and metadata")
    if not isinstance(data.get('settings', {}), dict) or not isinstance(data.get('metadata', {}), dict):
        raise ValueError('settings and metadata must be objects')
    episode_id = _text(data["episode_id"], "episode_id")
    title = _text(data["title"], "title")
    records = data["scenes"]
    if not isinstance(records, list) or not records:
        raise ValueError("scenes must be a non-empty array")

    scenes = []
    ids = set()
    for index, record in enumerate(records):
        label = f"scenes[{index}]"
        if not isinstance(record, dict):
            raise ValueError(f"{label} must be an object")
        missing = SCENE_FIELDS - record.keys()
        if missing:
            raise ValueError(f"{label} is missing: {', '.join(sorted(missing))}")
        unknown = record.keys() - (SCENE_FIELDS | {"narration_audio", "subtitle", "transition", "transition_seconds", "foreground_asset", "characters", "location", "media_type", "video_start_seconds", "video_audio_volume"})
        if unknown:
            raise ValueError(f"{label} has unknown fields: {', '.join(sorted(unknown))}")
        scene_id = record["scene_id"]
        if type(scene_id) is not int or scene_id < 1:
            raise ValueError(f"{label}.scene_id must be a positive integer")
        if scene_id in ids:
            raise ValueError(f"{label}.scene_id duplicates scene {scene_id}")
        ids.add(scene_id)

        duration = record["duration_seconds"]
        if type(duration) not in (int, float):
            raise ValueError(f"{label}.duration_seconds must be a positive finite number")
        try:
            duration = float(duration)
        except OverflowError as error:
            raise ValueError(f"{label}.duration_seconds must be finite") from error
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError(f"{label}.duration_seconds must be a positive finite number")

        motion = _text(record["camera_motion"], f"{label}.camera_motion")
        style = _text(record["subtitle_style"], f"{label}.subtitle_style")
        if motion not in CAMERA_MOTIONS:
            raise ValueError(f"{label}.camera_motion must be one of {', '.join(sorted(CAMERA_MOTIONS))}")
        if style not in SUBTITLE_STYLES:
            raise ValueError(f"{label}.subtitle_style must be one of {', '.join(sorted(SUBTITLE_STYLES))}")
        transition = record.get('transition', 'cut')
        if transition not in ('cut', 'crossfade', 'fade_black'):
            raise ValueError(f'{label}.transition must be cut, crossfade, or fade_black')
        transition_seconds = record.get('transition_seconds', 0.5)
        if type(transition_seconds) not in (int, float) or not math.isfinite(transition_seconds) or transition_seconds <= 0:
            raise ValueError(f'{label}.transition_seconds must be positive and finite')
        foreground = record.get('foreground_asset')
        if foreground is not None:
            foreground = _asset(foreground, f'{label}.foreground_asset')
        if motion == 'parallax' and not foreground:
            raise ValueError(f'{label}: parallax requires a transparent foreground_asset')
        characters = record.get('characters', [])
        if not isinstance(characters, list) or any(not isinstance(c, str) or not c.strip() for c in characters):
            raise ValueError(f'{label}.characters must be a list of nonempty character IDs')
        if len(set(characters)) != len(characters):
            raise ValueError(f'{label}.characters must not contain duplicate IDs')
        location = record.get('location')
        if location is not None:
            location = _text(location, f'{label}.location')

        media_type = record.get('media_type', 'image')
        if media_type not in ('image', 'video'):
            raise ValueError(f'{label}.media_type must be image or video')
        start = record.get('video_start_seconds', 0)
        volume = record.get('video_audio_volume', 0)
        for key, value, maximum in (('video_start_seconds', start, 86400), ('video_audio_volume', volume, 1)):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= maximum:
                raise ValueError(f'{label}.{key} must be between 0 and {maximum}')
        if media_type == 'video' and (motion != 'static' or foreground):
            raise ValueError(f'{label}: video scenes use static camera motion and no foreground layer')

        scenes.append(Scene(
            scene_id=scene_id,
            duration_seconds=duration,
            visual_asset=_asset(record["visual_asset"], f"{label}.visual_asset"),
            narration=_text(record["narration"], f"{label}.narration", allow_empty=True),
            camera_motion=motion,
            subtitle_style=style,
            narration_audio=(
                _asset(record["narration_audio"], f"{label}.narration_audio")
                if "narration_audio" in record else None
            ),
            subtitle=(
                _text(record["subtitle"], f"{label}.subtitle", allow_empty=True)
                if "subtitle" in record else None
            ),
            transition=transition,
            transition_seconds=float(transition_seconds),
            foreground_asset=foreground,
            characters=tuple(characters), location=location,
            media_type=media_type, video_start_seconds=float(start), video_audio_volume=float(volume),
        ))

    episode = Episode(episode_id, title, path.parent, tuple(scenes), data.get('settings', {}), data.get('metadata', {}))
    episode.timeline()
    from .settings import settings_for
    settings_for(episode)
    return episode


def episode_to_dict(episode: Episode) -> dict:
    return {'episode_id': episode.episode_id, 'title': episode.title,
            'scenes': [{k: v for k, v in asdict(scene).items() if v is not None} for scene in episode.scenes],
            'settings': episode.settings, 'metadata': episode.metadata}


def save_episode(episode: Episode, path: str | Path | None = None) -> None:
    from .media import atomic_json
    destination = Path(path) if path else episode.directory / 'scenes.json'
    data = episode_to_dict(episode)
    # Validate a sibling staging file before replacing a user's saved project.
    import tempfile
    import os
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.validate-', suffix='.json', dir=destination.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, allow_nan=False)
        load_episode(name)
        atomic_json(destination, data)
    finally:
        Path(name).unlink(missing_ok=True)
