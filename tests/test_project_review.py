"""Regression checks for source preservation, recovery and editorial saves."""
from dataclasses import replace
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src.exports import export_changed, export_source, source_inputs_sha256
from src.media import MediaError, ffmpeg
from src.production.runner import validate_script
from src.render_cache import ShotCache
from src.scene_builder import save_episode
from src.story_manager import StoryLibrary
from src.timeline import prepare_waveform
from src.video_renderer import render_episode
from test_media_pipeline import fixture
from test_production import PLAN, SCRIPT


class ProjectReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='VNS project review ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_deleted_source_in_copied_workspace_marks_export_outdated(self):
        library = StoryLibrary(self.root / 'original')
        episode = library.create_episode(library.create_story('Source'))
        image = episode.resolve_asset(episode.scenes[0].visual_asset)
        image.touch()
        source = episode.directory / 'scenes.json'
        report = {'source': str(source), 'source_inputs_sha256': source_inputs_sha256(source)}
        moved = self.root / 'copy'
        shutil.copytree(library.root, moved)
        local_source = moved / source.relative_to(library.root)
        self.assertFalse(export_changed(report, moved))
        local_source.unlink()
        self.assertEqual(export_source(report, moved), local_source)
        self.assertTrue(export_changed(report, moved))
        self.assertTrue(source.is_file())

    def test_nonobject_shot_cache_manifest_is_a_cache_miss(self):
        cache = ShotCache(self.root / 'shots')
        for record in ([], None, 'invalid', 42):
            with self.subTest(record=record):
                (cache.root / 'key.json').write_text(json.dumps(record), encoding='utf-8')
                self.assertFalse(cache.restore('key', self.root / 'restored.mp4'))

    def test_damaged_waveform_metadata_is_rebuilt(self):
        episode = fixture(self.root / 'waveform')
        data = prepare_waveform(episode)
        info = Path(data['path']).with_suffix('.json')
        for record in ([], {'sha256': data['sha256']}):
            with self.subTest(record=record):
                info.write_text(json.dumps(record), encoding='utf-8')
                restored = prepare_waveform(episode)
                self.assertGreater(len(restored['rms']), 0)
                self.assertEqual(restored['sha256'], data['sha256'])

    def test_unavailable_shot_cache_does_not_block_verified_render(self):
        episode = fixture(self.root / 'uncached')
        save_episode(episode)
        root = episode.directory / '.vns-cache'
        root.mkdir()
        (root / 'shots').write_text('Cannot create a directory here.', encoding='utf-8')
        output = self.root / 'export.mp4'
        report = render_episode(episode.directory / 'scenes.json', output)
        self.assertTrue(report['verified'])
        self.assertFalse(report['scene_cache']['enabled'])
        self.assertEqual(report['scene_cache']['hits'], 0)

    def test_export_cannot_replace_source_media_or_manual_subtitles(self):
        episode = fixture(self.root / 'protected')
        video = episode.directory / 'source.mp4'
        ffmpeg(['-f', 'lavfi', '-i', 'color=c=blue:size=80x140:rate=30', '-t', '0.8',
                '-an', '-c:v', 'libx264', str(video)])
        original = video.read_bytes()
        updated = replace(episode, scenes=(replace(episode.scenes[0], visual_asset='source.mp4',
                          media_type='video', camera_motion='static'),))
        save_episode(updated)
        with self.assertRaisesRegex(MediaError, 'source input'):
            render_episode(updated.directory / 'scenes.json', video)
        self.assertEqual(video.read_bytes(), original)

        save_episode(replace(episode, settings={**episode.settings, 'subtitle_mode': 'manual'}))
        subtitles = episode.directory / 'subtitles.srt'
        text = '1\n00:00:00,000 --> 00:00:00,100\nKeep my captions.\n'
        subtitles.write_text(text, encoding='utf-8')
        with self.assertRaisesRegex(MediaError, 'source input'):
            render_episode(episode.directory / 'scenes.json', episode.directory / 'subtitles.mp4')
        self.assertEqual(subtitles.read_text(encoding='utf-8'), text)
        self.assertFalse(video.with_suffix('.mp4.lock').exists())

    def test_duplicate_script_cast_is_rejected_before_media_generation(self):
        script = copy.deepcopy(SCRIPT)
        script['shots'][0]['characters'] = ['CHAR-001', 'CHAR-001']
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            validate_script(script, PLAN)

    def test_colliding_asset_import_hashes_without_reading_whole_media(self):
        library = StoryLibrary(self.root)
        episode = library.create_episode(library.create_story('Imports'))
        source = self.root / 'recording.wav'
        source.write_bytes(b'a new recording')
        existing = episode.directory / 'assets' / source.name
        existing.write_bytes(b'an earlier recording')
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Unbounded media read')):
            relative = library.import_asset(episode, source)
        self.assertEqual(episode.resolve_asset(relative).read_bytes(), b'a new recording')
        self.assertEqual(existing.read_bytes(), b'an earlier recording')


@unittest.skipUnless(os.environ.get('VNS_GUI_TESTS') == '1', 'Set VNS_GUI_TESTS=1 for editorial saves')
class DocumentSaveReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from src.app import StudioWindow
        temporary = tempfile.TemporaryDirectory(prefix='VNS document save ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        library = StoryLibrary(self.root)
        library.create_episode(library.create_story('Documents'))
        with patch('src.app.installed_voices', return_value=[]):
            self.window = StudioWindow(self.root)
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window.episode = None
        self.window.story = None
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_failed_bible_save_keeps_error_visible(self):
        self.window.bible_editor.setPlainText('Unsaved story notes')
        with patch('src.app.atomic_text', side_effect=OSError('Document is locked')):
            self.window.save_bible()
        self.assertIn('Document is locked', self.window.status.text())
        self.assertEqual(self.window.bible_editor.toPlainText(), 'Unsaved story notes')

    def test_failed_bible_switch_preserves_current_document_and_selection(self):
        self.window.bible_editor.setPlainText('Unsaved story notes')
        document = self.window._document_name
        with patch('src.app.atomic_text', side_effect=OSError('Document is locked')):
            self.window.bible_combo.setCurrentText('character_bible.md')
        self.assertEqual(self.window._document_name, document)
        self.assertEqual(self.window.bible_combo.currentText(), document)
        self.assertEqual(self.window.bible_editor.toPlainText(), 'Unsaved story notes')


if __name__ == '__main__':
    unittest.main()
