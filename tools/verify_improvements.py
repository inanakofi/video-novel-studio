"""Run the upgraded desktop against the real 75-second sample, twice."""
import json
import argparse
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaPlayer
from src.app import StudioWindow
from src.media import atomic_json
from src.render_cache import digest


def wait_for(app, predicate, timeout=600):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise RuntimeError('Desktop verification timed out.')
        app.processEvents()
        time.sleep(.02)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--final-only', action='store_true', help='One verified rerender after a caption/UI refinement')
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    source = ROOT / 'stories/the_letter_at_the_gate/episodes/episode_001/scenes.json'
    window = StudioWindow(ROOT)
    window.show()
    window.load_project(source)
    window.audio_output.setVolume(0)
    window.narration_output.setVolume(0)
    assert window.save_all(quiet=True), window.last_error
    timings, reports = [], []
    def task_done():
        wait_for(app, lambda: window._thread is None)
        assert not window.last_error, window.last_error
    for attempt in ((1,) if args.final_only else (1, 2)):
        started = time.monotonic()
        window.start_render()
        task_done()
        seconds = time.monotonic() - started
        timings.append(seconds)
        report = window.last_report
        assert report and report['verified'] and report['full_decode'] == 'passed'
        assert (report['width'], report['height'], report['fps']) == (1080, 1920, 30)
        assert report['video_duration_seconds'] == report['audio_end_seconds'] == 75
        assert report['subtitle_end_seconds'] <= 75
        assert digest(source) == report['source_sha256']
        assert digest(Path(report['output'])) == report['output_sha256']
        reports.append({key: value for key, value in report.items() if key != 'ffprobe'})
        print(json.dumps({'render': attempt, 'seconds': seconds, 'cache': report['scene_cache']}, ensure_ascii=False), flush=True)
    assert reports[-1]['scene_cache']['hits'] == 5
    window.tabs.setCurrentIndex(4)
    window.load_waveform()
    task_done()
    assert window.wave_data and max(window.wave_data['peaks']) > .01
    window.timeline_zoom.setValue(20)
    window.timeline_play_video()
    wait_for(app, lambda: window.player.position() > 100 and window.timeline_video.last_image is not None, 20)
    window.player.setPosition(10000)
    wait_for(app, lambda: 10000 <= window.player.position() < 11000, 20)
    # Wait for a decoded frame at the seek position, not only the clock change.
    frames = []
    window.video_widget.videoSink().videoFrameChanged.connect(lambda f: frames.append(f.startTime()/1e6) if f.isValid() else None)
    wait_for(app, lambda: frames and 10 <= frames[-1] < 12, 20)
    window.player.pause()
    assert window.player.error() == QMediaPlayer.Error.NoError, window.player.errorString()
    evidence = ROOT / 'verification'
    window.grab().save(str(evidence / 'timeline-production.png'))
    window.tabs.setCurrentIndex(7)
    window.run_publishing_check()
    task_done()
    assert window.publish_report['ready']
    window.grab().save(str(evidence / 'publishing-production.png'))
    summary = {'render_seconds': timings, 'exports': reports,
               'waveform_seconds': window.wave_data['duration'],
               'actual_player_frame_seconds': frames[-1], 'player_error': None,
               'publishing': window.publish_report,
               'note': 'Real 1080p desktop renders, real PCM waveform, actual player decoding; playback muted in automation.'}
    atomic_json(evidence / 'improvements-production.json', summary)
    window.close()
    app.processEvents()
    print(json.dumps({key: value for key, value in summary.items() if key != 'exports'}, indent=2), flush=True)


if __name__ == '__main__':
    main()
