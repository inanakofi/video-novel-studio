from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from src.story_manager import StoryLibrary, BIBLES
from src.scene_builder import load_episode, save_episode


class StoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.library = StoryLibrary(self.temp.name)

    def test_multiple_stories_numbering_and_previous_continuity(self):
        first = self.library.create_story('Ama & the heir', 'A family mystery.')
        second = self.library.create_story('Ama & the heir')
        self.assertNotEqual(first, second)
        self.assertTrue(all((first / name).is_file() for name in BIBLES))
        episode = self.library.create_episode(first)
        episode = replace(episode, metadata={**episode.metadata, 'cliffhanger': 'Who has the ring?'})
        save_episode(episode)
        next_episode = self.library.create_episode(first)
        self.assertEqual(next_episode.episode_id, 'episode_002')
        self.assertEqual(next_episode.metadata['previous_episode'], 'episode_001')
        context = (next_episode.directory / 'continuity_context.md').read_text(encoding='utf-8')
        self.assertIn('Who has the ring?', context)

    def test_breakdown_preserves_written_prose_and_generates_structured_files(self):
        story = self.library.create_story('New serial')
        episode = self.library.create_episode(story)
        text = '# Episode\n\n## Scene 1\n\nAma found the letter. Nobody was home.\n\n## Scene 2\n\nThe gate opened. Who was waiting?'
        updated = self.library.breakdown_script(episode, text)
        self.assertEqual(len(updated.scenes), 2)
        self.assertEqual(updated.metadata['hook'], 'Ama found the letter.')
        self.assertEqual(updated.metadata['cliffhanger'], 'Who was waiting?')
        self.assertEqual((episode.directory / 'script.md').read_text(encoding='utf-8'), text)
        self.assertTrue((episode.directory / 'scene_breakdown.md').is_file())
        self.assertEqual(load_episode(episode.directory / 'scenes.json').scenes, updated.scenes)

    def test_import_copies_unicode_files_and_preserves_existing_asset(self):
        episode = self.library.create_episode(self.library.create_story('Import'))
        source = self.library.root / 'été recording.wav'
        source.write_bytes(b'first contents')
        imported = self.library.import_asset(episode, source)
        source.write_bytes(b'second contents')
        second = self.library.import_asset(episode, source)
        self.assertNotEqual(imported, second)
        self.assertEqual(episode.resolve_asset(imported).read_bytes(), b'first contents')
        self.assertEqual(episode.resolve_asset(second).read_bytes(), b'second contents')

    def test_invalid_save_keeps_previous_project(self):
        episode = self.library.create_episode(self.library.create_story('Save'))
        path = episode.directory / 'scenes.json'
        before = path.read_bytes()
        invalid = replace(episode, scenes=(replace(episode.scenes[0], duration_seconds=-1),))
        with self.assertRaises(ValueError):
            save_episode(invalid)
        self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
