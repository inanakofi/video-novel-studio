# Connections upgrade verification — 1.2.0

Verified on 2026-10-11 in `J:\storyline\video-novel-studio`.

## Result

**69 automated tests passed in 69.513 seconds**, including desktop interaction,
real FFmpeg renders, installed Windows narration, and both MCP transports.
Command: `$env:VNS_GUI_TESTS='1'; python -m unittest discover -s tests -v`.
The captured output is [verification/connections-tests.txt](verification/connections-tests.txt).
`python -m src.doctor` passed and `python -m pip check` reported no broken requirements.

Before the initial Git commit, a clean copy exported from the Git index passed
**70 tests in 69.264 seconds** using the installed Python/media dependencies.
The copy contained no session settings, connection profiles, generation history
or render caches. Required setup files, guides, templates and sample media were
present. An additional desktop regression verifies that the export list opens
the MP4 in the copied workspace rather than its historical absolute path.
See [verification/fresh-checkout-tests.txt](verification/fresh-checkout-tests.txt).

## Real export and playback

The desktop application rendered
[connections_and_video_demo_episode_001.mp4](exports/connections_and_video_demo_episode_001.mp4)
from three scenes: two still scenes (including layered parallax) and a trimmed
video scene. This used the existing installed-Windows-voice WAVs, local music
and a local sound effect. Python socket connections were blocked during the
desktop render. Provider connections remained disabled.

| Measurement | Actual result |
|---|---|
| Video | H.264 High, yuv420p, 1080 × 1920, 30 FPS |
| Audio | AAC, 48 kHz, stereo |
| Video duration | 75.000 seconds |
| Audio end | 75.000 seconds |
| Captions | 18; last caption ends at 69.410 seconds |
| Full FFmpeg decode | Passed |
| Real desktop player | Decoded frames at 8, 33, 60 and 74 seconds; no player error |
| Render time | 107.701 seconds, five uncached shots |

MP4 SHA-256:
`d83d52f7f077f88763eb5fa68b749b4b47f03866c0a5203cb5198bf719fa122a`.

The middle clip was animated from original CC0 artwork using FFmpeg. It is not
AI-generated video. Playback automation was muted; stream/PCM tests and decode
checks validate audio technically, not by a human listening. Automatic captions
remain proportionally timed within actual narration clips, with manual waveform
editing available for more precise synchronization.

Evidence: [machine-readable release results](exports/verification/connections-release.json),
[FFprobe export report](exports/connections_and_video_demo_episode_001.verification.json),
[connection settings](exports/verification/connections-settings.png),
[prompt review](exports/verification/connections-prompt-review.png), and
[actual playback](exports/verification/connections-mixed-video-playback.png).
`tools/verify_connections_release.py` reproduces the production verification.

## What was tested

- OpenRouter model discovery, chat request shape, structured script review,
  provider usage metadata and explicit script application through desktop widgets.
- Ollama and OpenAI-compatible text request/response dialects.
- ElevenLabs MP3 response handling with actual FFprobe validation; invalid audio
  is not marked ready.
- ComfyUI API graph substitution, queue/history processing and real image download.
- Runway submit/task/download flow, interrupted jobs and resume without a second
  submission. Cancellation during submission still preserves a returned task ID.
- Disabled mode refuses connection operations before DNS or HTTP. Loopback-only
  restrictions, HTTPS requirements, redirect rejection, credential-origin
  checks, encrypted Windows credential roundtrip/deletion and absence of keys
  from profile/job files.
- HTTP 429 errors do not retry or create a successful job. Invalid script JSON
  is reviewable but cannot be applied. Generated asset paths are never accepted
  as filesystem instructions.
- Actual generic HTTP requests to a local server.
- Actual MCP subprocess discovery, read tools and draft creation with the Studio
  server; existing episode files remain unchanged. Actual Streamable HTTP
  discovery/calls and a tool failure with its useful error preserved.
- Studio MCP path containment and opt-in draft/render capabilities.
- Real mixed video/still FFmpeg exports, Unicode/spaces in paths, aspect-preserving
  output, timing, codecs, clip bounds, cached rerenders and video thumbnails.
- Desktop flow: add/save/test OpenRouter profile, generate fixture response,
  review/apply with backup, import video, disable connections, render offline,
  reopen and recover saved profiles/jobs.
- All previous offline editing, timeline, publishing, narration, caption,
  continuity, cache, interrupted render and rollback tests still pass.

The provider tests use deterministic local HTTP fixtures. Their media are real
PNG/MP3/MP4 files made locally for testing; their text is predetermined test data.
These tests verify adapters, not model quality, live billing, credentials or
inference capabilities.

## Still requires live verification

No real API keys were supplied and no billed generation was attempted. OpenRouter,
OpenAI-compatible cloud services, ElevenLabs and Runway still require a user
credentialed generation test. No Ollama or ComfyUI model service is installed;
their real model/workflow compatibility and generation quality remain untested.
MCP compatibility was tested with the official SDK and Studio's own server;
individual third-party servers can impose additional requirements.

## Environment and dependencies

Windows 10 build 19045; Python 3.14.2; Pillow 12.1.0; PySide6 6.10.1;
FFmpeg/FFprobe 9.0 full build; optional MCP SDK 2.3.0. AI HTTP adapters use the
Python standard library. MCP is pinned in `requirements-integrations.txt` and
the `integrations` package extra; it is not required by the offline application.

The desktop is configured with disabled provider presets, including OpenRouter,
and no stored production credentials. Setup, supported provider options,
recovery and limitations are documented in [CONNECTIONS.md](CONNECTIONS.md).
