# Runtime and model catalog review — 12 October 2026

The final full suite passed **132 tests in 110.315 seconds, with no failures or
skips**. The project virtual environment now starts the desktop application and
passes the environment doctor and dependency checks.

## Changes

- Restored missing PySide6 6.10.1 and Shiboken packages into `.venv` from the
  intact local Python installation, checking the installed RECORD hashes.
  Installed the declared optional MCP dependencies and Ruff. Large PySide6
  downloads timed out before the local recovery.
- Added **Show all models**, **Refresh model catalogs**, and visible
  **displayed / total** counts. Cleared the workspace's saved price/license
  filters while preserving its connection and model choices.
- Kept the complete OpenRouter all-modality catalog; followed paginated
  compatible-server catalogs through the last page, removed duplicate IDs, and
  preserved cached lists on failed or malformed refreshes.
- Added ElevenLabs synthesis-model discovery separately from voice discovery.
  A denied voice-list request no longer prevents successful model discovery.
- Added ComfyUI choices from the configured workflow's `{{model}}` inputs.
  Model choices shared by several inputs must satisfy every such input.
- Added 16 documented Runway text-to-video suggestions and configurable
  HTTP/MCP model lists, including task-specific lip-sync choices. Runway's
  suggestions are dated; these services do not share a universal discovery API.
- Isolated private catalogs by connection and ComfyUI catalogs by workflow.
  OpenRouter's public catalog remains shared between keys at the same endpoint.
- Prevented unknown speech prices from being labelled free and ignored damaged
  cached model metadata that could otherwise break selectors.
- Fixed production preflight to honor the task's chosen voice ID when the
  connection has no default voice ID.
- Replaced a fixed 900 ms playback-test delay with a bounded wait for a real
  displayed frame. The initial full run failed this timing assertion; the same
  workflow passed independently before the wait adjustment. No player behavior
  was changed to satisfy the test.

## Full live catalog and UI verification

A read-only OpenRouter refresh returned **659 unique models**. Every ID with the
matching output capability was compared against the actual task dropdown:

| Task | Models displayed | All matching IDs present |
| --- | ---: | --- |
| Analysis / planning | 458 | Yes |
| Scripts | 458 | Yes |
| Quality review | 458 | Yes |
| Illustrations / references | 61 | Yes |
| Speech | 32 | Yes |
| Animated / cinematic video | 30 | Yes |

These counts overlap for models supporting several outputs. Other catalog
outputs, such as embeddings and transcription, are not generation tasks in this
application. Music/audio-only output is not treated as speech synthesis.
Lip-sync uses the configured tool's model IDs; it has no built-in universal list.

Evidence: [live catalog counts](verification/project-review-live-catalog.json),
[exact UI comparison](verification/project-review-live-ui.json), and
[native selector screenshot](verification/project-review-models.png).

## Validation

- [Full test output](verification/project-review-tests.txt): 132 passed, including
  native desktop editing/playback, model selection, actual Windows speech,
  verified FFmpeg renders, recovery/cancellation, and local HTTP/MCP servers.
- Catalog regressions cover 840 provider records, more than 200 choices per task,
  pagination, cache recovery, malformed metadata, private catalog isolation,
  custom task lists, cancellation, and task voice routing.
- Environment doctor, `pip check`, source Ruff checks (`F,E9`), test/tool Ruff
  checks (`E9,F63,F7,F82`), Python compilation, and Git whitespace checks passed.
- All three completed demo projects passed asset and caption validation.
- Existing stories, exports, credentials, and pre-existing working-tree edits
  were preserved. Tests use temporary projects; historical screenshots and
  desktop verification data were restored after the tests.

## Remaining limits

Three existing draft episodes still need their intended source assets:

| Draft | Incomplete content |
| --- | --- |
| `ama_and_the_secret_heir/episode_001` | Two images and a complete narration recording; the current recording is only 0.25 seconds. |
| `ama_and_the_secret_heir/episode_002` | One image and `narration.wav`. |
| `fiifi/episode_001` | `assets/scene_001.png`. |

See the [current asset audit](verification/project-review-assets.json). These are
content gaps; those drafts cannot render successfully until the files are supplied.

This review made **zero live generation requests**. Catalog listing verifies
discovery, not account quotas, billing access, or successful inference by every
model. Non-OpenRouter discovery uses protocol tests; no live ElevenLabs, ComfyUI,
Runway, or local inference service was exercised. Runway models need compatible
duration/ratio settings. Compatible servers that omit capabilities expose their
full list with an unknown-compatibility tooltip. Custom tools require their exact
model list in `options.models` or manually entered IDs.

Provider contracts checked against the [OpenRouter model API](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties),
[ElevenLabs model API](https://elevenlabs.io/docs/api-reference/models/list),
[ComfyUI server routes](https://docs.comfy.org/development/comfyui-server/comms_routes),
and [Runway's official SDK schema](https://github.com/runwayml/sdk-python/blob/main/src/runwayml/types/text_to_video_create_params.py).
Setup and custom model-list examples are in [CONNECTIONS.md](CONNECTIONS.md#reuse-a-platform-across-tasks).
