"""Contrast, appearance persistence and the native job-details lifecycle."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.theme import THEMES


def contrast(foreground, background):
    def luminance(color):
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        channels = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
        return sum(c * weight for c, weight in zip(channels, (.2126, .7152, .0722)))
    low, high = sorted((luminance(foreground), luminance(background)))
    return (high + .05) / (low + .05)


class ThemeContrastTests(unittest.TestCase):
    def test_readable_text_controls_and_timeline_categories_in_both_themes(self):
        for theme, colors in THEMES.items():
            with self.subTest(theme=theme):
                for surface in ('canvas', 'surface'):
                    for text in ('text', 'muted', 'accent', 'warning', 'danger'):
                        self.assertGreaterEqual(contrast(colors[text], colors[surface]), 4.5,
                                                f'{theme}: {text} on {surface}')
                    self.assertGreaterEqual(contrast(colors['control_border'], colors[surface]), 3)
                for action in ('accent', 'accent_hover', 'accent_pressed'):
                    self.assertGreaterEqual(contrast(colors['on_accent'], colors[action]), 4.5)
                self.assertGreaterEqual(contrast(colors['selection_text'], colors['selection']), 4.5)
                for key in colors:
                    if key.startswith('track_') and key != 'track_text':
                        self.assertGreaterEqual(contrast(colors['track_text'], colors[key]), 4.5,
                                                f'{theme}: {key} label')


@unittest.skipUnless(os.environ.get('VNS_GUI_TESTS') == '1', 'Set VNS_GUI_TESTS=1 for native appearance checks')
class AppearanceDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='VNS appearance ')
        self.root = Path(self.temporary.name)
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            if window._thread:
                window.cancel_job()
                self.wait_for(lambda target=window: target._thread is None)
            window.episode = None
            window.story = None
            window.close()
            window.deleteLater()
        self.app.processEvents()
        self.temporary.cleanup()

    def open_window(self):
        from src.app import StudioWindow
        with patch('src.app.installed_voices', return_value=[]):
            window = StudioWindow(self.root)
        self.windows.append(window)
        window.show()
        self.app.processEvents()
        return window

    def wait_for(self, predicate):
        from PySide6.QtTest import QTest
        deadline = time.monotonic() + 10
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), 'Native task did not reach the expected state')

    def test_theme_choice_survives_reopen_without_discarding_edits(self):
        from PySide6.QtGui import QPalette

        from src.scene_builder import load_episode
        from src.story_manager import StoryLibrary
        library = StoryLibrary(self.root)
        episode = library.create_episode(library.create_story('Appearance test'))
        window = self.open_window()
        window.narration_text.setPlainText('An unsaved scene edit must survive an appearance change.')
        window.theme_combo.setCurrentIndex(window.theme_combo.findData('dark'))
        self.assertEqual(window.narration_text.toPlainText(), 'An unsaved scene edit must survive an appearance change.')
        self.assertEqual(window.current_theme, 'dark')
        self.assertEqual(window.timeline.colors['surface'], THEMES['dark']['surface'])
        self.assertEqual(window.production_title.palette().color(QPalette.ColorRole.PlaceholderText).name(),
                         THEMES['dark']['muted'])
        state = json.loads(window.state_path.read_text(encoding='utf-8'))
        self.assertEqual(state['theme'], 'dark')
        self.assertEqual(Path(state['episode']), episode.directory / 'scenes.json')
        self.assertTrue(window.save_all(quiet=True), window.last_error)
        self.assertEqual(load_episode(episode.directory / 'scenes.json').scenes[0].narration,
                         window.narration_text.toPlainText())
        window.close()
        reopened = self.open_window()
        self.assertEqual(reopened.current_theme, 'dark')
        self.assertEqual(reopened.theme_combo.currentData(), 'dark')
        self.assertEqual(reopened.narration_text.toPlainText(), window.narration_text.toPlainText())

    def test_system_changes_follow_system_choice_and_respect_manual_choice(self):
        from PySide6.QtCore import Qt
        window = self.open_window()
        hints = SimpleNamespace(colorScheme=lambda: Qt.ColorScheme.Dark)
        with patch.object(window, '_style_hints', hints):
            window._system_theme_changed(Qt.ColorScheme.Dark)
            self.assertEqual(window.current_theme, 'dark')
            window.theme_combo.setCurrentIndex(window.theme_combo.findData('light'))
            window._system_theme_changed(Qt.ColorScheme.Dark)
            self.assertEqual(window.current_theme, 'light')
            window.theme_combo.setCurrentIndex(window.theme_combo.findData('system'))
            self.assertEqual(window.current_theme, 'dark')

    def test_bad_appearance_state_falls_back_without_blocking_startup(self):
        (self.root / '.studio_state.json').write_text(json.dumps({'theme': 'unknown-theme'}), encoding='utf-8')
        window = self.open_window()
        self.assertEqual(window.theme_preference, 'system')
        self.assertIn(window.current_theme, ('light', 'dark'))
        self.assertEqual(window.tabs.count(), 10)

    def test_media_controls_follow_scene_type_and_keep_hidden_values(self):
        window = self.open_window()
        self.assertTrue(window.video_start_spin.isHidden())
        window.media_type_combo.setCurrentText('video')
        self.assertFalse(window.video_start_spin.isHidden())
        self.assertFalse(window.fit_video_button.isHidden())
        window.video_start_spin.setValue(2.5)
        window.video_volume_spin.setValue(.4)
        window.media_type_combo.setCurrentText('image')
        self.assertTrue(window.video_start_spin.isHidden())
        self.assertTrue(window.fit_video_button.isHidden())
        window.media_type_combo.setCurrentText('video')
        self.assertEqual(window.video_start_spin.value(), 2.5)
        self.assertEqual(window.video_volume_spin.value(), .4)

    def test_artwork_keeps_its_aspect_and_fits_when_details_expand(self):
        from PySide6.QtGui import QColor, QPixmap
        window = self.open_window()
        image = QPixmap(360, 640)
        image.fill(QColor('#20735e'))
        window.image_preview.setPixmap(image)
        for size, details in (((1440, 900), False), ((1280, 800), True), ((1280, 800), False)):
            window.resize(*size)
            window.details_button.setChecked(details)
            self.app.processEvents()
            fitted = window.image_preview.pixmap()
            self.assertLessEqual(fitted.width(), window.image_preview.width())
            self.assertLessEqual(fitted.height(), window.image_preview.height())
            self.assertAlmostEqual(fitted.width() / fitted.height(), 360 / 640, delta=.005)

    def test_active_job_cancel_and_failure_details_remain_accessible(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPalette
        from PySide6.QtTest import QTest
        window = self.open_window()
        self.assertTrue(window.progress_bar.isHidden())
        self.assertTrue(window.cancel_button.isHidden())
        self.assertTrue(window.log.isHidden())

        def job(progress, cancel):
            progress(.35, 'Working on a test render')
            if not cancel.wait(5):
                raise RuntimeError('Cancellation was not delivered')
            return 'stopped'

        completed = []
        window._run_task(job, completed.append)
        self.wait_for(lambda: window.progress_bar.value() == 35)
        self.assertTrue(window.progress_bar.isVisible())
        self.assertTrue(window.cancel_button.isEnabled())
        self.assertEqual(window.progress_label.text(), '35%')
        QTest.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
        self.wait_for(lambda: window._thread is None)
        self.assertEqual(completed, ['stopped'])
        self.assertTrue(window.cancel_button.isHidden())
        self.assertTrue(window.progress_bar.isHidden())

        def fail(progress, cancel):
            raise ValueError('Simulated renderer failure: missing scene visual')

        window._run_task(fail, completed.append)
        self.wait_for(lambda: window._thread is None)
        self.assertIn('missing scene visual', window.status.text())
        self.assertEqual(window.status.property('tone'), 'error')
        self.assertEqual(window.status.palette().color(QPalette.ColorRole.WindowText).name(),
                         THEMES[window.current_theme]['danger'])
        self.assertTrue(window.details_button.isChecked())
        self.assertTrue(window.log.isVisible())
        self.assertIn('Simulated renderer failure', window.log.toPlainText())
        QTest.mouseClick(window.details_button, Qt.MouseButton.LeftButton)
        self.assertTrue(window.log.isHidden())
