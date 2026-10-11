"""Real desktop actions against protocol fixtures; no live AI claim."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from test_connections import ProviderFixture


@unittest.skipUnless(os.environ.get('VNS_GUI_TESTS') == '1', 'Set VNS_GUI_TESTS=1 for desktop workflow')
class ConnectionDesktopTests(unittest.TestCase):
    def test_openrouter_review_apply_video_import_offline_render_and_reopen(self):
        from PySide6.QtCore import Qt, QUrl
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from src.app import StudioWindow
        from src.connections.config import ConnectionStore
        from src.scene_builder import load_episode
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        with tempfile.TemporaryDirectory(prefix='VNS UI connections été ') as folder:
            root = Path(folder)
            server = ProviderFixture(root)
            window = StudioWindow(root / 'workspace')
            window.show()
            window.audio_output.setVolume(0)
            def wait():
                deadline = time.monotonic() + 60
                while window._thread is not None and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.02)
                self.assertIsNone(window._thread)
                self.assertFalse(window.last_error, window.last_error)
            try:
                story = window.library.create_story('OpenRouter UI test')
                episode = window.library.create_episode(story)
                window.refresh_library()
                window.load_project(episode.directory / 'scenes.json')
                before = (episode.directory / 'scenes.json').read_bytes()
                window.tabs.setCurrentIndex(8)
                window.provider_picker.setCurrentIndex(window.provider_picker.findData('openrouter'))
                QTest.mouseClick(window.add_connection_button, Qt.MouseButton.LeftButton)
                window.connection_url.setText(server.url)
                window.connection_enabled.setChecked(True)
                window.connection_mode.setCurrentIndex(window.connection_mode.findData('local'))
                QTest.mouseClick(window.test_connection_button, Qt.MouseButton.LeftButton)
                wait()
                self.assertGreater(window.connection_model.count(), 0)
                window.connection_model.setCurrentText('fixture/model')
                QTest.mouseClick(window.save_connection_button, Qt.MouseButton.LeftButton)
                window.connection_pages.setCurrentIndex(1)
                window.generation_kind.setCurrentText('script')
                window.generation_instruction.setPlainText('Write the gate scene.')
                QTest.mouseClick(window.prepare_prompt_button, Qt.MouseButton.LeftButton)
                self.assertIn('scenes', window.generation_prompt.toPlainText())
                QTest.mouseClick(window.generate_ai_button, Qt.MouseButton.LeftButton)
                wait()
                self.assertEqual(window.review_job['status'], 'ready')
                self.assertEqual(window.episode.title, episode.title)
                QTest.mouseClick(window.apply_generation_button, Qt.MouseButton.LeftButton)
                self.assertFalse(window.last_error, window.last_error)
                self.assertEqual(window.episode.title, 'Ama returns')
                self.assertTrue(list((episode.directory / 'drafts').glob('before_apply_*/scenes.json')))
                window.tabs.setCurrentIndex(0)
                clip = root / 'fixture.mp4'
                with patch('src.app.QFileDialog.getOpenFileName', return_value=(str(clip), '')):
                    QTest.mouseClick(window.import_image_button, Qt.MouseButton.LeftButton)
                self.assertEqual(window.media_type_combo.currentText(), 'video')
                window.duration_spin.setValue(.8)
                window.narration_text.clear()
                window.caption_default.setChecked(False)
                window.caption_text.setPlainText('A locally rendered video clip.')
                window.save_all()
                window.tabs.setCurrentIndex(8)
                window.connection_mode.setCurrentIndex(window.connection_mode.findData('disabled'))
                QTest.mouseClick(window.save_mode_button, Qt.MouseButton.LeftButton)
                count = len(server.calls)
                # Enforce no Python network access during the ordinary offline render.
                with patch('socket.create_connection', side_effect=AssertionError('Offline render attempted network')):
                    window.start_render(preview=True)
                    wait()
                self.assertTrue(window.last_report['verified'])
                self.assertEqual(len(server.calls), count)
                window.player.setSource(QUrl())
                window.close()
                app.processEvents()
                window = StudioWindow(root / 'workspace')
                self.assertEqual(window.connection_mode.currentData(), 'disabled')
                self.assertEqual(len(window.generation_service.list_jobs()), 1)
                self.assertEqual(window.connection_profiles[0].provider, 'openrouter')
                window._refresh_generation_jobs(window.generation_service.list_jobs()[0]['id'])
                self.assertIn('Ama returns', window.generation_result.toPlainText())
            finally:
                if window._thread is not None:
                    window._cancel.set()
                    wait()
                window.close()
                app.processEvents()
                server.close()
