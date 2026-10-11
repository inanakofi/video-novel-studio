"""Local media tools, cancellation, probing and verified export publication."""
from __future__ import annotations

from fractions import Fraction
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
from typing import Callable


class MediaError(RuntimeError):
    pass


class RenderCancelled(MediaError):
    pass


def tool(name: str) -> str:
    override = os.environ.get(f'VNS_{name.upper()}')
    found = shutil.which(override or name)
    if not found:
        raise MediaError(f'{name} was not found. Install FFmpeg and FFprobe, add their bin folder to PATH, then restart the studio.')
    return found


def run(command: list[str], *, cwd: Path | None = None,
        cancel: threading.Event | None = None, progress: Callable[[float], None] | None = None,
        duration: float = 0) -> str:
    """Run argument lists without a shell; drain pipes and poll cancellation."""
    if cancel and cancel.is_set():
        raise RenderCancelled('Render cancelled.')
    with tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=errors, text=True,
                                encoding='utf-8', errors='replace',
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        lines: queue.Queue[str | None] = queue.Queue()

        def read():
            assert proc.stdout is not None
            for line in proc.stdout:
                lines.put(line)
            lines.put(None)

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        output = []
        try:
            while True:
                if cancel and cancel.is_set():
                    raise RenderCancelled('Render cancelled; the previous export was preserved.')
                try:
                    line = lines.get(timeout=0.1)
                except queue.Empty:
                    continue
                if line is None:
                    break
                output.append(line)
                if progress and duration and line.startswith('out_time_us='):
                    try:
                        progress(min(1.0, max(0.0, int(line.split('=', 1)[1]) / 1_000_000 / duration)))
                    except ValueError:
                        pass
            code = proc.wait()
            if cancel and cancel.is_set():
                raise RenderCancelled('Render cancelled.')
            if code:
                errors.seek(0)
                detail = errors.read().decode('utf-8', 'replace')[-8000:]
                raise MediaError(f'{Path(command[0]).name} failed (exit {code}):\n{detail}')
            return ''.join(output)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            reader.join(timeout=2)
            if proc.stdout:
                proc.stdout.close()


def ffmpeg(args: list[str], **kwargs) -> str:
    return run([tool('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin',
                '-y', '-threads', '2', '-filter_threads', '2', '-filter_complex_threads', '2',
                '-progress', 'pipe:1', '-nostats', *args], **kwargs)


def probe(path: str | Path) -> dict:
    path = Path(path).resolve()
    if not path.is_file():
        raise MediaError(f'Missing media file: {path}')
    return json.loads(run([tool('ffprobe'), '-v', 'error', '-show_streams', '-show_format',
                           '-of', 'json', str(path)]))


def audio_duration(path: str | Path) -> float:
    info = probe(path)
    streams = [s for s in info['streams'] if s['codec_type'] == 'audio']
    if not streams:
        raise MediaError(f'No audio stream in {path}')
    duration = float(streams[0].get('duration') or info['format'].get('duration') or 0)
    if duration <= 0:
        raise MediaError(f'Cannot determine audio duration: {path}')
    return duration


def verify_export(path: str | Path, *, width: int, height: int, fps: int,
                  duration: float, subtitle_end: float = 0,
                  cancel: threading.Event | None = None) -> dict:
    info = probe(path)
    video = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    audio = next((s for s in info['streams'] if s['codec_type'] == 'audio'), None)
    if not video or not audio:
        raise MediaError('Export must contain both video and audio streams.')
    problems = []
    if video['codec_name'] != 'h264' or audio['codec_name'] != 'aac':
        problems.append('expected H.264 video and AAC audio')
    if (video['width'], video['height']) != (width, height):
        problems.append('wrong video resolution')
    if abs(float(Fraction(video['avg_frame_rate'])) - fps) > 0.01:
        problems.append('wrong frame rate')
    if video.get('pix_fmt') != 'yuv420p':
        problems.append('expected compatible yuv420p pixel format')
    video_duration = float(video.get('duration') or info['format']['duration'])
    audio_end = float(audio.get('start_time', 0)) + float(audio.get('duration', 0))
    if abs(video_duration - duration) > max(0.1, 2 / fps):
        problems.append(f'video duration {video_duration:.3f}s differs from planned {duration:.3f}s')
    if audio_end > video_duration + 0.06:
        problems.append('audio exceeds video duration')
    if audio_end < video_duration - 0.06:
        problems.append('audio track ends before the planned video timeline')
    if subtitle_end > min(video_duration, audio_end) + 0.002:
        problems.append('subtitles exceed video or audio duration')
    if problems:
        raise MediaError('Export verification failed: ' + '; '.join(problems))
    ffmpeg(['-xerror', '-i', str(Path(path).resolve()), '-map', '0:v:0', '-map', '0:a:0',
            '-f', 'null', '-'], cancel=cancel)
    return {'verified': True, 'width': width, 'height': height, 'fps': fps,
            'video_codec': video['codec_name'], 'audio_codec': audio['codec_name'],
            'video_duration_seconds': video_duration, 'audio_end_seconds': audio_end,
            'subtitle_end_seconds': subtitle_end, 'full_decode': 'passed', 'ffprobe': info}


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.save-', suffix='.json', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
