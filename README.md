# Video Novel Studio

Video Novel Studio is an offline-first Python desktop application for creating
narrated story videos and adapting manuscripts into an editable episodic series.
Combine written scenes, illustrations or video clips, narration, captions, music
and sound effects, then export real H.264/AAC MP4 files using FFmpeg. The default
canvas is vertical **1080 × 1920 at 30 FPS**, with a **75-second** episode target
and a faster **360 × 640** preview option.

The studio is intended for authors, storytellers and video creators who want a
local workspace for writing, maintaining continuity, assembling media and reviewing
finished episodes. Its core editor and renderer work without accounts or a network.
Optional provider connections add AI-assisted writing and media generation; models,
provider accounts and API credits are supplied separately.

There are two main ways to use it:

1. **Edit an episode yourself.** Write or import a script, build scenes, import
   artwork/video and recordings, adjust the timeline and captions, and render.
2. **Produce from a manuscript.** Import TXT, Markdown or DOCX, choose an adaptation
   format, assign generation connections, review the plan, and run a saved sequence
   of writing, speech, visual generation and verified exports. Continue editing the
   resulting story in the same desktop workspace.

## Capabilities

| Area | What you can do |
| --- | --- |
| Story library | Create multiple series and numbered episodes; edit series, character and location bibles, hooks, cliffhangers and continuity notes. |
| Scene editor | Add, reorder and remove scenes; select reusable assets; control duration, camera movement, transitions, captions and character/location links. |
| Images and video | Animate stills with zooms or pans; composite layered parallax; import actual video, choose its trim start, and optionally mix its original sound. |
| Audio | Import separate scene recordings or one episode recording; create speech with an installed Windows voice; loop music, duck it under speech and place sound effects. |
| Timeline and captions | Decode narration waveforms, audition speech, seek and trim scene/caption boundaries; generate proportional captions or edit/import manual SRT timings. |
| Series defaults | Reuse fonts, colours, voice choices, music, output settings and title/end-card templates across episodes. |
| Publishing checks | Find missing assets, invalid timing, caption readability concerns, narration pauses and episodes outside your configured duration range. |
| Rendering and playback | Render previews, final MP4s or a whole story batch; cancel jobs; reuse cached shots; play the actual export in the embedded player. |
| AI connections | Draft text and generate images, speech or video through configured HTTP providers, local services or explicit MCP tools. Review saved results before applying them. |
| Manuscript production | Analyse source sections, create bibles and a season plan, write/review scripts, generate media, save stage history and resume interrupted production. |

Choose **System**, **Light** or **Dark** under **Appearance** in the sidebar.
The choice is saved for the workspace. Media thumbnails, collapsible inspectors
and render logs support editing and troubleshooting.

Successful exports include an MP4, SRT sidecar and verification report. Verification
checks stream properties, duration and caption bounds, then fully decodes the file.
This establishes technical integrity; watch and listen to each video to assess its
creative quality before publishing.

## Quick start

On Windows, install Python 3.10+ and a full FFmpeg build with FFprobe, then run
these commands from the checkout:

```powershell
.\Setup.ps1
.\Start-Studio.ps1
```

`Setup.ps1` creates `.venv`, updates pip, installs the core dependencies and checks the runtime.
It does not install Python or FFmpeg. See [Installation](#installation) for manual
setup, executable overrides and preparing an offline installation.

Open **The Letter at the Gate** to explore the supplied three-scene sample.
Use **Render preview** to produce and play a draft, then try a new story with your
own text and media. Sample projects are examples, not requirements for a new story.

**Beginner guide:** [TUTORIAL.md](TUTORIAL.md) explains fresh-PC setup, offline
production, optional APIs/MCP and manuscript production step by step.

## Manuscript production

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

Production runs support narrated illustrations, animated cartoons and realistic
cinematic footage. Cartoon/cinematic formats assemble generated video clips;
they require a video-capable connection. Each run creates a new story in one
format. Resume reuses completed stages and saved provider task IDs; unknown
submission outcomes need inspection and an explicit retry. Optional plan review
pauses before media generation.

The source importer accepts files up to 20 MiB and 2 million extracted characters.
The guided workflow supports 1–24 episodes and up to 100 shots per episode. Its
generation-stage limit controls new stages, not provider charges. It does not
automatically upload or publish videos.

## Optional connections and models

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

## Editing and production controls

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

Git excludes local session/connection settings, generated job history,
Python environments/bytecode, build output and rebuildable render caches/locks. The application
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
.\.venv\Scripts\python.exe -m pip install --upgrade "pip>=26.2,<27"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m src.doctor
.\.venv\Scripts\python.exe -m src.app
```

`Setup.ps1` performs the Python environment/dependency steps and checks FFmpeg;
`Start-Studio.ps1` prefers that virtual environment when present. FFmpeg may
also be installed manually. Set `VNS_FFMPEG` and `VNS_FFPROBE` to full executable
paths when PATH cannot be changed.

For an existing installation, rerun `Setup.ps1`, or update pip and install
`requirements.txt` using the commands above. Activate the environment with
`.\.venv\Scripts\Activate.ps1` before using the `python` commands below.

The core project can also be installed with `python -m pip install .`, which
provides the `video-novel-studio` command. For an installed package, select a
writable workspace explicitly, for example
`video-novel-studio --workspace D:\MyStories`. Sample projects and documentation
belong to the checkout and are not included in the Python wheel.

### Configuration

No environment variables are required when FFmpeg and FFprobe are on PATH.

| Setting | Purpose |
| --- | --- |
| `VNS_FFMPEG` | Optional full path to the FFmpeg executable. |
| `VNS_FFPROBE` | Optional full path to the FFprobe executable. |
| `--workspace PATH` / `Start-Studio.ps1 -Workspace PATH` | Select the directory containing your stories, assets, settings and exports. |
| Connection `key_env` | Name of an environment variable holding that connection's credential, as an alternative to the Windows encrypted credential store. |
| `VNS_GUI_TESTS=1` | Enable desktop interaction and playback tests; not needed for normal use. |

Connection modes are **disabled** (default), **local-only** (loopback HTTP
services) and **online** (configured remote HTTPS services). Set these in
**Connections / AI**. The core editor and renderer are available in every mode.
An MCP stdio connection launches the configured program; connection mode does
not sandbox that program. See [CONNECTIONS.md](CONNECTIONS.md) for setup and
credential handling.

After installation, application use, local speech, media importing, previewing,
and rendering require **no network connection, accounts, cloud AI, paid API,
or online inference**. To prepare dependencies for another offline machine,
download compatible wheels on a machine with the same Python/OS first:

```powershell
python -m pip download "pip>=26.2,<27" -r requirements.txt -d wheels
python -m pip install --no-index --find-links wheels --upgrade "pip>=26.2,<27"
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
3. In **Scenes / preview**, add one or more scenes. Browse to your images,
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

Keep the complete workspace when moving or backing up a project: episodes can
reference shared media in `assets/` or reusable series music. Local connection
profiles, model choices and generation/production history are excluded from Git;
include them in your own backup if you need to resume that work. Windows encrypted
credentials are stored outside the workspace and are specific to the current user.

## Code organization

The application uses **PySide6** for the desktop interface, **Pillow** for image
preparation and title cards, and external **FFmpeg/FFprobe** processes for media
decoding, mixing, encoding and verification. HTTP integrations use the Python
standard library; MCP is an optional dependency.

| Module area | Responsibility |
| --- | --- |
| `src/app.py`, `*_panels.py`, `theme.py`, `ui_widgets.py` | Desktop controls, workspace state, appearance and background jobs. |
| `scene_builder.py`, `settings.py`, `story_manager.py`, `series_tools.py` | Validated project format, file persistence, asset imports and series continuity/defaults. |
| `timeline.py`, `timeline_widget.py`, `subtitle_generator.py` | Waveforms, timeline edits and SRT/ASS captions. |
| `video_renderer.py`, `audio_manager.py`, `media.py`, `render_cache.py` | Media assembly, shot reuse, cancellation and verified export publication. |
| `publishing.py`, `exports.py`, `batch.py`, `doctor.py` | Editorial checks, export freshness, batch rendering and runtime diagnostics. |
| `src/connections/` | Provider profiles, credentials, transport, model catalogs and saved generation jobs. |
| `src/production/` | Manuscript extraction, prompt contracts, task routing and resumable stage execution. |
| `studio_mcp.py` | Optional workspace-scoped MCP server, read-only by default. |

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
python -m src.studio_mcp --workspace D:\MyStories
```

Omit `--render` to print a JSON planning summary. Batch rendering saves a
per-episode success/failure report and returns a failing exit code if any episode
fails. The pre-existing `ama_and_the_secret_heir` writing scaffold is preserved;
its example asset references need to be replaced before it can render.

The MCP command requires `python -m pip install -r requirements-integrations.txt`.
Use `--allow-drafts` to expose saving new review drafts and `--allow-render` to
expose rendering to new export files. It communicates over stdio and starts only
when explicitly launched.

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

## Further documentation

- [TUTORIAL.md](TUTORIAL.md): complete beginner walkthrough.
- [AUTOMATION.md](AUTOMATION.md): manuscript stages, prompt coverage, recovery and format limitations.
- [CONNECTIONS.md](CONNECTIONS.md): provider setup, custom HTTP/MCP tools and model routing.
- [UI_WORKSPACE.md](UI_WORKSPACE.md) and [UI_REFRESH.md](UI_REFRESH.md): desktop layout and appearance examples.
- [PROJECT_REVIEW.md](PROJECT_REVIEW.md): current bug fixes, regression checks and remaining gaps.
- [REVIEW_REPORT.md](REVIEW_REPORT.md), [MODEL_CATALOG_REVIEW.md](MODEL_CATALOG_REVIEW.md) and [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md): earlier reviews and recorded verification scope.
