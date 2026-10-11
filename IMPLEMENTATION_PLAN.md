# Video Novel Studio implementation plan

## Architecture

The application runs entirely on this computer. Python owns project files and
validation; FFmpeg encodes and mixes media; FFprobe verifies inputs and every
completed export. PySide6 supplies the desktop editor and an actual video player.
Pillow prepares original illustrations, cards, and correctly proportioned images.
Windows System.Speech supplies optional offline speech with imported recordings
as the portable fallback. No inference service, account, or network is required.

- `story_manager.py`: atomic project saves, story/episode creation, bibles,
  continuity, deterministic script breakdowns, and copied media imports.
- `scene_builder.py`: typed scene records and stable, ordered timing.
- `media.py`: dependency discovery, cancellable subprocesses, probing, validation.
- `audio_manager.py`: recorded audio, local speech, voice normalization and mixing.
- `subtitle_generator.py`: wrapped captions, editable cues, SRT and ASS styles.
- `video_renderer.py`: real scene motion, transitions, cards, audio, captions,
  cancellation, atomic publication, and FFprobe verification.
- `app.py`: desktop story library, document/script editors, scene forms, missing
  asset status, timeline/preview, audio/settings, background render jobs.
- `sample_project.py`: locally drawn sample images and installed-voice WAV files,
  with provenance. Original story text and illustrations are CC0.

Scene durations describe consecutive slots. Crossfades occupy the beginning of
the incoming slot, preserving narration boundaries and subtitle timing. A scene
can use its own voice clip or a slice from the episode recording. Narration that
does not fit is an actionable error. Title/end cards have explicit durations.
The default target is 75 seconds (guidance range 60–90); shorter previews and
longer episodes are allowed and reported honestly.

## Verifiable phases

1. Inspect dependencies and existing scaffold. Preserve the existing story.
2. Implement a three-scene media pipeline, create local sample assets, render
   an MP4, and inspect FFprobe results and extracted frames.
3. Add automated media tests, including failure, cancellation, Unicode paths,
   audio/subtitle timing, encoding, resolution, and frame rate.
4. Add story operations, script breakdowns, music/effects, styling, crossfades,
   cards and layered parallax. Verify each through real renders/tests.
5. Build the desktop application over the verified services. Exercise project
   creation, importing three visuals and narration, editing, subtitles, rendering,
   video playback, persistence and safe reruns through the actual widgets.
6. Deliver dependency/setup instructions, asset provenance, and a verification
   report distinguishing tested capabilities from remaining limitations.

## Environment inspected

Python 3.14.2, FFmpeg/FFprobe 9.0 full build, Pillow, PySide6, and Windows
System.Speech are available. Installed voices: David, Hazel, and Zira Desktop.
The existing project contains scene validation and plans but no video encoder.

## Export safety

Each render owns a unique temporary directory under its output directory. Only
that directory is cleaned. A per-output lock prevents simultaneous overwrite.
Encode into staging, validate streams, timestamps, subtitles and full decoding,
then replace the final file. Failure/cancellation leaves an older valid export
intact. A verification JSON accompanies every successful export.

## Completion

All six phases are implemented and verified. The delivered 75-second production
sample and 19.27-second prototype pass FFprobe and full decoding. The 34-test
suite includes real rendering, interruption/recovery and desktop editing/playback.
See [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md) for measured results,
evidence, tested platform and practical limitations.
