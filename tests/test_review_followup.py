"""Behavioral regressions found during the full-project follow-up review."""
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from src.connections.config import Connection, ConnectionStore
from src.connections.generation import GenerationService
from src.media import atomic_json, MediaError, RenderCancelled
from src.production.manuscript import extract
from src.production.runner import ProductionRunner
from src.scene_builder import save_episode
from src.story_manager import StoryLibrary
from test_production import config, ProductionFixture
from test_media_pipeline import fixture


class ProductionReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='VNS review provider ')
        cls.server = ProductionFixture(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls):
        cls.server.close()
        cls.temporary.cleanup()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='VNS review run ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.server.calls.clear()
        self.server.cancel_after = None
        self.profile = self.server.configure(self.root)
        self.runner = ProductionRunner(self.root)
        self.source = self.root / 'source.txt'
        self.source.write_text('Ama finds a letter.', encoding='utf-8')

    def test_character_voice_is_validated_before_any_submission(self):
        for profile in (
            Connection('voice', 'Character voice', 'elevenlabs', self.server.url, enabled=True),
            Connection('voice', 'Character voice', 'http', self.server.url, enabled=True,
                       options={'production': {'voice': {'arguments': {}}}}),
        ):
            with self.subTest(provider=profile.provider):
                ConnectionStore(self.root).save('local', [self.profile, profile])
                options = config()
                options['speaker_routes'] = {'CHAR-001': profile.id}
                with self.assertRaises(ValueError):
                    self.runner.create(self.source, options)
                self.assertEqual(self.server.calls, [])
                self.assertEqual(self.runner.list_runs(), [])

    def test_http_response_survives_cancel_during_submission(self):
        from src.connections.transport import Transport
        state = self.runner.create(self.source, config())
        cancel = threading.Event()
        original = Transport._open

        def cancel_after_headers(transport, *args, **kwargs):
            response = original(transport, *args, **kwargs)
            cancel.set()
            return response

        with patch.object(Transport, '_open', cancel_after_headers):
            with self.assertRaises(RenderCancelled):
                self.runner.run(state['id'], cancel=cancel)
        saved = self.runner.load(state['id'])
        self.assertEqual(saved['stages']['analyse_SRC-0001']['status'], 'ready')
        cancel.clear()
        completed = self.runner.run(state['id'], cancel=cancel)
        self.assertEqual(completed['status'], 'complete')
        self.assertEqual(len([p for p, _ in self.server.calls if p == '/story']), 5)

    def test_run_reloads_state_after_acquiring_its_lock(self):
        state = self.runner.create(self.source, config())
        original_open = Path.open
        run_file = self.runner.runs / state['id'] / 'run.json'
        lock = run_file.with_name('running.lock')

        def finish_competing_worker(path, *args, **kwargs):
            if path == lock and args and args[0] == 'x':
                atomic_json(run_file, {**state, 'status': 'complete', 'current_stage': 'complete'})
            return original_open(path, *args, **kwargs)

        with patch.object(Path, 'open', finish_competing_worker):
            result = self.runner.run(state['id'])
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(self.server.calls, [])


class SavedDataReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='VNS saved data ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_invalid_connection_shapes_raise_actionable_validation_errors(self):
        for data in ([], None, {'version': 1, 'mode': 'local'},
                     {'version': 1, 'mode': 'local', 'connections': [None]}):
            with self.subTest(data=data):
                (self.root / '.studio_connections.json').write_text(json.dumps(data), encoding='utf-8')
                with self.assertRaises(ValueError):
                    ConnectionStore(self.root).load()

    def test_invalid_job_and_production_history_are_ignored(self):
        for data in ([], None, {'id': 'broken'}):
            with self.subTest(data=data):
                for folder, filename in (('.generation_jobs', 'job.json'), ('.production_runs', 'run.json')):
                    path = self.root / folder / 'broken' / filename
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(data), encoding='utf-8')
                self.assertEqual(GenerationService(self.root).list_jobs(), [])
                self.assertEqual(ProductionRunner(self.root).list_runs(), [])

    def test_docx_preserves_tabs_and_manual_line_breaks(self):
        path = self.root / 'dialogue.docx'
        xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
               '<w:body><w:p><w:r><w:t>Ama:</w:t><w:tab/><w:t>Come home.</w:t>'
               '<w:br/><w:t>Now.</w:t></w:r></w:p></w:body></w:document>')
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('word/document.xml', xml)
        self.assertEqual(extract(path), 'Ama:\tCome home.\nNow.')


class ExportReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='VNS export review ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.episode = fixture(self.root / 'stories/review/episodes/episode_001')
        self.episode = replace(self.episode, settings={**self.episode.settings, 'subtitle_mode': 'manual'})
        self.source = self.episode.directory / 'scenes.json'
        save_episode(self.episode)
        self.captions = self.episode.directory / 'subtitles.srt'
        self.captions.write_text('1\n00:00:00,400 --> 00:00:01,000\nOriginal caption\n', encoding='utf-8')

    def test_freshness_tracks_captions_and_all_media_after_workspace_move(self):
        from src.exports import export_changed, source_inputs_sha256
        from src.render_cache import digest
        report = {'source': str(self.source), 'source_sha256': digest(self.source),
                  'source_inputs_sha256': source_inputs_sha256(self.source)}
        moved = self.root / 'moved'
        shutil.copytree(self.root / 'stories', moved / 'stories')
        self.assertFalse(export_changed(report, moved))
        candidates = [self.captions, *(self.episode.resolve_asset(name) for name in
                      (self.episode.scenes[0].visual_asset, self.episode.scenes[0].narration_audio,
                       'layer.png', 'music.wav', 'effect.wav'))]
        for original in candidates:
            with self.subTest(asset=original.name):
                path = moved / original.relative_to(self.root)
                contents = path.read_bytes()
                path.write_bytes(contents + b'changed')
                self.assertTrue(export_changed(report, moved))
                path.write_bytes(contents)
                self.assertFalse(export_changed(report, moved))
        path.unlink()
        self.assertTrue(export_changed(report, moved))

    def test_render_records_inputs_and_preserves_export_if_source_changes(self):
        from src.exports import export_changed
        from src.video_renderer import render_episode
        output = self.root / 'exports/review.mp4'
        report = render_episode(self.source, output)
        self.assertIn('source_inputs_sha256', report)
        self.assertFalse(export_changed(report, self.root))
        previous = {p: p.read_bytes() for p in (output, output.with_suffix('.srt'), output.with_suffix('.verification.json'))}
        def change_caption(fraction, message):
            if fraction == .95:
                self.captions.write_text(self.captions.read_text(encoding='utf-8').replace('Original', 'Updated'), encoding='utf-8')
        with self.assertRaisesRegex(MediaError, 'changed during rendering'):
            render_episode(self.source, output, progress=change_caption)
        for path, contents in previous.items():
            self.assertEqual(path.read_bytes(), contents)
        self.assertTrue(export_changed(report, self.root))
        def change_project_at_start(fraction, message):
            if fraction == 0:
                save_episode(replace(self.episode, title='Changed after the renderer loaded the episode'))
        with self.assertRaisesRegex(MediaError, 'changed during rendering'):
            render_episode(self.source, output, progress=change_project_at_start)
        for path, contents in previous.items():
            self.assertEqual(path.read_bytes(), contents)


@unittest.skipUnless(os.environ.get('VNS_GUI_TESTS') == '1', 'Set VNS_GUI_TESTS=1 for editor review')
class DesktopReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='VNS desktop review ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.library = StoryLibrary(self.root)

    def open_window(self):
        from src.app import StudioWindow
        with patch('src.app.installed_voices', return_value=[]):
            window = StudioWindow(self.root)
        def close():
            window.episode = None
            window.story = None
            window.close()
            window.deleteLater()
            self.app.processEvents()
        self.addCleanup(close)
        return window

    def test_malformed_optional_metadata_does_not_prevent_offline_startup(self):
        self.library.create_episode(self.library.create_story('Healthy story'))
        broken_story = self.library.create_story('Z broken metadata')
        (broken_story / 'story.json').write_text('[]', encoding='utf-8')
        (self.root / '.studio_connections.json').write_text('[]', encoding='utf-8')
        report = self.root / 'exports' / 'broken.verification.json'
        report.write_text('[]', encoding='utf-8')
        invalid_report = self.root / 'exports' / 'invalid.verification.json'
        invalid_report.with_suffix('').with_suffix('.mp4').touch()
        invalid_report.write_text(json.dumps({'source': 'missing', 'verified': True, 'width': 360,
                                              'height': 640, 'fps': 30, 'video_duration_seconds': None}), encoding='utf-8')
        window = self.open_window()
        self.assertIsNotNone(window.episode)
        self.assertIn('Could not load connections', window.connection_notice.text())
        self.assertIn('invalid story.json', self.library.story_title(broken_story))
        self.assertEqual(window.export_table.rowCount(), 0)

    def test_empty_story_document_saves_when_switching_stories(self):
        first = self.library.create_story('A first')
        second = self.library.create_story('B second')
        window = self.open_window()
        window.bible_editor.setPlainText('Important planning notes before creating any episodes.')
        window.story_combo.setCurrentIndex(window.story_combo.findData(str(second)))
        self.assertIn('Important planning notes', (first / 'series_bible.md').read_text(encoding='utf-8'))

    def test_failed_save_keeps_sidebar_on_current_episode_and_story(self):
        first = self.library.create_story('A first')
        episode = self.library.create_episode(first)
        self.library.create_episode(first)
        second = self.library.create_story('B second')
        self.library.create_episode(second)
        episode = replace(episode, scenes=(replace(episode.scenes[0], subtitle='Caption'),))
        save_episode(episode)
        window = self.open_window()
        window.caption_table.item(0, 0).setText('unfinished')
        window.episode_list.setCurrentRow(1)
        self.assertEqual(window.episode_list.currentRow(), 0)
        window.story_combo.setCurrentIndex(window.story_combo.findData(str(second)))
        self.assertEqual(window.story_combo.currentData(), str(first))
        self.assertEqual(window.episode.directory, episode.directory)


if __name__ == '__main__':
    unittest.main()
