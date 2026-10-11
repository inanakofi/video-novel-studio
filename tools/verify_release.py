"""Capture local environment, real sample playback and audio measurements."""
from pathlib import Path
import array
import hashlib
import json
import math
import sys
import tempfile
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaPlayer
from src.app import StudioWindow
from src.doctor import check_environment
from src.media import ffmpeg, atomic_json
from src.scene_builder import load_episode
from src.subtitle_generator import parse_srt


def wait_for(app, condition, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(.01)
    raise RuntimeError('Timed out waiting for actual media playback.')


def main():
    evidence = ROOT / 'verification'
    evidence.mkdir(exist_ok=True)
    output = ROOT / 'exports' / 'the_letter_at_the_gate_episode_001.mp4'
    if not output.is_file():
        output = ROOT / 'exports' / 'The Letter at the Gate - Episode 001.mp4'
    source = ROOT / 'stories' / 'the_letter_at_the_gate' / 'episodes' / 'episode_001' / 'scenes.json'
    report = json.loads(output.with_suffix('.verification.json').read_text(encoding='utf-8'))
    assert report['verified'] and report['full_decode'] == 'passed'
    assert report['output_sha256'] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert report['source_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert (report['width'], report['height'], report['fps']) == (1080, 1920, 30)
    assert report['video_duration_seconds'] == report['audio_end_seconds'] == 75.0
    cues = parse_srt(output.with_suffix('.srt').read_text(encoding='utf-8'))
    assert len(cues) == report['caption_count']
    atomic_json(evidence / 'environment.json', check_environment())
    with tempfile.TemporaryDirectory(prefix='vns-audio-verify-') as folder:
        pcm = Path(folder) / 'decoded.wav'
        ffmpeg(['-i', str(output), '-vn', '-ac', '1', '-ar', '48000', '-c:a', 'pcm_s16le', str(pcm)])
        with wave.open(str(pcm), 'rb') as recording:
            samples = array.array('h', recording.readframes(recording.getnframes()))
        peak = max(abs(sample) for sample in samples) / 32768
        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples)) / 32768
        assert .001 < rms < 1, 'Audio should be audible and nonempty'
        assert peak < .999, 'Decoded AAC audio must retain clipping headroom'
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = StudioWindow(ROOT)
    window.show()
    window.load_project(source)
    window.audio_output.setVolume(0)
    timestamps = []
    window.video_widget.videoSink().videoFrameChanged.connect(lambda frame: timestamps.append(frame.startTime() / 1000) if frame.isValid() else None)
    window.play_export(output)
    wait_for(app, lambda: window.player.position() > 100 and window.video_widget.last_image is not None)
    checkpoints = []
    for second in (10, 34, 60, 74):
        count = len(timestamps)
        window.player.setPosition(second * 1000)
        wait_for(app, lambda: len(timestamps) > count and abs(timestamps[-1] - second * 1000) < 350)
        window.player.pause()
        app.processEvents()
        assert window.player.error() == QMediaPlayer.Error.NoError, window.player.errorString()
        frame = evidence / f'playback-{second:02}s.png'
        assert window.video_widget.last_image.save(str(frame))
        checkpoints.append({'requested_seconds': second, 'decoded_frame_seconds': timestamps[-1] / 1000, 'image': frame.name})
        if second == 34:
            window.grab().save(str(evidence / 'desktop-final.png'))
        window.player.play()
    summary = {'player': 'PySide6 QMediaPlayer with QVideoSink', 'playback_error': None,
               'decoded_frames_observed': len(timestamps), 'checkpoints': checkpoints,
               'duration_seconds': window.player.duration() / 1000,
               'decoded_audio_peak': peak, 'decoded_audio_rms': rms,
               'subtitle_count': len(cues), 'subtitle_end_seconds': max(cue.end for cue in cues),
               'output_sha256': report['output_sha256'], 'note': 'Playback muted during automated checks; PCM measured from the actual AAC stream.'}
    atomic_json(evidence / 'sample-playback.json', summary)
    window.close()
    app.processEvents()
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
