"""Check the local runtime and the codecs/filters the studio actually uses."""
import json
import platform
import sys

from .media import tool, run
from .audio_manager import installed_voices


def check_environment():
    import PIL
    import PySide6
    filters = run([tool('ffmpeg'), '-hide_banner', '-filters'])
    encoders = run([tool('ffmpeg'), '-hide_banner', '-encoders'])
    required = ['zoompan', 'overlay', 'fade', 'ass', 'loudnorm', 'sidechaincompress', 'alimiter', 'amix']
    missing = [name for name in required if not any(name == line.split()[1] for line in filters.splitlines() if len(line.split()) >= 2)]
    for name in ('libx264', 'aac'):
        if not any(name == line.split()[1] for line in encoders.splitlines() if len(line.split()) >= 2):
            missing.append(name)
    if missing:
        raise RuntimeError('FFmpeg build is missing: ' + ', '.join(missing))
    return {'python': sys.version.split()[0], 'platform': platform.platform(), 'pillow': PIL.__version__,
            'pyside6': PySide6.__version__, 'ffmpeg': run([tool('ffmpeg'), '-version']).splitlines()[0],
            'ffprobe': run([tool('ffprobe'), '-version']).splitlines()[0],
            'required_media_features': 'available', 'local_voices': installed_voices(),
            'recorded_narration_fallback': 'supported'}


def main():
    try:
        print(json.dumps(check_environment(), indent=2))
    except Exception as error:
        print(f'Environment check failed: {error}', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
