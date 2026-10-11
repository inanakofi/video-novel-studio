"""Real FFmpeg integration tests. No fake encoders or successful placeholder files."""
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
import threading
import unittest
import wave
from unittest.mock import patch
import os
import array

from PIL import Image, ImageDraw

from src.audio_manager import inspect_narration, prepare_voice, mix_audio
from src.media import MediaError, RenderCancelled, audio_duration, probe, verify_export
from src.scene_builder import Episode, Scene, save_episode, load_episode
from src.subtitle_generator import Cue, parse_srt, validate_cues
from src.video_renderer import render_episode, episode_captions, _publish_files
from src.story_manager import fit_episode_to_target
from src.batch import render_batch


def tone(path, duration=.65, frequency=330, amplitude=6000):
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
        output.writeframes(b''.join(struct.pack('<h', round(amplitude * math.sin(2 * math.pi * frequency * i / 48000))) for i in range(round(duration * 48000))))


def fixture(directory: Path) -> Episode:
    directory.mkdir(parents=True, exist_ok=True)
    scenes = []
    for index, color in enumerate(('#944530', '#2d675d', '#263354')):
        image = Image.new('RGB', (280, 490), color)
        ImageDraw.Draw(image).rectangle((80, 90, 180, 380), fill='#e3d49c')
        visual = f'image {index} été.png'
        image.save(directory / visual)
        recording = f'voix {index} été.wav'
        tone(directory / recording, frequency=330 + index * 80)
        scenes.append(Scene(index+1, .8, visual, f'Scene {index+1} caption.',
                            ['slow_zoom_in', 'pan_left', 'parallax'][index], 'cinematic', recording,
                            transition='crossfade', foreground_asset='layer.png' if index == 2 else None))
    layer = Image.new('RGBA', (280, 490))
    ImageDraw.Draw(layer).rectangle((15, 30, 35, 490), fill='#223344')
    layer.save(directory / 'layer.png')
    tone(directory / 'music.wav', .5, 110)
    tone(directory / 'effect.wav', .12, 660)
    return Episode('episode_001', 'A real test', directory, tuple(scenes),
                   {'width': 240, 'height': 426, 'fps': 30, 'preset': 'ultrafast',
                    'title_card': 'Opening', 'end_card': 'Next episode', 'title_duration': .4, 'end_duration': .4,
                    'music_asset': 'music.wav', 'music_volume': .1,
                    'sound_effects': [{'asset': 'effect.wav', 'start_seconds': 1, 'volume': .1}]})


class MediaPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='VNS été paths ')
        cls.root = Path(cls.temp.name)
        cls.episode = fixture(cls.root / 'story with spaces')
        cls.source = cls.episode.directory / 'scenes.json'
        save_episode(cls.episode)
        cls.output = cls.root / 'Export été.mp4'
        cls.report = render_episode(cls.source, cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_export_resolution_fps_encoding_and_decode(self):
        self.assertTrue(self.report['verified'])
        self.assertEqual((self.report['width'], self.report['height'], self.report['fps']), (240, 426, 30))
        self.assertEqual((self.report['video_codec'], self.report['audio_codec']), ('h264', 'aac'))
        self.assertEqual(self.report['full_decode'], 'passed')
        self.assertAlmostEqual(self.report['video_duration_seconds'], 3.2, places=2)
        self.assertAlmostEqual(self.report['audio_end_seconds'], 3.2, delta=.025)

    def test_subtitles_stay_in_actual_narration_windows(self):
        spans = inspect_narration(self.episode)
        cues = episode_captions(self.episode, spans)
        self.assertAlmostEqual(cues[0].start, .4)
        self.assertAlmostEqual(cues[0].end, 1.05)
        self.assertLessEqual(max(c.end for c in cues), self.report['audio_end_seconds'])
        saved = parse_srt(self.output.with_suffix('.srt').read_text(encoding='utf-8'))
        self.assertEqual(saved, cues)

    def test_pcm_slots_are_exact_even_after_loudness_normalization(self):
        with tempfile.TemporaryDirectory(dir=self.root) as folder:
            voice = prepare_voice(self.episode, inspect_narration(self.episode), Path(folder))
            self.assertAlmostEqual(audio_duration(voice), 3.2, places=4)
            for path in Path(folder).glob('voice_*.wav'):
                duration = audio_duration(path)
                self.assertTrue(abs(duration-.8) < .0001 or abs(duration-.4) < .0001)

    def test_long_audio_is_rejected_instead_of_truncated(self):
        episode = replace(self.episode, scenes=(replace(self.episode.scenes[0], duration_seconds=.3),))
        with self.assertRaisesRegex(MediaError, 'Fit to audio'):
            inspect_narration(episode)

    def test_short_episode_recording_is_rejected(self):
        episode = replace(self.episode, settings={**self.episode.settings, 'narration_asset': self.episode.scenes[0].narration_audio},
                          scenes=(replace(self.episode.scenes[0], narration_audio=None),))
        with self.assertRaisesRegex(MediaError, 'complete recording'):
            inspect_narration(episode)

    def test_missing_asset_fails_without_publishing(self):
        bad = replace(self.episode, scenes=(replace(self.episode.scenes[0], visual_asset='missing.png'),))
        source = self.episode.directory / 'missing.json'
        save_episode(bad, source)
        output = self.root / 'failed.mp4'
        with self.assertRaisesRegex(MediaError, 'missing image'):
            render_episode(source, output)
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix('.verification.json').exists())
        self.assertFalse(output.with_suffix('.mp4.lock').exists())

    def test_interrupted_render_preserves_export_and_can_rerun(self):
        digest = hashlib.sha256(self.output.read_bytes()).hexdigest()
        event = threading.Event()
        def progress(fraction, message):
            if .15 < fraction < .8:
                event.set()
        with self.assertRaises(RenderCancelled):
            render_episode(self.source, self.output, cancel=event, progress=progress)
        self.assertEqual(hashlib.sha256(self.output.read_bytes()).hexdigest(), digest)
        self.assertFalse(list(self.root.glob('.vns-render-*')))
        self.assertFalse(self.output.with_suffix('.mp4.lock').exists())
        report = render_episode(self.source, self.output)
        self.assertTrue(report['verified'])

    def test_active_output_lock_prevents_competing_render(self):
        lock = self.output.with_suffix('.mp4.lock')
        lock.write_text('test lock', encoding='utf-8')
        try:
            with self.assertRaisesRegex(MediaError, 'locked'):
                render_episode(self.source, self.output)
            self.assertEqual(lock.read_text(encoding='utf-8'), 'test lock')
        finally:
            lock.unlink()

    def test_verifier_rejects_wrong_export_contract(self):
        with self.assertRaisesRegex(MediaError, 'wrong video resolution'):
            verify_export(self.output, width=1080, height=1920, fps=30, duration=3.2)
        with self.assertRaisesRegex(MediaError, 'wrong frame rate'):
            verify_export(self.output, width=240, height=426, fps=24, duration=3.2)

    def test_invalid_manual_subtitle_bounds_fail_honestly(self):
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            validate_cues([Cue(0, 100, 'Too late')], 3.2)
        with self.assertRaisesRegex(ValueError, 'overlaps'):
            validate_cues([Cue(0, 1, 'One'), Cue(.5, 2, 'Two')], 3.2)
        with self.assertRaisesRegex(ValueError, 'outside'):
            validate_cues([Cue(.4, 1.2, 'Past narration')], 3.2, [(.4, 1.05)])

    def test_verification_report_is_bound_to_source_file(self):
        report = json.loads(self.output.with_suffix('.verification.json').read_text(encoding='utf-8'))
        self.assertEqual(report['source_sha256'], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(report['output'], str(self.output))
        self.assertEqual(report['output_sha256'], hashlib.sha256(self.output.read_bytes()).hexdigest())

    def test_fit_target_preserves_narration_and_rejects_impossible_length(self):
        episode = replace(self.episode, settings={**self.episode.settings, 'target_duration': 4})
        fitted = fit_episode_to_target(episode)
        self.assertAlmostEqual(fitted.timeline()[-1].end_seconds + .8, 4)
        self.assertTrue(all(s.duration_seconds >= .65 for s in fitted.scenes))
        with self.assertRaisesRegex(ValueError, 'needs at least'):
            fit_episode_to_target(replace(episode, settings={**episode.settings, 'target_duration': 1}))

    def test_final_audio_limiter_prevents_clipping_with_loud_music(self):
        with tempfile.TemporaryDirectory(dir=self.root) as folder:
            work = Path(folder)
            tone(work / 'loud.wav', .5, 111, amplitude=32000)
            episode = replace(self.episode, settings={**self.episode.settings, 'music_asset': str(work / 'loud.wav'),
                              'music_volume': 1, 'narration_volume': 2, 'duck_music': False})
            voice = prepare_voice(episode, inspect_narration(episode), work)
            mixed = mix_audio(episode, voice, work, 3.2)
            with wave.open(str(mixed), 'rb') as source:
                samples = array.array('h', source.readframes(source.getnframes()))
            peak = max(abs(sample) for sample in samples) / 32768
            self.assertLessEqual(peak, .891)
            self.assertGreater(peak, .8)

    def test_publication_error_rolls_back_video_and_sidecars(self):
        with tempfile.TemporaryDirectory(dir=self.root) as folder:
            work = Path(folder)
            pairs = []
            for index in range(3):
                old = self.root / f'publish_{index}.dat'
                new = work / f'new_{index}.dat'
                old.write_bytes(b'previous valid output')
                new.write_bytes(b'new output')
                pairs.append((new, old))
            real_replace = os.replace
            def fail_once(source, target):
                if Path(source) == pairs[2][0]:
                    raise OSError('simulated publication failure')
                return real_replace(source, target)
            with patch('src.video_renderer.os.replace', side_effect=fail_once):
                with self.assertRaisesRegex(OSError, 'publication failure'):
                    _publish_files(pairs, work)
            for _, old in pairs:
                self.assertEqual(old.read_bytes(), b'previous valid output')

    def test_batch_reports_each_success_and_failure(self):
        missing = self.root / 'bad_story' / 'episodes' / 'episode_002'
        missing.mkdir(parents=True)
        invalid = replace(self.episode, directory=missing)
        save_episode(invalid)
        reports = render_batch([self.source, missing / 'scenes.json'], self.root / 'batch')
        self.assertEqual([item['status'] for item in reports], ['verified', 'failed'])
        self.assertIn('missing image', reports[1]['error'])
        self.assertTrue((self.root / 'batch' / 'batch_report.json').is_file())


if __name__ == '__main__':
    unittest.main()
