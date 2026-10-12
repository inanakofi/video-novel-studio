"""Regression coverage for project review findings."""
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.scene_builder import episode_to_dict, load_episode, save_episode
from src.story_manager import StoryLibrary


class ProjectRegressionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='VNS review ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.library = StoryLibrary(self.root)
        self.episode = self.library.create_episode(self.library.create_story('Review'))

    def test_script_rebuild_detaches_previous_recordings_and_manual_captions(self):
        episode = replace(self.episode, settings={'narration_asset': 'old.wav', 'subtitle_mode': 'manual'},
                          scenes=(replace(self.episode.scenes[0], narration_audio='scene.wav'),))
        old_audio = episode.directory / 'old.wav'
        old_audio.write_bytes(b'original recording')
        updated = self.library.breakdown_script(episode, 'Completely new dialogue.')
        self.assertIsNone(updated.scenes[0].narration_audio)
        self.assertNotEqual(updated.settings['narration_asset'], 'old.wav')
        self.assertEqual(updated.settings['subtitle_mode'], 'auto')
        self.assertEqual(old_audio.read_bytes(), b'original recording')

    def test_invalid_sound_effects_are_rejected_before_loading_the_editor(self):
        for effect in (None, {}, {'asset': 42, 'start_seconds': 0, 'volume': .2},
                       {'asset': '', 'start_seconds': 0, 'volume': .2},
                       {'asset': 'fx.wav', 'start_seconds': -1, 'volume': .2},
                       {'asset': 'fx.wav', 'start_seconds': True, 'volume': .2},
                       {'asset': 'fx.wav', 'start_seconds': 0, 'volume': float('nan')},
                       {'asset': 'fx.wav', 'start_seconds': 0, 'volume': 2}):
            with self.subTest(effect=effect):
                data = episode_to_dict(self.episode)
                data['settings'] = {'sound_effects': [effect]}
                path = self.episode.directory / 'invalid.json'
                path.write_text(json.dumps(data), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'sound_effects'):
                    load_episode(path)

    def test_documented_schema_accepts_saved_video_scenes(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('jsonschema is provided by optional MCP dependencies')
        schema = json.loads((Path(__file__).resolve().parents[1] / 'templates/scenes.schema.json').read_text(encoding='utf-8'))
        episode = replace(self.episode, scenes=(replace(self.episode.scenes[0],
            media_type='video', camera_motion='static', visual_asset='clip.mp4',
            video_start_seconds=.5, video_audio_volume=.2),))
        data = json.loads(json.dumps(episode_to_dict(episode)))
        Draft202012Validator(schema).validate(data)

    def test_asset_checked_render_plan_accepts_silent_scenes(self):
        from src.video_renderer import build_render_plan
        episode = self.episode
        visual = episode.resolve_asset(episode.scenes[0].visual_asset)
        visual.parent.mkdir(exist_ok=True)
        visual.touch()
        plan = build_render_plan(episode, check_assets=True)
        self.assertIsNone(plan['scenes'][0]['narration_audio'])

    def test_asset_checked_render_plan_checks_foreground_layers(self):
        from src.video_renderer import build_render_plan
        episode = replace(self.episode, scenes=(replace(self.episode.scenes[0],
            camera_motion='parallax', foreground_asset='missing-layer.png'),))
        visual = episode.resolve_asset(episode.scenes[0].visual_asset)
        visual.parent.mkdir(exist_ok=True)
        visual.touch()
        with self.assertRaisesRegex(FileNotFoundError, 'missing-layer'):
            build_render_plan(episode, check_assets=True)


@unittest.skipUnless(os.environ.get('VNS_GUI_TESTS') == '1', 'Set VNS_GUI_TESTS=1 for editor regressions')
class EditorRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from src.app import StudioWindow
        temporary = tempfile.TemporaryDirectory(prefix='VNS editor review ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        library = StoryLibrary(self.root)
        episode = library.create_episode(library.create_story('Review'))
        self.episode = replace(episode, settings={'fps': 25},
            scenes=(replace(episode.scenes[0], narration='', subtitle='A silent caption.'),))
        save_episode(self.episode)
        with patch('src.app.installed_voices', return_value=[]):
            self.window = StudioWindow(self.root)
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window.captions_dirty = False
        self.window.episode = None
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_open_and_save_preserves_non_preset_frame_rate(self):
        self.assertEqual(self.window.fps_combo.currentText(), '25')
        self.assertTrue(self.window.save_all(quiet=True))
        self.assertEqual(load_episode(self.episode.directory / 'scenes.json').settings['fps'], 25)

    def test_generate_captions_recovers_from_invalid_unsaved_timings(self):
        window = self.window
        window.caption_table.item(0, 0).setText('not a time')
        self.assertTrue(window.captions_dirty)
        window.subtitle_mode.setCurrentText('manual')
        window.title_edit.setText('Repaired captions')
        window.generate_captions()
        self.assertFalse(window.captions_dirty, window.last_error)
        self.assertEqual(window.subtitle_mode.currentText(), 'auto')
        self.assertEqual(float(window.caption_table.item(0, 0).text()), 0)
        saved = load_episode(self.episode.directory / 'scenes.json')
        self.assertEqual(saved.title, 'Repaired captions')
        self.assertEqual(saved.settings['subtitle_mode'], 'auto')

    def test_timeline_plays_paired_export_after_workspace_move(self):
        window = self.window
        self.assertTrue(window.save_all(quiet=True))
        output = self.root / 'exports' / 'custom-name.mp4'
        output.touch()
        report = {'source': 'Z:/old/workspace/stories/review/episodes/episode_001/scenes.json',
                  'output': 'Z:/old/workspace/exports/custom-name.mp4', 'verified': True,
                  'source_sha256': 'previous version', 'width': 360, 'height': 640,
                  'fps': 25, 'video_duration_seconds': 6}
        output.with_suffix('.verification.json').write_text(json.dumps(report), encoding='utf-8')
        with patch.object(window, 'play_export') as play:
            window.timeline_play_video()
        play.assert_called_once_with(output)
        self.assertIn('changed', window.timeline_video_note.text().lower())
        window.refresh_exports()
        self.assertIn('changed', window.export_table.item(0, 3).text().lower())

    def test_valid_nonobject_session_state_does_not_crash_startup(self):
        from src.app import StudioWindow
        (self.root / '.studio_state.json').write_text('[]', encoding='utf-8')
        with patch('src.app.installed_voices', return_value=[]):
            other = StudioWindow(self.root)
        try:
            self.assertIsNotNone(other.episode)
        finally:
            other.close()
            other.deleteLater()
            self.app.processEvents()

    def test_empty_exception_is_reported_without_a_second_exception(self):
        window = self.window
        def fail():
            raise ValueError()
        window._guard(fail)
        self.assertTrue(window.last_error)


if __name__ == '__main__':
    unittest.main()
