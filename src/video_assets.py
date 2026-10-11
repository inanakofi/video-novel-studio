"""Local video validation and cached thumbnails; no integration dependencies."""
import hashlib
from pathlib import Path
from .media import probe, ffmpeg, MediaError


def video_info(path):
    data = probe(path)
    streams = [s for s in data['streams'] if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic')]
    if not streams:
        raise MediaError(f'No video track: {Path(path).name}')
    stream = streams[0]
    duration = float(stream.get('duration', data.get('format', {}).get('duration', 0)))
    if duration <= 0:
        raise MediaError(f'Cannot determine video duration: {Path(path).name}')
    return {'duration': duration, 'width': stream['width'], 'height': stream['height'],
            'has_audio': any(s.get('codec_type') == 'audio' for s in data['streams'])}


def visual_preview(episode, scene):
    source = episode.resolve_asset(scene.visual_asset)
    if scene.media_type != 'video' or not source.is_file():
        return source
    stat = source.stat()
    key = hashlib.sha256(f'{source}|{stat.st_size}|{stat.st_mtime_ns}|{scene.video_start_seconds}'.encode()).hexdigest()
    root = episode.directory / '.vns-cache' / 'thumbnails'
    root.mkdir(parents=True, exist_ok=True)
    output = root / (key + '.png')
    if not output.exists():
        ffmpeg(['-ss', str(scene.video_start_seconds), '-i', str(source), '-frames:v', '1',
                '-vf', 'scale=360:640:force_original_aspect_ratio=decrease', '-threads', '2', str(output)])
    return output
