from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from src.media import ffmpeg
from src.scene_builder import save_episode, load_episode
from src.video_assets import visual_preview
from src.video_renderer import render_episode, asset_errors
from src.render_cache import shot_key
from src.settings import settings_for
from test_media_pipeline import fixture


class VideoSceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='VNS vidéo clips ')
        cls.root = Path(cls.temp.name)
        episode = fixture(cls.root / 'episode été')
        cls.clip = episode.directory / 'moving picture été.mp4'
        ffmpeg(['-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=24', '-f', 'lavfi', '-i',
                'sine=frequency=200:sample_rate=48000', '-t', '2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(cls.clip)])
        scenes = list(episode.scenes)
        scenes[1] = replace(scenes[1], media_type='video', visual_asset=cls.clip.name, camera_motion='static',
                            video_start_seconds=.3, video_audio_volume=.2)
        cls.episode = replace(episode, scenes=tuple(scenes))
        save_episode(cls.episode)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_mixed_video_export_audio_captions_and_cache(self):
        report = render_episode(self.episode.directory / 'scenes.json', self.root / 'mix été.mp4')
        self.assertTrue(report['verified'])
        self.assertEqual(report['full_decode'], 'passed')
        self.assertEqual((report['width'], report['height'], report['fps']), (240, 426, 30))
        self.assertLessEqual(report['audio_end_seconds'], report['video_duration_seconds'] + .06)
        self.assertTrue(visual_preview(self.episode, self.episode.scenes[1]).is_file())
        cached = render_episode(self.episode.directory / 'scenes.json', self.root / 'mix été.mp4')
        self.assertEqual(cached['scene_cache']['misses'], 0)

    def test_trim_rejected_beyond_clip_and_cache_depends_on_start(self):
        scenes = list(self.episode.scenes)
        scenes[1] = replace(scenes[1], video_start_seconds=1.5)
        invalid = replace(self.episode, scenes=tuple(scenes))
        self.assertTrue(any('beyond' in e for e in asset_errors(invalid)))
        settings = settings_for(self.episode)
        a = shot_key(self.clip, .8, 'static', settings, media_type='video', video_start_seconds=0)
        b = shot_key(self.clip, .8, 'static', settings, media_type='video', video_start_seconds=.2)
        self.assertNotEqual(a, b)

    def test_schema_roundtrip_and_video_motion_validation(self):
        loaded = load_episode(self.episode.directory / 'scenes.json')
        self.assertEqual(loaded.scenes[1].media_type, 'video')
        self.assertEqual(loaded.scenes[1].video_start_seconds, .3)
        scenes = list(loaded.scenes)
        scenes[1] = replace(scenes[1], camera_motion='parallax', foreground_asset='layer.png')
        with self.assertRaisesRegex(ValueError, 'video scenes'):
            save_episode(replace(loaded, scenes=tuple(scenes)))
