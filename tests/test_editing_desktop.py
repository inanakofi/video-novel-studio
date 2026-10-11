"""Actual timeline gestures, local audio playback and series controls."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from test_media_pipeline import fixture
from src.scene_builder import save_episode, load_episode


@unittest.skipUnless(os.environ.get('VNS_GUI_TESTS') == '1', 'Set VNS_GUI_TESTS=1 for native desktop checks')
class EditingDesktopTests(unittest.TestCase):
    def test_waveform_drag_audition_series_continuity_and_publishing(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from PySide6.QtMultimedia import QMediaPlayer
        from src.app import StudioWindow
        from src.subtitle_generator import parse_srt

        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        temporary = tempfile.TemporaryDirectory(prefix='Timeline été ')
        root = Path(temporary.name)
        episode = fixture(root / 'stories' / 'serial' / 'episodes' / 'episode_001')
        save_episode(episode)
        window = StudioWindow(root)
        window.show()
        window.narration_output.setVolume(0)
        window.audio_output.setVolume(0)

        def wait_task():
            deadline = time.monotonic() + 60
            while window._thread and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.02)
            self.assertIsNone(window._thread, 'Background job did not finish')
            self.assertFalse(window.last_error, window.last_error)

        def drag(kind, index, shift):
            block = next(b for b in window.timeline.blocks if b['kind'] == kind and b['index'] == index)
            start = QPoint(round(block['rect'].right()-3), round(block['rect'].center().y()))
            finish = QPoint(start.x()+shift, start.y())
            QTest.mousePress(window.timeline, Qt.MouseButton.LeftButton, pos=start)
            QTest.mouseMove(window.timeline, finish, delay=20)
            QTest.mouseRelease(window.timeline, Qt.MouseButton.LeftButton, pos=finish)
            app.processEvents()

        try:
            window.tabs.setCurrentIndex(4)
            QTest.mouseClick(window.generate_captions_button, Qt.MouseButton.LeftButton)
            QTest.mouseClick(window.wave_button, Qt.MouseButton.LeftButton)
            wait_task()
            self.assertIsNotNone(window.wave_data)
            self.assertGreater(max(window.wave_data['peaks']), .01)
            window.timeline_zoom.setValue(100)
            QTest.qWait(150)
            self.assertGreaterEqual(window.timeline_scroll.viewport().height(), 237, 'Caption track must fit visibly')
            before = float(window.caption_table.item(0, 1).text())
            drag('caption', 0, -12)
            self.assertAlmostEqual(float(window.caption_table.item(0, 1).text()), before-.12, places=2)
            self.assertEqual(window.subtitle_mode.currentText(), 'manual', window.last_error)
            saved_cues = parse_srt((episode.directory / 'subtitles.srt').read_text(encoding='utf-8'))
            self.assertAlmostEqual(saved_cues[0].end, before-.12, places=2)
            start_later = float(window.caption_table.item(1, 0).text())
            drag('scene', 0, 30)
            self.assertAlmostEqual(window.episode.scenes[0].duration_seconds, 1.1, places=3)
            self.assertAlmostEqual(float(window.caption_table.item(1, 0).text()), start_later+.3, places=3)
            self.assertIsNone(window.wave_data, 'A timing change must invalidate the loaded waveform')
            QTest.mouseClick(window.wave_button, Qt.MouseButton.LeftButton)
            wait_task()
            QTest.qWait(150)
            window.timeline_seek(.5)
            QTest.mouseClick(window.listen_button, Qt.MouseButton.LeftButton)
            QTest.qWait(300)
            self.assertEqual(window.narration_player.error(), QMediaPlayer.Error.NoError)
            self.assertGreater(window.narration_player.position(), 500)
            window.narration_player.pause()

            window.tabs.setCurrentIndex(6)
            series_tabs = window.tabs.widget(6)
            series_tabs.setCurrentIndex(1)
            window._add_continuity_row('characters', {'id': 'ama', 'name': 'Ama', 'notes': 'Keeps the letter.'})
            window._add_continuity_row('locations', {'id': 'gate', 'name': 'Gate', 'notes': 'Northern entrance.'})
            window._add_continuity_row('threads', {'id': 'letter', 'name': 'Who sent it?', 'status': 'open',
                'opened_episode': 'episode_001', 'resolved_episode': '', 'notes': 'Blue wax seal.'})
            QTest.mouseClick(window.save_continuity_button, Qt.MouseButton.LeftButton)
            self.assertFalse(window.last_error, window.last_error)
            window.tabs.setCurrentIndex(0)
            window.scene_characters.item(0).setCheckState(Qt.CheckState.Checked)
            window.scene_location.setCurrentIndex(1)
            window.save_all()
            window.refresh_continuity()
            self.assertEqual(window.episode.scenes[0].characters, ('ama',))
            self.assertIn('Who sent it?', window.continuity_preview.toPlainText())
            self.assertIn('Keeps the letter.', window.continuity_preview.toPlainText())

            window.tabs.setCurrentIndex(6)
            series_tabs.setCurrentIndex(0)
            window.settings_widgets['caption_color'].setText('#FFDDAA')
            window.title_template.setText('{series} / {episode}')
            QTest.mouseClick(window.save_style_button, Qt.MouseButton.LeftButton)
            self.assertTrue((window.story / 'style.json').is_file())
            first_path = window.episode.directory / 'scenes.json'
            window.new_episode()
            self.assertEqual(window.episode.episode_id, 'episode_002')
            self.assertEqual(window.settings_widgets['caption_color'].text(), '#FFDDAA')
            self.assertIn('/ 002', window.settings_widgets['title_card'].text())
            window.load_project(first_path)
            self.assertEqual(window.episode.scenes[0].location, 'gate')
            window.tabs.setCurrentIndex(7)
            QTest.mouseClick(window.publish_check_button, Qt.MouseButton.LeftButton)
            wait_task()
            self.assertTrue(window.publish_report['ready'])
            self.assertGreater(window.publish_table.rowCount(), 0)  # Deliberately short test duration.
            window.tabs.setCurrentIndex(4)
            QTest.mouseClick(window.wave_button, Qt.MouseButton.LeftButton)
            wait_task()
            window.timeline_zoom.setValue(100)
            evidence = Path(__file__).resolve().parents[1] / 'verification'
            window.grab().save(str(evidence / 'timeline-workflow.png'))
            (evidence / 'editing-workflow.json').write_text(json.dumps({
                'real_caption_edge_drag': True, 'scene_trim_ripple': True,
                'waveform_from_real_pcm': True, 'narration_playback': 'passed (muted automation)',
                'series_defaults_inherited': True, 'scene_continuity_saved': True,
                'publishing_check': window.publish_report,
            }, indent=2), encoding='utf-8')
        finally:
            if window._thread:
                window.cancel_job()
                wait_task()
            window.close()
            window.deleteLater()
            QTest.qWait(150)
            temporary.cleanup()


if __name__ == '__main__':
    unittest.main()
