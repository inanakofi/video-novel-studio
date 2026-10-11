# Video Novel Studio — verification report

The completed editing/production upgrade is documented in
[UPGRADE_REPORT.md](UPGRADE_REPORT.md), with the current **46-test** result,
new desktop controls and measured scene-cache performance. The initial baseline
measurements below remain a record of the first delivery; its older export
sidecars describe the source at that time.

Verified locally on 11 October 2026. The application, sample media, tests and
documentation are delivered in this directory. No external AI service or online
inference was used. Runtime media processing and Windows speech synthesis run
locally.

## Delivered exports

| Measurement | Full sample | Three-scene prototype |
| --- | --- | --- |
| File | [The Letter at the Gate - Episode 001.mp4](exports/The%20Letter%20at%20the%20Gate%20-%20Episode%20001.mp4) | [Prototype – three scenes.mp4](exports/Prototype%20%E2%80%93%20three%20scenes.mp4) |
| Resolution / frame rate | 1080 × 1920 / 30 FPS | 1080 × 1920 / 30 FPS |
| Video / audio | H.264 / AAC | H.264 / AAC |
| Video duration | 75.000000 s | 19.266667 s |
| Audio end | 75.000000 s | 19.266667 s |
| Last subtitle end | 69.410 s | 16.962 s |
| Caption count | 18 | 5 |
| Full FFmpeg decode | Passed | Passed |

The short prototype deliberately falls below the default 60–90 second guidance.
The full sample meets it. Both exports have SRT and `.verification.json` sidecars
containing FFprobe measurements, completion timestamps and source/output SHA-256
hashes. Only validated exports are published.

The full sample exercises three illustrated scenes, slow zoom/pan, layered
parallax, crossfades, title/end cards, local narration, background music, a timed
sound effect and burned-in captions. Artwork is proportionately cropped rather
than stretched. Original art/text/procedural audio and local voice provenance are
documented in [SAMPLE_ASSETS.md](SAMPLE_ASSETS.md).

## Desktop workflow and playback

The actual PySide6 application was exercised through its widgets: create a story,
add three scenes, import included images and offline-voice WAV recordings, reorder
scenes, generate captions, edit caption text and timing, save manual captions,
render a preview, play decoded frames, and reopen saved state. File-picker choices
were supplied by the test; encoding and playback were real. The local voice button
also generated a real WAV through the installed Windows voice.

The final 75-second MP4 was opened in the studio's QMediaPlayer/QVideoSink player.
Playback and seeking at 10, 34, 60 and 74 seconds produced real decoded frames
without a playback error. Screenshots were inspected for image composition and
caption visibility. Automated playback was muted; this is not a claim of human
listening or word-level alignment. The actual AAC stream was separately decoded
to PCM: measured mono peak 0.574707 and RMS 0.065345, below full-scale clipping.

Evidence:

- [Final desktop screenshot](verification/desktop-final.png)
- [Sample playback measurements](verification/sample-playback.json)
- [Desktop workflow measurements](verification/desktop-workflow.json)
- [Scene and caption frame](verification/playback-60s.png)
- [Environment inventory](verification/environment.json)

The workflow test uses an isolated temporary workspace which is removed after
the test. Its JSON preserves the measured result; the delivered MP4s above remain
in `exports/`.

## Automated checks

The complete suite passed **34 tests in 30.873 seconds**, including real desktop
tests enabled with `VNS_GUI_TESTS=1`. After the final planning-summary and manual
caption test refinements, the affected scene suite passed again (13 tests), and
the desktop suite passed again (2 tests).

Coverage includes scene validation/order/timing, subtitle parsing and bounds,
missing assets, narration duration, exact normalized audio slot lengths, actual
encoding/resolution/frame rate, music limiting, manual captions, filenames with
spaces and non-ASCII characters, cancellation during rendering, safe reruns,
output locks, transactional publication rollback, and batch success/failure
reporting. Story tests cover numbering, continuity, structured script breakdowns,
asset import collisions and atomic saves. Failed exports are not marked successful.

Run from this directory in PowerShell:

```powershell
$env:VNS_GUI_TESTS = '1'
python -m unittest discover -s tests -v
python -m src.doctor
```

`python -m pip check` also passed. The environment used Python 3.14.2, Pillow
12.1.0, PySide6 6.10.1, FFmpeg/FFprobe 9.0 full build, and Windows 10 build 19045.
Required encoders/filters and Microsoft David, Hazel and Zira Desktop voices were
detected. Windows is the tested desktop platform.

## Practical limits

- Automatic captions use proportional text timing within the actual narration
  span, not speech recognition or forced alignment. Review and manually adjust
  timing for a polished publication. Bounds are enforced against audio/video.
- Script breakdowns and hook/cliffhanger drafts organize user-written text using
  deterministic rules. No AI novel, image or voice model is bundled.
- Windows System.Speech is implemented and tested. Import recorded narration if
  a compatible installed voice is unavailable; no speech API is required.
- Graceful cancellation and publication rollback are tested. A hard operating
  system/process crash can leave an owned lock/temp directory; recovery is
  documented in the README.
- The original `ama_and_the_secret_heir` scaffold is preserved. Its example asset
  references must be populated before rendering; the two supplied sample stories
  contain working assets.

Launch with `python -m src.app` or `Start-Studio.ps1`. Installation, offline setup,
editing, rendering and troubleshooting are in [README.md](README.md).
