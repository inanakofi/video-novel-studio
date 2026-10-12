# Video Novel Studio

The studio now includes coordinated light and dark appearances, media thumbnails,
grouped scene/settings inspectors, cleaner tabs and controls, and collapsible
render details. Choose **Appearance** at the
bottom of the sidebar: **System**, **Light**, or **Dark**. The choice is saved
for the workspace. See [the appearance refresh](UI_REFRESH.md) and
[the workspace improvements and screenshots](UI_WORKSPACE.md).

**Complete beginner guide:** [TUTORIAL.md](TUTORIAL.md) covers fresh-PC setup,
offline video production, AI APIs/MCP, and automatic manuscript production.

The latest review, fixes, test results and outstanding draft assets are recorded
in [REVIEW_REPORT.md](REVIEW_REPORT.md). The subsequent model-catalog and runtime
review is in [MODEL_CATALOG_REVIEW.md](MODEL_CATALOG_REVIEW.md).

## Manuscript → videos

Attach a TXT, Markdown or DOCX manuscript, choose narrated visual novel,
animated cartoon or realistic cinematic series, assign task-specific connections,
and create an editable story with verified video exports. The workflow includes
35 built-in prompt areas, source analysis, bibles, scripts, text review, measured
speech, images/video, captions, saved stages and resume controls. Start with a
single short pilot. Cartoon/cinematic output requires a video connection;
optional lip-sync requires a compatible tool. Creative media review remains
necessary, and music/effects can be added in the editor.

See [AUTOMATION.md](AUTOMATION.md) for the conversation analysis, implemented
workflow, provider contracts and limitations. A small original
[practice manuscript](examples/blue_gate_manuscript.txt) is included.

An offline-first desktop application that turns written episodes, still images, video clips, and
narration recordings into vertical H.264/AAC videos. It includes a real FFmpeg
renderer, editable scene timeline, caption editor, story documents, local audio
mixing, an export verifier, and an embedded player for the finished MP4.

**Start here:** run `Start-Studio.ps1` (uses the project's virtual environment),
or run `.\.venv\Scripts\python.exe -m src.app` after setup. Open **The Letter at
the Gate** to explore the supplied three-scene sample. Its finished 75-second
video is in `exports/`.

## Optional connections and video scenes (1.2)

**Connections / AI** adds OpenRouter, Ollama and OpenAI-compatible text drafting,
ElevenLabs narration, ComfyUI image/video workflows, Runway text-to-video, generic
JSON HTTP requests and MCP tools. Connections are disabled by default. Every
generation is saved locally for review before you apply it. Windows credentials
are encrypted outside project files. Offline editing and exports remain independent
of these services; provider accounts and local models are not bundled.

Each manuscript task now has its own searchable model selection. Reuse one
platform connection/API key across text, illustration, speech and video models,
or keep several connections with different keys on the same platform. Free and
open-weights filters, cached discovery, saved task choices and connection
duplication simplify setup. OpenRouter media generation and compatible
image/speech servers are supported; see [setup details](CONNECTIONS.md#reuse-a-platform-across-tasks).
Use **Show all models** to clear catalog filters and **Refresh model catalogs**
to retrieve current lists. Each manuscript task displays its shown/total count;
discovery now also covers ElevenLabs speech models and ComfyUI workflow choices.

The scene editor now imports actual video clips with trim starts, muted-by-default
original audio, aspect-preserving crop and the existing captions/transitions.
**Connections and Video Demo** contains a verified 75-second mixed-media sample.

See [CONNECTIONS.md](CONNECTIONS.md) for provider setup, OpenRouter instructions,
optional MCP installation, recovery and current limits. See
[CONNECTIONS_VERIFICATION.md](CONNECTIONS_VERIFICATION.md) for tested versus
untested capabilities. [Live OpenRouter checks](exports/verification/openrouter-models-live.json)
produced a script and narration; the test account blocked images with HTTP 402.
Other adapters use protocol fixtures, which are not AI models.

## New editing and production controls

- **Timeline / captions:** click **Load waveform** to decode the current local
  narration, then **Listen / pause narration** to audition it. The waveform,
  scene blocks, transitions, music, sound effects and captions share the same
  timeline, including title/end cards. Zoom in for fine edits. Click the ruler
  to seek, drag a caption's edge to trim it or its centre to move it, or use
  **Cue start here / Cue end here** at the playhead. Changes save as manual SRT
  timings. The adjacent cue text follows playback.
  In automatic mode, saving keeps the caption table/SRT synchronized with the
  renderer. Ordinary automatic captions wrap to at most two lines; unusually
  long single words can still require manual shortening.
- Drag the right edge of a scene to change its duration. Later captions and sound
  effects move with the new boundary. Narration cannot be cut short. Ripple
  trimming requires separate scene recordings; split a continuous episode
  recording first. Drag a transition's right edge to change its length, or drag a
  sound effect to reposition it. Use the scene list's arrows to reorder scenes.
- **Play last video** plays/pauses the actual previous export beside the timeline.
  It is labelled when the project has changed. Rerender to see new caption,
  motion or timing edits. Narration audition shows scene artwork and current cue
  text; it does not pretend to be a newly rendered video. Load waveform again
  after changing scene/audio timing. Music and sound effects are heard in the MP4.
- **Series → Series style:** set fonts, voice, levels, music and card durations in
  Audio / output, choose colours in Series, then **Save as series defaults**.
  Title/end templates accept `{series}`, `{episode}` and `{title}`. New episodes
  inherit the defaults. **Apply defaults to this episode** updates an existing
  episode explicitly. Manual captions follow changes to the title offset. The
  narrator setting chooses future local speech generation; it does not replace
  existing recordings. Series music is copied to reusable `story/assets/music/`.
- **Series → Continuity tracker:** maintain character/location IDs, names and
  notes, plus plot threads with `open`/`resolved` status and episode references
  such as `episode_003`. Link records using the scene editor's character
  checkboxes and location selector. Writing shows previous endings, relevant
  open threads and linked reference notes. The Markdown bibles remain editable.
- **Publishing:** run the check before exporting. It reports missing/invalid
  assets and timings as errors, and flags duration, caption margins, long/fast
  captions and low-level narration pauses as warnings. Adjust the duration range
  and pause threshold for your series. Double-click a timed finding to inspect
  it in the timeline. Results save to `publishing_check.json`; rerun after edits.
  Margin/readability checks are conservative editorial guides, not platform UI
  guarantees. Pause detection measures audio level, not words or meaning.

Automatic caption generation remains proportional timing within the recording.
Waveform editing provides manual synchronization; no forced-alignment model is
used. Optional voice generation is separate from caption alignment.

## Faster rerenders

Scene encodes are cached under each episode's `.vns-cache/shots/`. A caption-only
edit reuses unchanged scene encodes while still encoding the final burned-in
captions/audio and fully verifying the new MP4. Changing an image rebuilds that
shot and dependent transitions. Cache keys include media contents, foregrounds,
motion, durations, transition frames, output quality/resolution/FPS and the
renderer/FFmpeg version. Checksums detect damaged entries and trigger rebuilding.

The shot cache is limited to approximately 1 GiB per episode; oldest entries are
evicted. Raw final frames keep transition dependencies independent of compression
artefacts. Export reports include actual cache hits/misses. `--no-cache` forces a
fresh scene render. Waveform audition files are also cached locally under the
episode's `.vns-cache/waveforms/`. You may remove an episode's `.vns-cache/` when
the studio and any renders are closed; it contains derived data, not source assets.
Original media, verified exports and normal cancellation guarantees are unchanged.

## Installation

For a new computer, clone or copy the whole repository into any folder. Run
`Setup.ps1` there, then `Start-Studio.ps1`. The source code, dependencies lists,
setup scripts, templates, documentation and sample images/audio/videos are all
included in Git. Replace example paths below with your checkout location.

Git excludes only local session/connection settings, generated job history,
Python environments/bytecode and rebuildable render caches/locks. The application
recreates its settings and caches. Optional provider keys must be entered again
on a new computer; recorded assets already applied to episodes are included in
the project's assets folders. Install Python and FFmpeg/FFprobe as described below.

Requirements:

- Python 3.10 or later; verified with Python 3.14.2.
- FFmpeg and FFprobe on PATH. The FFmpeg build must include `libx264`, `aac`,
  `libass`/`ass`, `zoompan`, `overlay`, `loudnorm`, `sidechaincompress`, and
  `alimiter`. Verified with FFmpeg/FFprobe 9.0 full build on Windows.
- Pillow and PySide6. Verified versions: Pillow 12.3.0 and PySide6 6.10.1.
  Pillow 12.3.0 or newer is required for its image-decoding security fixes.
- For optional local speech: Windows with an installed System.Speech voice.
  Importing recorded audio is available regardless of speech support.

On Windows, in PowerShell:

```powershell
cd J:\storyline\video-novel-studio
# If FFmpeg is not already installed:
winget install --id Gyan.FFmpeg --exact
# Open a new terminal after changing PATH.
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m src.doctor
.\.venv\Scripts\python.exe -m src.app
```

`Setup.ps1` performs the Python environment/dependency steps and checks FFmpeg;
`Start-Studio.ps1` prefers that virtual environment when present. FFmpeg may
also be installed manually. Set `VNS_FFMPEG` and `VNS_FFPROBE` to full executable
paths when PATH cannot be changed.

For an existing installation, update the project environment with
`.\.venv\Scripts\python.exe -m pip install -r requirements.txt`. Activate it with
`.\.venv\Scripts\Activate.ps1` before using the `python` commands below.

After installation, application use, local speech, media importing, previewing,
and rendering require **no network connection, accounts, cloud AI, paid API,
or online inference**. To prepare dependencies for another offline machine,
download compatible wheels on a machine with the same Python/OS first:

```powershell
python -m pip download -r requirements.txt -d wheels
python -m pip install --no-index --find-links wheels -r requirements.txt
```

Copy the FFmpeg/FFprobe executables separately. The installed Windows voices
belong to the operating system; they are not bundled voice models.

## Complete desktop workflow

1. **New story** creates the series, character and location bibles and continuity
   log. **New episode** assigns the next number and links previous continuity.
2. In **Writing**, type/paste a script or import a UTF-8 `.txt`/`.md` manuscript.
   Use a paragraph per scene or `## Scene 1` headings. **Build scenes from script**
   creates editable scene records, an episode outline, an opening hook and a
   cliffhanger draft, plus Markdown breakdown and continuity files.
   Rebuilding detaches previous recordings and returns captions to automatic
   mode; import or create narration for the revised text. Original recordings
   remain on disk.
3. In **Scenes / preview**, add at least three scenes. Browse to your images,
   or use shared character/background assets. The still preview preserves aspect
   ratio. The renderer fills the vertical frame by cropping, without stretching.
4. Import a voice recording for each scene. WAV, MP3, FLAC, AAC and other
   FFmpeg-supported formats work. Import fits the scene to the clip; **Fit to
   audio** repeats that operation. Alternatively, choose a complete episode
   recording in **Audio / output**, leaving individual voice clip fields empty.
5. On Windows, **Create local voice** uses the selected installed voice and
   writes a real WAV. If a supported voice is unavailable, import a recording.
   Text changes do not automatically change existing recorded speech.
6. Adjust scene duration, camera motion, transition and caption override.
   Move scenes with the arrow buttons. Durations are snapped to video frames
   when saved. Parallax needs a background plus a transparent foreground PNG;
   the app moves those layers at different rates during rendering.
7. Configure title/end cards, output resolution, frame rate, music, sound effects
   and volume under **Audio / output**. Music loops to the episode length and
   ducks under narration. Each sound effect has an editable start time and gain.
8. The default target is **75 seconds**, within the requested 60–90-second range.
   **Fit scenes to target duration** adjusts scene holds while preserving whole
   narration clips. It rejects a target shorter than the speech requires. This
   operation needs separate scene recordings; a continuous episode recording
   already has fixed speech positions.
9. **Captions → Generate from narration** creates wrapped SRT cues within the
   actual audio windows. Edit start/end times and text, then **Save manual timings**.
   Choose `auto` to regenerate during rendering or `manual` to use saved SRT.
10. **Check assets**, then **Render preview** for a 360 × 640 draft or **Render MP4**
    for the configured output (default 1080 × 1920, 30 FPS). Progress is real
    FFmpeg progress. Cancel safely with **Cancel job**.
11. The embedded player plays the actual verified output. Play/pause and seek
    through it. The Exports tab shows verified files and flags changed source
    projects. Each MP4 has an SRT sidecar and a `.verification.json` report.

New verification reports track scene settings, manual captions and referenced
images, foregrounds, videos, narration, music and sound effects. Changing or
removing those inputs marks the export as outdated, including after moving the
workspace. A detected source change during rendering prevents publication and
preserves the previous export. Older reports track only `scenes.json`; rerender
once to enable the expanded checks.

Use **Save project** to persist edits. Switching scenes keeps form edits in
memory; switching stories/episodes and closing the window save the project.
The last opened episode is restored on the next launch.

## Timing and rendering behavior

Scene durations are consecutive slots in array order. Title and end card
durations extend that timeline. Crossfades blend the previous scene's held final
frame into the beginning of the new scene, so transitions do not overlap voices
or shorten the narration timeline. `fade_black` fades the incoming scene from
black. Transitions are capped at half the incoming scene's length.

Each separate voice clip starts at zero. If a scene has no `narration_audio`,
the renderer uses the scene's time slice in `settings.narration_asset` (default
`narration.wav`). That complete recording covers the scenes, excluding title/end
cards. Narration longer than its assigned scene is an error, with a Fit to audio
instruction. Silent scenes are allowed by leaving both narration and voice clip
empty. Audio is normalized around −18 LUFS, music is optionally sidechain-ducked,
and the combined signal is peak-limited with headroom before AAC encoding.

Automatic caption timing distributes short text chunks across each actual
recording. **It is not speech recognition or word-level forced alignment.**
Listen in preview and correct cue boundaries manually for pauses and emphasis.
Cues that overlap, extend beyond the video, or exceed their scene's actual
narration window are rejected. Changing scene order, title duration, or narration
requires reviewing/regenerating saved manual timings.

Captions are burned into the video using ASS styles. Defaults are bold white,
outlined text with shadow, two short wrapped lines, a 360-pixel bottom margin,
and a 180-pixel right margin at 1080p. These keep text away from common short-video
controls; inspect the final preview for your chosen platform. Fonts and margins
are configurable. `cinematic` is bold; `standard` is smaller and regular weight.

## Story files and scene format

```text
video-novel-studio/
  stories/<story>/
    story.json
    series_bible.md
    character_bible.md
    location_bible.md
    continuity_log.md
    episodes/episode_001/
      script.md
      scenes.json
      episode_outline.md
      scene_breakdown.md
      continuity_context.md
      subtitles.srt
      assets/
  assets/{characters,backgrounds,music,sound_effects}/
  templates/{scenes.json,scenes.schema.json}
  src/
  tests/
  exports/
  verification/
```

An individual scene can contain:

```json
{
  "scene_id": 1,
  "duration_seconds": 6,
  "visual_asset": "assets/ama_mansion_night.png",
  "narration": "The night Ama married the poorest man in Accra...",
  "narration_audio": "assets/scene_001.wav",
  "camera_motion": "slow_zoom_in",
  "transition": "crossfade",
  "transition_seconds": 0.5,
  "subtitle_style": "cinematic"
}
```

The episode object contains `episode_id`, `title`, `scenes`, and optional
`settings`/`metadata`. IDs must be unique positive integers. Supported motions:
`static`, `slow_zoom_in`, `slow_zoom_out`, `pan_left`, `pan_right`, `parallax`.
Parallax requires `foreground_asset`. An optional `subtitle` overrides narration
text; an empty string hides that scene's captions. Asset references resolve
relative to `scenes.json`, including shared-library paths such as
`../../../../assets/backgrounds/mansion.png`.

See `src/settings.py` for the complete validated settings list. Projects use
ordinary JSON/Markdown/media files and can be moved together as a directory.
Absolute paths appear only in generated local render plans and verification
reports; rerender after moving a workspace to refresh those reports.

## Command-line tools

Run from the project directory:

```powershell
python -m src.doctor
python -m src.app
python -m src.app --workspace D:\MyStories
python -m src.sample_project
python -m src.sample_project --short
python -m src.subtitle_generator stories/the_letter_at_the_gate/episodes/episode_001/scenes.json
python -m src.video_renderer stories/the_letter_at_the_gate/episodes/episode_001/scenes.json --render --output exports/episode_001.mp4
python -m src.video_renderer stories/the_letter_at_the_gate/episodes/episode_001/scenes.json --render --preview --output exports/preview.mp4
python -m src.batch stories/the_letter_at_the_gate --output exports
python -m src.publishing stories/the_letter_at_the_gate/episodes/episode_001/scenes.json
```

Omit `--render` to print a JSON planning summary. Batch rendering saves a
per-episode success/failure report and returns a failing exit code if any episode
fails. The pre-existing `ama_and_the_secret_heir` writing scaffold is preserved;
its example asset references need to be replaced before it can render.

## Tests and verification

```powershell
python -m unittest discover -s tests -v
# Include real desktop interaction and playback tests:
$env:VNS_GUI_TESTS = '1'
python -m unittest discover -s tests -v
```

Tests use actual FFmpeg renders, not mocked encoders. The desktop test supplies
file-picker choices programmatically, then imports real sample recordings and
images, edits the widgets, renders, decodes video in the player, and reopens the
saved project. It requires an interactive desktop and the included prototype
sample files. The GUI local-voice test runs when an installed Windows voice is
available. No microphone or cloud service is required. Connection tests start
loopback HTTP fixtures; MCP tests are skipped if the optional dependency is absent.

Every successful export is checked with FFprobe for H.264/AAC, pixel format,
resolution, frame rate, video/audio duration, and subtitle bounds, then decoded
fully by FFmpeg. Tests also cover Unicode/space-containing filenames, audio
normalization duration, clipping prevention, missing assets, manual timing,
cancellation, safe reruns, output locks, publication rollback, and batch failures.

See `VERIFICATION_REPORT.md` for the final environment and measured results.
The editing/cache upgrade is documented in `IMPROVEMENTS_PLAN.md` and its
verification evidence is under `verification/`.

## Limitations and troubleshooting

- The original script breakdown/hook helpers remain deterministic. Optional
  generation adapters require a separately configured model service. No AI model
  weights or voice-cloning implementation are bundled. Live OpenRouter text and
  speech were exercised; other cloud and local-model inference remains unverified.
  See CONNECTIONS.md for the tested scope and account limitations.
- Local TTS is implemented and tested for Windows System.Speech. On other
  platforms, import narration. The Python/media services are portable, but
  desktop packaging and playback were verified on Windows only.
- Still-image motion and layered parallax are compositing effects, not generated
  character animation. Supply artwork and transparent layers yourself.
- Missing `ffmpeg`/`ffprobe`: install a full build, reopen the terminal/app, and
  run `python -m src.doctor`. Missing `ass` requires a build with libass.
- A recording does not fit: use Fit to audio, lengthen the scene, or revise and
  re-record narration. A continuous episode track must cover every scene slot.
- Captions outside narration: regenerate or adjust their timings, especially
  after changing title cards, scene order, duration or recordings.
- A locked export: let the active render finish or cancel it. After a hard
  process/OS crash, confirm that process is gone, then remove only that output's
  `.mp4.lock`. Never remove another running render's lock or temporary folder.
- An interrupted render cleans its own `.vns-render-*` temporary directory.
  Older verified exports remain intact on validation, encoding, cancellation,
  and tested publication failures. An OS crash can leave an owned temporary
  folder behind; it can be removed once that render process is gone.
- An MP4 open in another application may be locked on Windows. Close that player
  before replacing the file. The studio releases its own player before rerendering.
- Render speed depends on CPU, resolution and length. Use the 360p draft while
  editing; final output defaults to 1080p. Detailed process errors appear in the
  bottom log; failures never receive a successful verification report.

Sample artwork, text, music and sound-effect provenance is in `SAMPLE_ASSETS.md`.
