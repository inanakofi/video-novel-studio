"""Scene media, hidden settings and sticky creation controls retain their behavior."""
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(os.environ.get('VNS_GUI_TESTS') == '1', 'Set VNS_GUI_TESTS=1 for native workspace checks')
class WorkspaceDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from src.scene_builder import save_episode
        from src.story_manager import StoryLibrary
        self.temporary = tempfile.TemporaryDirectory(prefix='VNS workspace polish ')
        self.root = Path(self.temporary.name)
        library = StoryLibrary(self.root)
        episode = library.create_episode(library.create_story('Workspace test'))
        self.image = episode.directory / 'assets' / 'scene.png'
        self.write_image(self.image, '#20735e')
        episode = replace(episode, scenes=(replace(episode.scenes[0], visual_asset='assets/scene.png',
                           narration='The letter arrives before sunrise.', camera_motion='slow_zoom_in',
                           transition='crossfade'),))
        save_episode(episode)
        from src.app import StudioWindow
        with patch('src.app.installed_voices', return_value=[]):
            self.window = StudioWindow(self.root)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.episode = None
        self.window.story = None
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temporary.cleanup()

    def write_image(self, path, color):
        from PySide6.QtGui import QColor, QImage
        path.parent.mkdir(parents=True, exist_ok=True)
        image = QImage(180, 320, QImage.Format.Format_RGB32)
        image.fill(QColor(color))
        self.assertTrue(image.save(str(path)))

    def test_hidden_scene_fields_save_canonical_motion_and_caption_values(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        from src.scene_builder import load_episode
        w = self.window
        timing = w.scene_sections['Timing']
        timing.toggle.setFocus()
        QTest.keyClick(timing.toggle, Qt.Key.Key_Space)
        self.assertTrue(timing.body.isVisible())
        w.motion_combo.setCurrentIndex(w.motion_combo.findData('pan_right'))
        self.assertEqual(w.motion_combo.currentText(), 'Pan right')
        w.transition_combo.setCurrentIndex(w.transition_combo.findData('fade_black'))
        w.caption_default.setChecked(False)
        w.caption_text.setPlainText('A different caption.')
        for section in w.scene_sections.values():
            section.set_expanded(False)
        self.assertTrue(w.save_all(quiet=True), w.last_error)
        scene = load_episode(w.episode.directory / 'scenes.json').scenes[0]
        self.assertEqual(scene.camera_motion, 'pan_right')
        self.assertEqual(scene.transition, 'fade_black')
        self.assertEqual(scene.subtitle, 'A different caption.')
        self.assertEqual(scene.narration, 'The letter arrives before sunrise.')

    def test_real_thumbnail_updates_when_an_asset_is_replaced(self):
        from PySide6.QtCore import Qt
        def center_color():
            icon = self.window.scene_list.item(0).data(Qt.ItemDataRole.DecorationRole)
            image = icon.pixmap(44, 68).toImage()
            return image.pixelColor(image.width() // 2, image.height() // 2).name()
        self.assertEqual(center_color(), '#20735e')
        stat = self.image.stat()
        self.write_image(self.image, '#94552e')
        os.utime(self.image, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000))
        self.window._refresh_scene_list(0)
        self.assertEqual(center_color(), '#94552e')
        self.assertIn('Scene 01', self.window.scene_list.item(0).text())

    def test_browsing_video_rows_uses_only_existing_thumbnail_cache(self):
        from src.video_assets import cached_visual_preview, visual_preview
        w = self.window
        clip = w.episode.directory / 'assets' / 'not-decoded.mp4'
        clip.write_bytes(b'Fixture placeholder: the scene list must never decode this file.')
        scene = replace(w.episode.scenes[0], visual_asset='assets/not-decoded.mp4',
                        media_type='video', camera_motion='static')
        w.episode = replace(w.episode, scenes=(scene,))
        with patch('src.video_assets.ffmpeg') as decoder:
            w._refresh_scene_list(0)
            self.assertIsNone(cached_visual_preview(w.episode, scene))
            decoder.assert_not_called()
        with patch('src.video_assets.ffmpeg', side_effect=lambda command: self.write_image(Path(command[-1]), '#38678c')):
            cached = visual_preview(w.episode, scene)
        self.assertEqual(cached_visual_preview(w.episode, scene), cached)
        self.assertFalse(w._scene_icon(scene).isNull())
        self.assertIsNone(cached_visual_preview(w.episode, replace(scene, video_start_seconds=1)))

    def test_output_groups_keep_settings_when_collapsed(self):
        from src.scene_builder import load_episode
        w = self.window
        w.settings_widgets['font_size'].setValue(68)
        w.settings_widgets['music_volume'].setValue(.27)
        for section in w.output_sections.values():
            section.set_expanded(False)
        self.assertTrue(w.save_all(quiet=True), w.last_error)
        settings = load_episode(w.episode.directory / 'scenes.json').settings
        self.assertEqual(settings['font_size'], 68)
        self.assertEqual(settings['music_volume'], .27)

    def test_create_videos_stays_visible_when_setup_scrolls(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QScrollArea
        w = self.window
        w.resize(1280, 800)
        w.tabs.setCurrentIndex(9)
        page = w.production_pages.widget(0)
        scroll = page.findChild(QScrollArea)
        self.app.processEvents()
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        self.app.processEvents()
        self.assertTrue(w.production_start.isVisible())
        origin = w.production_start.mapTo(page, QPoint(0, 0))
        self.assertGreaterEqual(origin.y(), 0)
        self.assertLessEqual(origin.y() + w.production_start.height(), page.height())
        self.assertEqual(len(w.production_models), 7)
        w.production_models['analysis'].setEditText('retained/model-id')
        w.production_sections['Task models'].set_expanded(False)
        w.production_sections['Task models'].set_expanded(True)
        self.assertEqual(w.production_models['analysis'].currentText(), 'retained/model-id')
        w.production_sections['Manuscript'].set_expanded(False)
        w.production_sections['Video format'].set_expanded(False)
        scroll.verticalScrollBar().setValue(0)
        self.app.processEvents()
        source_bottom = w.production_sections['Manuscript'].geometry().bottom()
        format_top = w.production_sections['Video format'].geometry().top()
        self.assertLess(format_top - source_bottom, 40, 'Collapsed sections must reclaim their vertical space')

    def test_missing_visual_and_tool_configuration_open_relevant_groups(self):
        w = self.window
        self.image.unlink()
        w._populate_scene(0)
        self.assertTrue(w.scene_sections['Visual'].toggle.isChecked())
        w.provider_picker.setCurrentIndex(w.provider_picker.findData('mcp_stdio'))
        w._add_connection()
        self.assertTrue(w.connection_sections['Advanced options'].toggle.isChecked())
        w.connection_options.setPlainText('{"command":"example"}')
        w.connection_sections['Advanced options'].set_expanded(False)
        self.assertEqual(w.connection_options.toPlainText(), '{"command":"example"}')
