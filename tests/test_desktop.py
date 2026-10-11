"""Exercise actual desktop widgets, real file imports, encoding and playback.

Enable with VNS_GUI_TESTS=1 in a desktop session. File picker decisions are supplied
by the test; media operations, worker threads, codecs and player are all real.
"""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.environ.get('VNS_GUI_TESTS') == '1', 'Set VNS_GUI_TESTS=1 to exercise desktop widgets and playback')
class DesktopWorkflowTests(unittest.TestCase):
    def test_export_list_uses_moved_workspace_files(self):
        import json
        import shutil
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from src.app import StudioWindow
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        original = Path(__file__).resolve().parents[1] / 'exports/connections_and_video_demo_episode_001.mp4'
        with tempfile.TemporaryDirectory(prefix='Moved Studio workspace ') as folder:
            root = Path(folder)
            (root / 'exports').mkdir()
            moved = root / 'exports' / original.name
            shutil.copyfile(original, moved)
            report = json.loads(original.with_suffix('.verification.json').read_text(encoding='utf-8'))
            report['output'] = str(original)
            moved.with_suffix('.verification.json').write_text(json.dumps(report), encoding='utf-8')
            window = StudioWindow(root)
            try:
                self.assertEqual(window.export_table.rowCount(), 1)
                listed = Path(window.export_table.item(0, 0).data(Qt.ItemDataRole.UserRole))
                self.assertEqual(listed, moved)
                self.assertNotEqual(listed, original)
            finally:
                window.close()
                window.deleteLater()
                app.processEvents()

    def test_create_import_edit_caption_render_play_and_reopen(self):
        import faulthandler
        faulthandler.dump_traceback_later(25, repeat=True)
        self.addCleanup(faulthandler.cancel_dump_traceback_later)
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from PySide6.QtMultimedia import QMediaPlayer
        from src.app import StudioWindow
        from src.scene_builder import load_episode

        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        temporary = tempfile.TemporaryDirectory(prefix='Desktop été ')
        root = Path(temporary.name)
        sample_path = Path(__file__).resolve().parents[1] / 'stories' / 'studio_prototype' / 'episodes' / 'episode_001' / 'scenes.json'
        source = load_episode(sample_path)
        window = StudioWindow(root / 'workspace')
        window.show()
        window.audio_output.setVolume(0)
        QTest.qWait(150)
        try:
            with patch('src.app.QInputDialog.getText', return_value=('Été studio workflow', True)):
                QTest.mouseClick(window.new_story_button, Qt.MouseButton.LeftButton)
            self.assertIsNotNone(window.episode, window.last_error)
            for index in range(3):
                if index:
                    QTest.mouseClick(window.add_scene_button, Qt.MouseButton.LeftButton)
                window.narration_text.setPlainText(source.scenes[index].narration)
                visual = source.resolve_asset(source.scenes[index].visual_asset)
                audio = source.resolve_asset(source.scenes[index].narration_audio)
                with patch('src.app.QFileDialog.getOpenFileName', return_value=(str(visual), '')):
                    QTest.mouseClick(window.import_image_button, Qt.MouseButton.LeftButton)
                with patch('src.app.QFileDialog.getOpenFileName', return_value=(str(audio), '')):
                    QTest.mouseClick(window.import_audio_button, Qt.MouseButton.LeftButton)
            self.assertEqual(len(window.episode.scenes), 3)
            before = [s.scene_id for s in window.episode.scenes]
            QTest.mouseClick(window.up_button, Qt.MouseButton.LeftButton)
            self.assertEqual([s.scene_id for s in window.episode.scenes], [before[0], before[2], before[1]])
            QTest.mouseClick(window.down_button, Qt.MouseButton.LeftButton)
            window.tabs.setCurrentIndex(4)
            QTest.mouseClick(window.generate_captions_button, Qt.MouseButton.LeftButton)
            self.assertGreaterEqual(window.caption_table.rowCount(), 3, window.last_error)
            window.caption_table.item(0, 2).setText('Edited mobile caption.')
            corrected_end = float(window.caption_table.item(0, 1).text()) - .05
            window.caption_table.item(0, 1).setText(f'{corrected_end:.3f}')
            QTest.mouseClick(window.save_captions_button, Qt.MouseButton.LeftButton)
            self.assertEqual(window.subtitle_mode.currentText(), 'manual', window.last_error)
            source_path = window.episode.directory / 'scenes.json'
            self.assertEqual(load_episode(source_path).settings['subtitle_mode'], 'manual')
            window.tabs.setCurrentIndex(0)
            decoded_frames = []
            window.video_widget.videoSink().videoFrameChanged.connect(lambda frame: decoded_frames.append(frame.isValid()))
            QTest.mouseClick(window.preview_button, Qt.MouseButton.LeftButton)
            deadline = time.monotonic() + 90
            while window._thread is not None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.02)
            self.assertIsNone(window._thread, 'Render worker did not finish')
            self.assertIsNotNone(window.last_report, window.last_error)
            self.assertTrue(window.last_report['verified'])
            QTest.qWait(900)
            self.assertEqual(window.player.error(), QMediaPlayer.Error.NoError, window.player.errorString())
            self.assertGreater(window.player.position(), 0)
            self.assertTrue(any(decoded_frames), 'The actual player did not decode any video frames')
            self.assertIsNotNone(window.video_widget.last_image, 'Player frames were not displayed in the preview')
            self.assertGreater(window.export_table.rowCount(), 0)
            evidence = Path(__file__).resolve().parents[1] / 'verification'
            evidence.mkdir(exist_ok=True)
            window.grab().save(str(evidence / 'desktop-workflow.png'))
            import json
            (evidence / 'desktop-workflow.json').write_text(json.dumps({
                'created_story': True, 'imported_three_images_and_recordings': True,
                'reordered_scenes': True, 'manual_captions_saved': True,
                'render_verified': True, 'real_player_decoded_frames': sum(decoded_frames),
                'player_position_ms': window.player.position(),
                'report': {k: v for k, v in window.last_report.items() if k != 'ffprobe'},
                'test_assets': 'Original local illustrations and actual imported Windows offline-voice WAV narration from the supplied prototype.'
            }, indent=2), encoding='utf-8')
            window.player.stop()
            window.close()
            QTest.qWait(150)
            reopened = StudioWindow(root / 'workspace')
            self.assertEqual(reopened.episode.directory / 'scenes.json', source_path)
            self.assertEqual(len(reopened.episode.scenes), 3)
            self.assertEqual(reopened.caption_table.item(0, 2).text(), 'Edited mobile caption.')
            self.assertAlmostEqual(float(reopened.caption_table.item(0, 1).text()), corrected_end, places=3)
            reopened.close()
            reopened.deleteLater()
        finally:
            if window._thread:
                window.cancel_job()
                deadline = time.monotonic() + 10
                while window._thread and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.02)
            window.player.stop()
            window.close()
            window.deleteLater()
            QTest.qWait(200)
            temporary.cleanup()

    def test_installed_voice_button_creates_a_real_recording(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt
        from src.app import StudioWindow
        from src.media import audio_duration
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        with tempfile.TemporaryDirectory(prefix='Local voice UI ') as temporary:
            window = StudioWindow(Path(temporary))
            if not window.voices:
                window.close()
                self.skipTest('No installed Windows speech voice; recorded import is the supported fallback')
            window.show()
            with patch('src.app.QInputDialog.getText', return_value=('Offline voice test', True)):
                QTest.mouseClick(window.new_story_button, Qt.MouseButton.LeftButton)
            window.narration_text.setPlainText('This narration was created by an installed offline voice.')
            QTest.mouseClick(window.tts_button, Qt.MouseButton.LeftButton)
            deadline = time.monotonic() + 30
            while window._thread and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.02)
            self.assertIsNone(window._thread, 'Local voice task did not finish')
            scene = window.episode.scenes[0]
            self.assertIsNotNone(scene.narration_audio, window.last_error)
            length = audio_duration(window.episode.resolve_asset(scene.narration_audio))
            self.assertGreater(length, 1)
            self.assertGreaterEqual(scene.duration_seconds, length)
            window.close()
            window.deleteLater()
            QTest.qWait(100)


if __name__ == '__main__':
    unittest.main()
