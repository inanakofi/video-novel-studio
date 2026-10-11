from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from test_media_pipeline import fixture
from src.scene_builder import save_episode, load_episode
from src.media import MediaError
from src.series_tools import save_style, apply_style, save_continuity, continuity_notes, reference_errors
from src.story_manager import StoryLibrary
from src.timeline import edit_timeline, prepare_waveform, silent_ranges, total_duration
from src.video_renderer import render_episode, episode_captions
from src.subtitle_generator import cues_to_srt, write_ass
from src.settings import settings_for
from src.publishing import publishing_check


class EditingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='Editing été ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.episode = fixture(self.root / 'stories' / 'serial' / 'episodes' / 'episode_001')
        save_episode(self.episode)
        self.cues = episode_captions(self.episode)

    def test_caption_millisecond_edit_preserves_audio_boundary_and_rejects_overlap(self):
        _, cues = edit_timeline(self.episode, self.cues, 'caption', 0, .45, self.cues[0].end)
        self.assertEqual(cues[0].start, .45)
        self.assertEqual(cues[0].end, 1.05)
        with self.assertRaisesRegex(ValueError, 'outside|overlaps'):
            edit_timeline(self.episode, self.cues, 'caption', 0, .4, 1.3)
        self.assertEqual(self.cues[0].start, .4)

    def test_automatic_captions_respect_two_wrapped_lines(self):
        from src.subtitle_generator import make_cues
        from src.audio_manager import inspect_narration
        text = 'Handwriting extraordinary handwriting extraordinary handwriting extraordinary'
        episode = replace(self.episode, scenes=(replace(self.episode.scenes[0], narration=text),))
        cues = make_cues(episode, inspect_narration(episode))
        self.assertTrue(all(len(cue.text.splitlines()) <= 2 for cue in cues))
        self.assertEqual(' '.join(' '.join(cue.text.split()) for cue in cues), text)

    def test_scene_trim_ripples_later_captions_and_preserves_voice(self):
        updated, cues = edit_timeline(self.episode, self.cues, 'scene', 0, .4, 1.5)
        self.assertAlmostEqual(updated.scenes[0].duration_seconds, 1.1)
        self.assertEqual(cues[0], self.cues[0])
        self.assertAlmostEqual(cues[1].start, self.cues[1].start + .3)
        with self.assertRaisesRegex(MediaError, 'narration'):
            edit_timeline(self.episode, self.cues, 'scene', 0, .4, .7)

    def test_continuous_recording_cannot_silently_ripple(self):
        episode = replace(self.episode, scenes=(replace(self.episode.scenes[0], narration_audio=None),))
        with self.assertRaisesRegex(ValueError, 'separate scene recordings'):
            edit_timeline(episode, [], 'scene', 0, .4, 2)

    def test_transition_and_sound_effect_edits_are_bounded(self):
        updated, _ = edit_timeline(self.episode, self.cues, 'transition', 0, .4, .6)
        self.assertAlmostEqual(updated.scenes[0].transition_seconds, .2)
        with self.assertRaisesRegex(ValueError, 'half the scene'):
            edit_timeline(self.episode, self.cues, 'transition', 0, .4, 1.1)
        updated, _ = edit_timeline(self.episode, self.cues, 'effect', 0, 2.4, 2.52)
        self.assertEqual(updated.settings['sound_effects'][0]['start_seconds'], 2.4)
        with self.assertRaisesRegex(ValueError, 'complete sound effect'):
            edit_timeline(self.episode, self.cues, 'effect', 0, 3.15, 3.27)

    def test_waveform_is_actual_pcm_with_cards_and_content_invalidation(self):
        data = prepare_waveform(self.episode)
        self.assertAlmostEqual(data['duration'], total_duration(self.episode), places=3)
        self.assertEqual(len(data['peaks']), 320)
        self.assertEqual(max(data['peaks'][:35]), 0)
        self.assertGreater(max(data['peaks'][45:90]), .01)
        again = prepare_waveform(self.episode)
        self.assertEqual(again['key'], data['key'])
        from test_media_pipeline import tone
        tone(self.episode.resolve_asset(self.episode.scenes[0].narration_audio), .65, 880)
        changed = prepare_waveform(self.episode)
        self.assertNotEqual(changed['key'], data['key'])
        self.assertTrue(silent_ranges({'rms': [0]*20+[.2]*10+[0]*20, 'bin_seconds': .1, 'duration': 5}, minimum=1.5))

    def test_series_defaults_inherit_without_mutating_old_episode_or_music_path(self):
        episode = replace(self.episode, settings={**self.episode.settings, 'font_size': 65, 'caption_color': '#FFAACC'})
        save_style(episode, voice='Offline voice', rate=2, title_template='{series} | {episode} | {title}')
        original = (episode.directory / 'scenes.json').read_bytes()
        library = StoryLibrary(self.root)
        new = library.create_episode(episode.directory.parent.parent, 'Next chapter')
        self.assertEqual(new.settings['font_size'], 65)
        self.assertEqual(new.metadata['voice_rate'], 2)
        self.assertEqual(new.resolve_asset(new.settings['music_asset']).read_bytes(), episode.resolve_asset('music.wav').read_bytes())
        self.assertNotEqual(new.resolve_asset(new.settings['music_asset']), episode.resolve_asset('music.wav'))
        self.assertIn('002 | Next chapter', new.settings['title_card'])
        self.assertEqual((episode.directory / 'scenes.json').read_bytes(), original)
        with self.assertRaisesRegex(ValueError, 'support only'):
            save_style(episode, title_template='{unknown}')
        ass = self.root / 'colours.ass'
        write_ass(self.cues, ass, settings_for(episode))
        self.assertIn('&H00CCAAFF', ass.read_text(encoding='utf-8-sig'))

    def test_ripple_moves_later_effects_and_manual_styles_follow_scene(self):
        episode = replace(self.episode, settings={**self.episode.settings, 'sound_effects': [{'asset': 'effect.wav', 'start_seconds': 1.6, 'volume': .2}]})
        updated, cues = edit_timeline(episode, self.cues, 'scene', 0, .4, 1.5)
        self.assertAlmostEqual(updated.settings['sound_effects'][0]['start_seconds'], 1.9)
        updated = replace(updated, scenes=tuple(replace(s, subtitle_style='standard') for s in updated.scenes),
                          settings={**updated.settings, 'subtitle_mode': 'manual'})
        (updated.directory / 'subtitles.srt').write_text(cues_to_srt(cues), encoding='utf-8')
        self.assertTrue(all(cue.style == 'standard' for cue in episode_captions(updated)))

    def test_continuity_tracks_episode_specific_threads_and_scene_references(self):
        story = self.episode.directory.parent.parent
        data = {'characters': [{'id': 'ama', 'name': 'Ama', 'notes': 'Carries the letter.'}],
                'locations': [{'id': 'gate', 'name': 'North gate', 'notes': 'Always locked.'}],
                'threads': [{'id': 'letter', 'name': 'Who sent it?', 'status': 'resolved',
                             'opened_episode': 'episode_001', 'resolved_episode': 'episode_003', 'notes': 'Blue seal.'}]}
        save_continuity(story, data)
        episode = replace(self.episode, scenes=(replace(self.episode.scenes[0], characters=('ama',), location='gate'),))
        save_episode(episode)
        self.assertEqual(load_episode(episode.directory / 'scenes.json').scenes[0].characters, ('ama',))
        self.assertIn('Who sent it?', continuity_notes(episode))
        self.assertIn('Carries the letter', continuity_notes(episode))
        self.assertNotIn('Who sent it?', continuity_notes(replace(episode, episode_id='episode_003')))
        self.assertEqual(reference_errors(episode), [])
        self.assertTrue(reference_errors(replace(episode, scenes=(replace(episode.scenes[0], location='absent'),))))
        before = (story / 'continuity.json').read_bytes()
        data['threads'][0]['resolved_episode'] = ''
        with self.assertRaisesRegex(ValueError, 'resolution episode'):
            save_continuity(story, data)
        self.assertEqual((story / 'continuity.json').read_bytes(), before)

    def test_publishing_check_reports_assets_margins_duration_and_pauses(self):
        scenes = tuple(replace(scene, duration_seconds=3) for scene in self.episode.scenes)
        episode = replace(self.episode, scenes=scenes, settings={**self.episode.settings, 'margin_bottom': 50})
        report = publishing_check(episode)
        self.assertTrue(report['ready'])
        codes = {i['code'] for i in report['issues']}
        self.assertTrue({'duration', 'safe_area', 'pause'}.issubset(codes))
        self.episode.resolve_asset(self.episode.scenes[0].visual_asset).unlink()
        bad = publishing_check(episode)
        self.assertFalse(bad['ready'])
        self.assertIn('asset', {i['code'] for i in bad['issues']})


class CacheIntegrationTests(unittest.TestCase):
    def test_real_rerenders_reuse_then_invalidate_shots_and_recover_corruption(self):
        with tempfile.TemporaryDirectory(prefix='Cache été ') as folder:
            root = Path(folder)
            episode = fixture(root / 'episode')
            source, output = episode.directory / 'scenes.json', root / 'verified.mp4'
            save_episode(episode)
            first = render_episode(source, output)
            self.assertEqual(first['scene_cache'], {'enabled': True, 'hits': 0, 'misses': 5})
            episode = replace(episode, scenes=(replace(episode.scenes[0], subtitle='Edited caption.'), *episode.scenes[1:]))
            save_episode(episode)
            second = render_episode(source, output)
            self.assertEqual(second['scene_cache']['hits'], 5)
            self.assertIn('Edited caption', output.with_suffix('.srt').read_text())
            Image.new('RGB', (280, 490), '#111111').save(episode.resolve_asset(episode.scenes[0].visual_asset))
            third = render_episode(source, output)
            self.assertEqual(third['scene_cache']['misses'], 2, 'Changed visual and next crossfade must be rebuilt')
            self.assertTrue(third['verified'])
            cache = episode.directory / '.vns-cache' / 'shots'
            for path in cache.glob('*.mp4'):
                path.write_bytes(b'corrupt cached media')
            fourth = render_episode(source, output)
            self.assertEqual(fourth['scene_cache']['hits'], 0)
            self.assertTrue(fourth['verified'])
            self.assertFalse(list(root.glob('.vns-render-*')))


if __name__ == '__main__':
    unittest.main()
