# Sample assets and provenance

The supplied samples use original geometric illustrations drawn locally with
Python/Pillow, original story text, and narration synthesized on this computer
with an installed Windows System.Speech voice. The voice is clearly labeled as
synthetic; no online voice service, AI image generator, or downloaded recording
was used.

The original sample illustrations, story text, procedural ambience, and paper
rustle sound are dedicated to the public domain under **CC0 1.0 Universal**.
You may use, modify, and redistribute these original assets, including in
commercial videos, without attribution. No likeness of a real person is used.

The Windows voice software is provided by the operating system and is not
redistributed with this project. The example WAV files are its locally produced
output. You can replace them with your own recordings or regenerate them using
an installed voice. They are not presented as human voice performances or as a
trained local AI voice model.

- `stories/studio_prototype/episodes/episode_001/assets/`: three original images,
  a transparent gate layer, and three short WAV voice recordings.
- `stories/the_letter_at_the_gate/episodes/episode_001/assets/`: the longer
  sample's images, transparent layer, and narration recordings.
- `assets/music/Studio ambience.wav`: original procedural sine-wave chords.
- `assets/sound_effects/Paper rustle.wav`: original filtered procedural noise.

The procedural audio and artwork are ordinary local software output. Source
code to recreate them is in `src/sample_project.py`.

The `connections_and_video_demo` sample reuses those original assets and voice
outputs. Its courtyard MP4 is animated locally from the CC0 artwork using FFmpeg,
and the animation is also dedicated under CC0 1.0. It is not an AI-generated
video. `tools/verify_connections_release.py` creates and verifies this mixed-media
sample without contacting an AI provider.
