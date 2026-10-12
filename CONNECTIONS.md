# Optional AI and software connections — version 1.2

**Manuscript automation:** the new **Manuscript → videos** page can route analysis,
writing, review, speech, images and video through these profiles. Starting that
workflow applies outputs to a new story automatically; the individual Generate
page below still saves drafts for explicit review/apply. HTTP/MCP profiles can
advertise production capabilities through `options.production`. See the
[complete tutorial](TUTORIAL.md#part-d--use-mcp-or-a-custom-http-service) for
argument templates, result contracts, reference inputs and optional lip-sync.

The studio still works offline. Connections start **Disabled**, each profile has
its own enable switch, and no model discovery or network connection happens at
startup. Normal editing, recorded narration, Windows speech, subtitles and
FFmpeg exports do not import an AI SDK or require an account.

## Available adapters

| Connection | Implemented capability | Required from you |
|---|---|---|
| **OpenRouter** | All-modality model discovery, text, images, MP3 speech, asynchronous video, usage/cost metadata when returned | API key and a model with the required output capability |
| Ollama | Installed-model discovery, story and structured script drafts | Running Ollama with a downloaded text model |
| OpenAI-compatible / open model server | `/models`, `/chat/completions`, `/images/generations`, `/audio/speech` | A server implementing the selected task's endpoint, models and credentials if required |
| ElevenLabs | Speech-model and voice discovery, MP3 narration generation | API key, voice ID and a compatible speech model |
| ComfyUI | Workflow model discovery, queue, poll and download saved image/video outputs | Running ComfyUI, installed models/nodes and an API-format workflow |
| Runway | Submit text-to-video, poll a saved task ID, download MP4 | API key, text-to-video model ID and model-compatible duration/ratio |
| JSON HTTP API | Explicit GET/POST/PUT/PATCH/DELETE requests and JSON results | API endpoint and optional Bearer key |
| MCP stdio / Streamable HTTP | Tool discovery, schema inspection and explicit tool calls | Optional MCP dependency and a trusted server |

These are adapters, not bundled models. OpenRouter uses `/images`, `/audio/speech`
and `/videos` for media. Video task IDs are saved before polling so Resume does
not submit another generation. Music/audio-only models are excluded from the
Speech picker; use a model advertising **speech** output for exact narration.

Protocol fixtures exercise requests, response parsing, real media downloads,
error handling and recovery. On 2026-10-12, live OpenRouter tests using the supplied
CEO manuscript produced a valid structured script with `openrouter/free` and
playable MP3 speech with `fish-audio/s2.1-pro-free:free`. The zero-priced Ming image
model was rejected with HTTP 402 because the test account had never purchased
credits. No complete AI video was produced. See
[live results](exports/verification/openrouter-models-live.json). Video generation
is covered by protocol fixtures; it was not tested with a paid live model.
Actual local AI inference also remains untested because no Ollama/ComfyUI model
service is installed here. Real MCP stdio and HTTP calls, local media rendering,
Windows key encryption, and the desktop workflow have been exercised.

## Connect OpenRouter

1. Open **Connections / AI → Connections**. Select the OpenRouter profile, or
   select OpenRouter in the preset menu and click **Add connection**.
2. Select **Online and local services**, enable the profile, and enter your
   key in **Secure API key**. The preset URL is
   `https://openrouter.ai/api/v1`.
3. Click **Save & test / discover**. Discovery caches model IDs, output
   capabilities, prices and open-weights metadata. A default model is optional.
   Use **Free only** or **Open weights / local** to narrow suggestions.
4. Open **Generate**, choose OpenRouter, the task and **Model for this task**, describe
   what you want, and optionally include the current script, bibles or continuity.
5. Click **Build prompt for review**. The editable prompt is the text that will
   be transmitted. For scripts it includes the structured output instructions.
   Changing the instruction/context checkboxes later requires rebuilding it.
6. Click **Generate and save for review**. Review the saved result in
   **Jobs / review**. Edit it and choose **Apply reviewed result to current
   episode** when ready. Applying is a separate local action.

Optional text parameters go in Provider options, for example:

```json
{"generation": {"temperature": 0.7, "max_tokens": 2000}}
```

Models differ. Some use `max_completion_tokens` instead of `max_tokens` or
reject `temperature`. Leave options empty if unsure, then consult that model's
documentation. OpenRouter model lists are fetched only when requested, not hardcoded.
Provider-reported usage/cost is saved with the job; there is no universal price
estimate or account spending cap in this release. Set limits with your provider.

OpenRouter's documented interface uses Bearer authentication and its normalized
chat-completions response. See the [official OpenRouter API reference](https://openrouter.ai/docs/api/reference/overview).

## Reuse a platform across tasks

Save **one connection per API key**. In **Manuscript → videos**, each task has a
connection selector and a searchable model selector. Analysis, Scripts and
Quality review can use different models through the same connection/key, or the
same model. Illustrations, Speech and Video can share that connection too, using
models that generate those outputs. Blank model uses the connection's default.
Blank Scripts/Quality review connection inherits Analysis and its model unless
you choose a model override. **Save task choices** restores these choices next time.

**Use Analysis model for all text tasks** copies the model/key to writing and
review. **Use Analysis platform for supported tasks** also selects that platform
for media tasks and displays matching catalog models. Review those choices
before starting. Filters narrow suggestions; existing choices and manually typed
IDs remain available. A zero listed price does not guarantee account access.

For multiple keys on the same platform, add more connections, or use **Duplicate
with same key** and replace the copied key. Duplication copies the credential into
a separate encrypted vault entry; later key changes affect only that copy. An
environment-variable credential keeps referring to the same variable until you
change its name. Model discovery is cached per provider/base URL and reused by
OpenRouter connections to that endpoint. Other catalogs are isolated by connection;
ComfyUI lists also follow the configured workflow. No discovery occurs automatically
at startup.

**Show all models** clears both price and license filters without replacing your
chosen model. Each manuscript task shows **displayed / total** model counts.
**Refresh model catalogs** in manuscript setup or Generate refreshes all enabled
generation connections in the background. Failed refreshes preserve cached lists
and show the failure. Compatible servers with `has_more`/`last_id` pagination are
read through the final page. Lists are searchable and have no item-count limit.

ElevenLabs speech choices come from `/models` and its `can_do_text_to_speech`
capability, separately from voice IDs. ComfyUI choices come from `/object_info`
for the workflow inputs containing `{{model}}`; one selection must satisfy all
such inputs. A fixed-model workflow needs no model override. Runway has no standard
model-list endpoint: its 16 text-to-video suggestions were checked against the
[official SDK schema](https://github.com/runwayml/sdk-python/blob/main/src/runwayml/types/text_to_video_create_params.py)
on 2026-10-12. Set duration and ratio to values accepted by the chosen model;
these suggestions do not establish account access and may need updating.

HTTP/MCP tools can provide their full model choices in `options.models`, alongside
their existing `production` templates. This also supports the Lip-sync selector:

```json
{"models": [
  {"id": "your-speech-model", "output_modalities": ["speech"], "tasks": ["voice"]},
  {"id": "your-lipsync-model", "output_modalities": ["video"], "tasks": ["lipsync"]}
]}
```

Use the exact IDs supported by that tool. Simple model-ID strings are also accepted.
When a server omits output capabilities, its full list remains selectable and the
tooltip labels compatibility as unknown. A model's presence does not guarantee
quota, permissions, price, or support for every generation parameter.

Open models work through Ollama for text, compatible servers for text/image/speech,
ComfyUI workflows for image/video, or your HTTP/MCP tools. Open weights are inferred
from the platform's model repository metadata and are distinct from free pricing;
check each license. Enter local model IDs manually when the server's catalog does
not advertise modalities. In ComfyUI, put `{{model}}` in the checkpoint/model input
to use task model selection; otherwise the workflow keeps its configured model.

Optional OpenRouter media options:

```json
{
  "image_generation": {"aspect_ratio": "9:16", "output_format": "png"},
  "voice_id": "your-model-supported-voice",
  "speech_generation": {"instructions": "Warm, clear delivery"},
  "video_generation": {"duration": 5, "aspect_ratio": "9:16"}
}
```

Use options the selected model supports. Speech has a per-task voice ID field;
blank keeps the connection's voice/default. See the official
[Image API](https://openrouter.ai/docs/guides/overview/multimodal/image-generation),
[Speech API](https://openrouter.ai/docs/guides/overview/multimodal/tts), and
[Video API](https://openrouter.ai/docs/guides/overview/multimodal/video-generation).

## Local AI, voice and video

**Ollama:** install/run Ollama separately and download a model before offline use.
Choose **Local services only**, enable the Ollama profile and use
`http://127.0.0.1:11434`. Test/discover lists locally installed models. Choose one
and save. No model is downloaded by Studio. The adapter uses
[`/api/generate`](https://docs.ollama.com/api/generate) with streaming off.

**ElevenLabs:** enable online mode, enter a key, then Test/discover to retrieve
voices. The response is shown in **Software tools**. Copy a `voice_id` into the
Voice ID field; optionally enter a supported speech model ID. Select **voice**
under Generate and put **only the words to speak** in the reviewed prompt.
Studio requests MP3, probes the downloaded recording, and saves it for review.
Applying it updates the selected scene's narration text and voice reference.
Existing durations stay intact: use **Fit to audio** and regenerate/review
captions as needed. Recorded imports and Windows speech remain available.
See [ElevenLabs Create speech](https://elevenlabs.io/docs/api-reference/text-to-speech/convert).

**ComfyUI:** use `http://127.0.0.1:8188` in local mode. Export a working workflow
in **API format**, then load it with **Load ComfyUI workflow**. In the resulting
`options.workflow` JSON, replace the positive-prompt text input with
`{{prompt}}`. Do not change connected-node arrays or node IDs. Save the profile.
All other workflow parameters are sent as configured. The workflow must already
have its models and custom nodes installed. A normal canvas/workflow JSON file
with a `nodes` array is not the API graph and is rejected.

Use a SaveImage node for images, or an installed video-saving node whose history
returns MP4/WebM/MOV/MKV files under `images`, `gifs` or `videos`. Choose the
matching **image** or **video** task. Studio submits `/prompt`, polls
`/history/{prompt_id}` and downloads through `/view`. It does not install nodes,
fetch weights or run an arbitrary workflow locally itself. GIF-only video
outputs, latent previews and archives are not imported as video scenes.
See [ComfyUI server routes](https://docs.comfy.org/development/comfyui-server/comms_routes).

**Runway:** use the preset, your key and a supported text-to-video model ID.
For example, the documented `gen4.5` contract accepts vertical `720:1280` output;
Provider options can contain `{"duration": 5, "ratio": "720:1280"}`. Model
availability, allowed settings and pricing are provider-controlled. This adapter
implements text-to-video; image-reference uploads and video-to-video are not
implemented. It uses the documented API version header and saves the returned
task ID before polling. See [Runway's API](https://docs.dev.runwayml.com/api/)
and its [official SDK text-to-video contract](https://github.com/runwayml/sdk-python/blob/main/src/runwayml/resources/text_to_video.py).

## Review, storage and recovery

- Profiles and selected mode are in `.studio_connections.json`. Stored keys are
  encrypted with Windows user-scoped DPAPI under
  `%LOCALAPPDATA%\VideoNovelStudio\credentials`, outside project files. The app
  never displays a saved key. Leaving the key field blank keeps the old key;
  **Remove stored key** deletes it. On other operating systems, use a credential
  environment variable and enter its name in the profile. Keys are not portable
  between Windows accounts/machines.
- Prompts, provider settings, returned usage, status and outputs are local files
  under `.generation_jobs/<id>/`. These contain story content; treat them as
  project data. Profiles/jobs are ignored by Git. Never put keys into prompts,
  URLs, Provider options, MCP arguments or HTTP bodies.
- **Stop / Cancel job** stops waiting. It does not claim to cancel a remote
  generation. An in-flight HTTP request can take up to its 120-second socket
  timeout to return. Runway/ComfyUI jobs with saved IDs can be resumed without
  submitting another generation. Polling stops after 30 minutes.
- Text and speech requests do not have a resumable task interface here. If a
  connection dies during submission, Studio reports `failed_or_unknown`.
  Check provider history before clicking Generate again; there are no automatic
  retries of potentially billable submissions.
- A hard crash can leave `running.lock` in a job folder. Confirm no Studio
  worker is using that job before removing **only that lock file**, then resume
  the saved provider task. Do not resubmit just to clear a lock.
- Results are never automatically applied. Script output is validated as
  structured data and cannot choose asset paths. Applying a script reuses visuals
  by scene position, resets narration references and automatic captions, and
  stores visual directions in metadata. Record or generate new narration.
  Invalid model JSON remains editable in review but cannot be applied.
- Applying a story/script/media result backs up existing scene JSON, script,
  SRT and series bible under `episode/drafts/before_apply_<id>/`. A story result
  replaces the current series bible. Media imports copy into the selected
  episode's assets folder. Applying media preserves scene duration; run asset
  checks and fit/adjust timing before rendering.
- **Import text draft for review** also accepts local `.json` structured scripts
  and `.md`/`.txt` series-bible drafts, including drafts produced by another app.

## Video scenes

Browse for an MP4/MOV/MKV/WebM in **Scenes / preview**. The editor recognizes the
media type, extracts a real thumbnail and supports a trim start. Set camera
motion to **static** for video: motion is already in the clip. Foreground
parallax is available for still scenes only. Use **Fit scene to remaining video**
or set a shorter scene duration. The renderer rejects a scene that runs beyond
the available clip instead of silently looping it or cutting narration.

```json
{
  "scene_id": 2,
  "duration_seconds": 6,
  "visual_asset": "assets/courtyard.mp4",
  "media_type": "video",
  "video_start_seconds": 1.5,
  "video_audio_volume": 0,
  "narration": "Ama opened the letter.",
  "narration_audio": "assets/scene_002.wav",
  "camera_motion": "static",
  "subtitle_style": "cinematic",
  "transition": "crossfade",
  "transition_seconds": 0.5
}
```

Original clip sound is muted at volume 0. A value from 0 to 1 enables it and
automatically ducks it beneath narration; a positive setting requires an audio
track. Aspect ratio is preserved with a centred fill/crop. Output is constant
frame rate, with the same transitions, subtitle system, cache and FFprobe/full
decode verification used for still scenes. Existing scene files default to
`media_type: image`. Generated media must be downloaded before offline rendering.

The new **Connections and Video Demo** series includes a real 75-second
1080×1920 MP4 with a video scene. Its clip is an FFmpeg animation of the original
CC0 sample artwork, **not AI-generated**. Narration reuses the tested installed
Windows voice. See [SAMPLE_ASSETS.md](SAMPLE_ASSETS.md).

## Connect other software

**HTTP APIs:** add a JSON HTTP API profile with the base URL, optional Bearer key,
and mode. In **Software tools**, select the profile, method, relative path and
JSON body, then click **Call selected tool / HTTP endpoint**. GET sends no body.
This is a JSON client, not a universal adapter for OAuth, multipart uploads,
GraphQL schemas or proprietary binary protocols. Results are displayed for
inspection; they are not executed or automatically applied to a story.

**MCP:** optional client/server support uses the official Python SDK. Install it
in the same environment you use to start Studio:

```powershell
python -m pip install -r requirements-integrations.txt
# If you used Setup.ps1:
.\.venv\Scripts\python.exe -m pip install -r requirements-integrations.txt
```

For a local MCP server, add **MCP local program** and configure Provider options:

```json
{
  "command": "C:/path/to/python.exe",
  "args": ["-m", "some_mcp_server"],
  "cwd": "C:/path/to/server"
}
```

Use an executable and separate arguments, not a shell command string. To pass
the stored key to the child, add `"credential_env": "EXPECTED_KEY_NAME"`.
Only a small default OS environment plus that explicit credential is inherited.
External executables run with your user's permissions and may access the network
independently. They are not sandboxed by Studio's local HTTP restriction.

For **MCP Streamable HTTP**, enter the full `/mcp` endpoint and an optional
Bearer key. OAuth login, legacy SSE-only endpoints, model sampling and server
elicitation are not implemented. Choose **List MCP tools**, inspect the selected
tool's description/input schema, enter a JSON argument object and click **Call**.
No language model automatically chooses or invokes tools. Each action uses a
fresh MCP connection; the client does not preserve server-side sessions between
separate UI actions. See the [official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk).

Other apps can connect to Studio's real **stdio MCP server**, for example:

```json
{
  "mcpServers": {
    "video-novel-studio": {
      "command": "C:/path/to/python.exe",
      "args": ["-m", "src.studio_mcp", "--workspace", "J:/storyline/video-novel-studio"],
      "cwd": "J:/storyline/video-novel-studio"
    }
  }
}
```

Client configuration syntax varies; use its equivalent command/arguments/cwd
fields. Studio exposes `list_stories`, `get_episode` and `validate_episode` by
default. Add `--allow-drafts` to expose `save_script_draft` (new files only), and
`--allow-render` to expose `render` (a new verified export). Paths and referenced
assets must stay inside the configured workspace. The server never starts with
the desktop and has no shell-execution or arbitrary file-writing tool. A client
that launches it explicitly controls that process; the desktop's connection
mode does not control a separately launched server.

## Boundaries and troubleshooting

- Local-only HTTP accepts loopback/localhost; remote endpoints require HTTPS.
  Redirects are rejected, and authentication is not forwarded to downloaded
  media hosts. JSON responses are bounded to 16 MiB, speech responses to 64 MiB,
  and media downloads to 512 MiB. Signed direct media URLs work; a provider that
  returns redirect-only URLs may require a future adapter update.
- HTTP 401/403: check the key, endpoint, permissions and provider account.
  HTTP 429: check the provider's quota/limits before explicitly trying again.
  Provider error bodies are not logged because they can contain sensitive data.
- ComfyUI missing nodes/models or unsupported output: run the same API workflow
  in ComfyUI and inspect its node/history errors. Studio does not claim success
  until it downloads and validates the requested media type.
- No connection: confirm the local service is actually running and the port is
  correct. Merely selecting Ollama/ComfyUI does not install or start them.
- Rendering remains available if any provider or MCP dependency is absent.
  Automatic caption timing is still proportional to recorded speech duration,
  not speech recognition or forced alignment. Use the waveform to refine it.
