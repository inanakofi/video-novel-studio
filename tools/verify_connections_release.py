"""Verify a real, offline, 1080p mixed-media sample through the desktop app."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication
from src.app import StudioWindow
from src.connections.config import Connection, ConnectionStore, PRESETS
from src.media import ffmpeg, atomic_json
from src.render_cache import digest
from src.scene_builder import load_episode, save_episode
from src.story_manager import StoryLibrary, atomic_text
from src.video_renderer import _segment
from src.settings import settings_for


def sample():
    path = ROOT / 'stories/connections_and_video_demo/episodes/episode_001/scenes.json'
    if path.is_file():
        return path
    library = StoryLibrary(ROOT)
    original = load_episode(ROOT / 'stories/the_letter_at_the_gate/episodes/episode_001/scenes.json')
    story = library.create_story('Connections and Video Demo', 'A 75-second offline sample with a video clip, still images and installed Windows narration.')
    episode = library.create_episode(story, 'The Letter at the Gate — mixed media')
    scenes = []
    for scene in original.scenes:
        scenes.append(replace(scene, visual_asset=library.import_asset(episode, original.resolve_asset(scene.visual_asset)),
                              narration_audio=library.import_asset(episode, original.resolve_asset(scene.narration_audio)),
                              foreground_asset=library.import_asset(episode, original.resolve_asset(scene.foreground_asset)) if scene.foreground_asset else None))
    settings = dict(original.settings)
    settings['music_asset'] = library.import_asset(episode, original.resolve_asset(settings['music_asset']))
    settings['sound_effects'] = [{**effect, 'asset': library.import_asset(episode, original.resolve_asset(effect['asset']))} for effect in settings['sound_effects']]
    clip = episode.directory / 'assets/Courtyard motion — été.mp4'
    shot = scenes[1]
    video_settings = {**settings_for(original), 'width': 720, 'height': 1280}
    _segment(episode.resolve_asset(shot.visual_asset), clip, shot.duration_seconds + 1, 'pan_right', video_settings, episode.directory)
    scenes[1] = replace(shot, visual_asset='assets/' + clip.name, media_type='video', camera_motion='static', video_start_seconds=.5)
    episode = replace(episode, scenes=tuple(scenes), settings=settings,
                      metadata={**original.metadata, 'sample_visuals': 'Original CC0 illustrations; middle clip animated locally with FFmpeg. No AI image/video generation.'})
    save_episode(episode)
    atomic_text(episode.directory / 'script.md', (original.directory / 'script.md').read_text(encoding='utf-8'))
    atomic_text(episode.directory / 'ASSET_ORIGIN.md', '# Sample asset origin\n\nArtwork and writing reuse the original CC0 Studio sample. '
                'The courtyard video is an FFmpeg animation of that artwork, not an AI generation. '
                'Narration is the installed Microsoft David Desktop voice, generated offline; it is not a human recording. '
                'Music and effects are the Studio sample procedural audio. See the workspace sample asset licence.\n')
    library.write_outline(episode)
    library.refresh_continuity(episode)
    return episode.directory / 'scenes.json'


def main():
    source = sample()
    store = ConnectionStore(ROOT)
    if not store.path.exists():
        store.save('disabled', [Connection.preset(provider) for provider in PRESETS])
    evidence = ROOT / 'exports/verification'
    evidence.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = StudioWindow(ROOT)
    window.show()
    window.audio_output.setVolume(0)
    window.load_project(source)
    def wait(predicate, timeout=600):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > deadline:
                raise RuntimeError('Release desktop verification timed out')
            app.processEvents()
            time.sleep(.02)
    try:
        with patch('socket.create_connection', side_effect=AssertionError('Offline production attempted Python network access')):
            started = time.monotonic()
            window.start_render()
            wait(lambda: window._thread is None)
        assert not window.last_error, window.last_error
        report = window.last_report
        assert report['verified'] and report['full_decode'] == 'passed'
        assert (report['width'], report['height'], report['fps']) == (1080, 1920, 30)
        assert abs(report['video_duration_seconds'] - 75) < .001
        assert report['audio_end_seconds'] <= 75.06 and report['subtitle_end_seconds'] <= 75
        assert digest(source) == report['source_sha256']
        assert digest(Path(report['output'])) == report['output_sha256']
        print(json.dumps({'render_seconds': time.monotonic()-started, 'verified': True, 'output': report['output']}, ensure_ascii=False), flush=True)
        window.play_export(Path(report['output']))
        wait(lambda: window.player.position() > 100 and window.video_widget.last_image is not None)
        frames = []
        window.video_widget.videoSink().videoFrameChanged.connect(lambda frame: frames.append(frame.startTime()/1e6) if frame.isValid() else None)
        for seconds in (8, 33, 60, 74):
            window.player.setPosition(seconds * 1000)
            wait(lambda: frames and abs(frames[-1] - seconds) < .75, timeout=20)
        window.player.pause()
        window.grab().save(str(evidence / 'connections-mixed-video-playback.png'))
        window.tabs.setCurrentIndex(8)
        window.connection_pages.setCurrentIndex(0)
        app.processEvents()
        window.grab().save(str(evidence / 'connections-settings.png'))
        window.connection_pages.setCurrentIndex(1)
        window.generation_kind.setCurrentText('script')
        window.generation_instruction.setPlainText('Draft the next episode. Ama must decide whether to open the garden door.')
        window.context_continuity.setChecked(True)
        window._prepare_generation_prompt()
        app.processEvents()
        window.grab().save(str(evidence / 'connections-prompt-review.png'))
        atomic_json(evidence / 'connections-release.json', {
            'version': '1.2.0', 'export': {k: v for k, v in report.items() if k != 'ffprobe'},
            'player_frames_seconds': frames[-12:], 'player_error': window.player.errorString(),
            'offline_mode': store.load()[0], 'network_calls': 'Python socket.create_connection blocked during desktop render',
            'cloud_generation': 'Not tested: no provider credentials supplied',
            'local_ai_generation': 'Not tested: no Ollama/ComfyUI model service installed',
            'sample_clip': 'Locally animated original CC0 artwork; not AI-generated',
        })
        print('Playback verified at 8, 33, 60 and 74 seconds; connection screenshots saved.', flush=True)
    finally:
        window.player.stop()
        window.player.setSource(QUrl())
        window.close()
        app.processEvents()


if __name__ == '__main__':
    main()
