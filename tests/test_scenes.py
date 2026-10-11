"""Behavior checks for scene validation, scheduling, and subtitle generation."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from src.scene_builder import load_episode
from src.subtitle_generator import generate_subtitles
from src.video_renderer import build_render_plan


class ScenePipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.scenes_path = self.directory / "scenes.json"
        self.data = {
            "episode_id": "episode_001",
            "title": "Test episode",
            "scenes": [
                {
                    "scene_id": 1,
                    "duration_seconds": 6,
                    "visual_asset": "assets/first.png",
                    "narration": "First scene narration.",
                    "camera_motion": "slow_zoom_in",
                    "subtitle_style": "cinematic",
                },
                {
                    "scene_id": 2,
                    "duration_seconds": 5,
                    "visual_asset": "assets/second.png",
                    "narration": "Second scene narration.",
                    "camera_motion": "static",
                    "subtitle_style": "standard",
                },
            ],
        }

    def load(self, data=None):
        self.scenes_path.write_text(json.dumps(self.data if data is None else data), encoding="utf-8")
        return load_episode(self.scenes_path)

    def test_scene_changes_follow_array_order_and_duration(self):
        self.data["scenes"][0]["scene_id"] = 8
        episode = self.load()
        self.assertEqual(
            [(item.scene.scene_id, item.start_seconds, item.end_seconds) for item in episode.timeline()],
            [(8, 0.0, 6.0), (2, 6.0, 11.0)],
        )

    def test_plan_resolves_assets_relative_to_episode(self):
        plan = build_render_plan(self.load())
        self.assertEqual(plan["duration_seconds"], 11.0)
        self.assertEqual(plan["scenes"][0]["visual_asset"], str((self.directory / "assets/first.png").resolve()))
        self.assertEqual(plan["scenes"][1]["narration_audio"], str((self.directory / "narration.wav").resolve()))
        self.assertEqual(plan["scenes"][1]["audio_offset_seconds"], 6.0)
        self.assertEqual(plan["scenes"][1]["subtitle"], "Second scene narration.")

    def test_scene_audio_starts_at_zero_and_caption_can_be_overridden(self):
        self.data["scenes"][1].update({"narration_audio": "assets/voice_002.wav", "subtitle": "A shorter caption."})
        episode = self.load()
        scene = build_render_plan(episode)["scenes"][1]
        self.assertEqual(scene["audio_offset_seconds"], 0.0)
        self.assertEqual(scene["narration_audio"], str((self.directory / "assets/voice_002.wav").resolve()))
        self.assertEqual(scene["subtitle"], "A shorter caption.")
        self.assertIn("A shorter caption.", generate_subtitles(episode))

    def test_srt_uses_the_same_scene_boundaries(self):
        self.assertEqual(
            generate_subtitles(self.load()),
            "1\n00:00:00,000 --> 00:00:06,000\nFirst scene narration.\n\n"
            "2\n00:00:06,000 --> 00:00:11,000\nSecond scene narration.\n",
        )

    def test_fractional_durations_and_hidden_caption(self):
        self.data["scenes"][0].update({"duration_seconds": 0.125, "subtitle": ""})
        self.data["scenes"][1]["duration_seconds"] = 1.875
        self.assertEqual(
            generate_subtitles(self.load()),
            "1\n00:00:00,125 --> 00:00:02,000\nSecond scene narration.\n",
        )

    def test_timestamp_rounding_carries_into_minutes(self):
        self.data["scenes"][0]["duration_seconds"] = 59.9996
        subtitles = generate_subtitles(self.load())
        self.assertIn("00:00:00,000 --> 00:01:00,000", subtitles)
        self.assertIn("00:01:00,000 --> 00:01:05,000", subtitles)

    def test_rejects_duration_values_that_cannot_be_scheduled(self):
        for duration in (0, -1, True, "6", float("nan"), float("inf"), 10 ** 400):
            with self.subTest(duration=duration):
                data = copy.deepcopy(self.data)
                data["scenes"][0]["duration_seconds"] = duration
                with self.assertRaisesRegex(ValueError, "duration_seconds"):
                    self.load(data)

    def test_rejects_duplicate_or_invalid_scene_ids(self):
        for scene_id in (1, 0, -1, True, "2"):
            with self.subTest(scene_id=scene_id):
                data = copy.deepcopy(self.data)
                data["scenes"][1]["scene_id"] = scene_id
                with self.assertRaisesRegex(ValueError, "scene_id"):
                    self.load(data)

    def test_rejects_missing_fields_and_unknown_presets(self):
        for field in ("visual_asset", "narration", "camera_motion", "subtitle_style"):
            with self.subTest(missing=field):
                data = copy.deepcopy(self.data)
                del data["scenes"][0][field]
                with self.assertRaisesRegex(ValueError, "missing"):
                    self.load(data)
        for field in ("camera_motion", "subtitle_style"):
            with self.subTest(invalid=field):
                data = copy.deepcopy(self.data)
                data["scenes"][0][field] = "unknown"
                with self.assertRaisesRegex(ValueError, field):
                    self.load(data)

    def test_rejects_empty_episode_and_unknown_fields(self):
        self.data["scenes"] = []
        with self.assertRaisesRegex(ValueError, "non-empty array"):
            self.load()
        self.data["scenes"] = [{"scene_id": 1}]
        with self.assertRaisesRegex(ValueError, "missing"):
            self.load()
        self.data["scenes"][0] = {
            "scene_id": 1, "duration_seconds": 1, "visual_asset": "image.png",
            "narration": "Text", "camera_motion": "static", "subtitle_style": "standard",
            "duration_second": 1,
        }
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            self.load()

    def test_asset_check_reports_missing_media_and_accepts_existing_media(self):
        episode = self.load()
        with self.assertRaisesRegex(FileNotFoundError, "Scene 1: missing asset"):
            build_render_plan(episode, check_assets=True)
        (self.directory / "assets").mkdir()
        for filename in ("assets/first.png", "assets/second.png", "narration.wav"):
            (self.directory / filename).touch()
        self.assertEqual(build_render_plan(episode, check_assets=True)["duration_seconds"], 11.0)

    def test_rejects_episode_duration_overflow(self):
        for scene in self.data["scenes"]:
            scene["duration_seconds"] = 1e308
        with self.assertRaisesRegex(ValueError, "Total episode duration"):
            self.load()

    def test_rejects_srt_cues_shorter_than_timestamp_resolution(self):
        self.data["scenes"][0]["duration_seconds"] = 0.0001
        with self.assertRaisesRegex(ValueError, "too short for an SRT cue"):
            generate_subtitles(self.load())


if __name__ == "__main__":
    unittest.main()
