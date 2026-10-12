# Video Novel Studio: from a fresh PC to a finished video

This guide teaches two complete ways to make a video: **offline production**, using your own writing and local assets, and **connected production**, using AI APIs, local models or MCP tools. It also walks through the **Manuscript → videos** automation workflow.

You do not need to know Python to use the editor. Commands below are installation or troubleshooting steps. Run them in **PowerShell**, one block at a time. Replace `C:\VideoNovelStudio` with the folder where you put this project.

## Contents

1. [What you will make](#1-what-you-will-make)
2. [Install on a fresh Windows PC](#2-install-on-a-fresh-windows-pc)
3. [Understand the workspace](#3-understand-the-workspace)
4. [Part A — make a complete video offline](#part-a--make-a-complete-video-offline)
5. [Part B — connect AI APIs and local models](#part-b--connect-ai-apis-and-local-models)
6. [Part C — automate a manuscript into videos](#part-c--automate-a-manuscript-into-videos)
7. [Part D — use MCP or a custom HTTP service](#part-d--use-mcp-or-a-custom-http-service)
8. [Review, export and back up](#review-export-and-back-up)
9. [Troubleshooting](#troubleshooting)

## 1. What you will make

An episode is a sequence of scenes or shots. Each shot has an image or video, an optional recording, text for captions, and a duration. Studio combines these with transitions, cards and optional music/effects, then produces a real MP4.

| Video type | What supplies the picture | What Studio does |
|---|---|---|
| Narrated visual novel | Illustrations or photographs | Pan/zoom, narration, captions, transitions and assembly |
| Animated cartoon | Actual animated clips from an animation tool or video model | Clip assembly, dialogue recordings, captions and export |
| Realistic cinematic series | Actual filmed or generated cinematic clips | Clip assembly, dialogue recordings, captions and export |

Moving a still image is not character animation. The cartoon and cinematic choices in automation require a video-capable connection. Precise mouth movement requires an additional lip-sync tool that accepts the final audio and video; selecting a format alone cannot create that capability.

For your first project, make **one 30–60 second narrated episode**. Once you can hear, see and export it correctly, increase the episode count or try generated video. A long novel cannot fit unabridged into a one-minute episode; that setting requests a condensed adaptation.

The automatic workflow handles analysis, planning, scripts, textual quality review, speech, image/video generation, captions and rendering. Music, Foley, custom animation rigs, frame-perfect identity consistency and automatic publishing are not bundled. You can add licensed music/effects in the editor after generation. A verified MP4 still needs someone to watch it for creative quality.

## 2. Install on a fresh Windows PC

### 2.1 Prepare the computer and project folder

You need a current Windows PC, a writable folder, Python, FFmpeg/FFprobe, and the complete project. An ordinary CPU can edit and render; local AI models have separate RAM/GPU requirements. Leave room for original media, generated files, temporary renders and final exports. Video models can require substantially more hardware and storage than Studio itself.

1. Download or copy the **whole project**, including `src`, `stories`, `templates`, `requirements.txt`, `Setup.ps1` and `Start-Studio.ps1`.
2. If you received a ZIP, extract it first. Do not run the app inside the ZIP preview.
3. Put it somewhere writable, for example `C:\VideoNovelStudio`. Avoid `Program Files` for a working project.
4. Open that folder in File Explorer. Type `powershell` into the address bar and press Enter. This opens a terminal in the project folder.
5. Confirm the location:

```powershell
Get-Location
Get-ChildItem requirements.txt, Setup.ps1, Start-Studio.ps1
```

You should see the three files. If they are missing, enter the extracted project subfolder before continuing.

### 2.2 Install Python

Install a **64-bit Python 3.14 release** from the [official Python Windows downloads](https://www.python.org/downloads/windows/). Studio's verified development environment uses Python 3.14.2; the project declares Python 3.10 or newer. Use the regular installer/runtime, not the embeddable ZIP. When offered, enable the option that makes Python available from the terminal.

Close and reopen PowerShell after installation, then run:

```powershell
python --version
python -m pip --version
```

Both commands should print version information. If `python` opens a store page or is not found, use the Python installer's configuration/repair options and open a new terminal. If `py -3.14 --version` works, you can use `py -3.14` instead of `python` to create the environment in the manual setup below.

### 2.3 Install FFmpeg and FFprobe

FFmpeg creates the video and mixes audio. FFprobe reads the resulting media. Both must be installed. The [FFmpeg download page](https://www.ffmpeg.org/download.html) links Windows builds.

If Windows Package Manager is available, the existing project setup supports this installation approach:

```powershell
winget install --id Gyan.FFmpeg --exact
```

Alternatively, download a Windows build linked by FFmpeg, extract it, and add its `bin` folder to your **user PATH** through Windows' environment-variable settings. Choose a build with H.264, AAC and subtitle rendering support. The doctor command below checks the actual required features.

Open a **new** PowerShell window and run:

```powershell
ffmpeg -version
ffprobe -version
```

Both must print version information. If you cannot change PATH, set the executable paths in the same terminal used to launch Studio:

```powershell
$env:VNS_FFMPEG = 'C:\Tools\ffmpeg\bin\ffmpeg.exe'
$env:VNS_FFPROBE = 'C:\Tools\ffmpeg\bin\ffprobe.exe'
```

Change those paths to the actual extracted files. These assignments last only for that terminal session.

### 2.4 Install Studio's dependencies

Return to the project folder:

```powershell
Set-Location -LiteralPath 'C:\VideoNovelStudio'
.\Setup.ps1
```

The setup script creates `.venv`, installs the packages in `requirements.txt`, and runs the environment check. The first setup normally needs internet access to download Python packages. Successful setup ends with a message telling you to start Studio.

If PowerShell blocks local scripts, you can use the equivalent direct commands without changing your machine's execution policy:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m src.doctor
```

The doctor output should include `"required_media_features": "available"`. It also lists installed Windows speech voices. An empty voice list means you must install a compatible Windows voice or import your own recording; it does not prevent video rendering.

### 2.5 Start the app and test the installation

```powershell
.\Start-Studio.ps1
```

If scripts are blocked, use:

```powershell
.\.venv\Scripts\python.exe -m src.app
```

1. Select **The Letter at the Gate** in the story library.
2. Select its first episode.
3. Click **Check assets**. Read any error in the bottom status/log area.
4. Click **Render preview · 360p**.
5. Wait for verification, then use **Play / pause**. Confirm that the video has images, speech and readable captions.

This sample test separates installation problems from problems in a new project. You do not need to connect an AI provider to complete it.

### 2.6 Prepare a PC that will remain offline

On an internet-connected PC with the **same Windows architecture and Python version** as the offline machine:

```powershell
python -m pip download -r requirements.txt -d wheels
```

Copy the project, `wheels` folder, Python installer and FFmpeg build to removable storage. On the offline PC, install Python/FFmpeg first, then:

```powershell
Set-Location -LiteralPath 'C:\VideoNovelStudio'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --find-links wheels -r requirements.txt
.\.venv\Scripts\python.exe -m src.doctor
.\.venv\Scripts\python.exe -m src.app
```

Windows speech voices and any local AI weights must also be installed before disconnecting. Copying Studio does not install Ollama, ComfyUI, their models or their custom nodes. Plain offline editing, imported media, installed speech and rendering need none of those AI tools.

## 3. Understand the workspace

The **workspace** is the folder containing your stories, shared assets and exports. By default this is the project folder. The main areas are:

| Area | Use it for |
|---|---|
| Left story/episode library | Create or select a series and an episode |
| Scenes / preview | Import pictures/clips, edit spoken text, create/import voices, set timing and motion |
| Writing | Draft the episode and turn paragraphs into scenes |
| Story bibles | Record the world, character descriptions, locations and continuity |
| Audio / output | Choose output settings, voices, music, effects, cards and caption appearance |
| Timeline / captions | Listen, inspect the waveform and synchronize captions |
| Exports | Open finished videos and their verification status |
| Series | Save reusable presentation defaults and track characters/locations/plot threads |
| Publishing | Check technical and editorial issues before release |
| Connections / AI | Configure providers and generate individual drafts/assets |
| Manuscript → videos | Run the automated production pipeline |

If the window is narrow, use the arrows on the tab bar to reach the later tabs. **Save project** saves your editable episode. A changed project does not change an existing MP4; render again to see the edits in video.

For a separate workspace, create a writable folder and launch:

```powershell
.\Start-Studio.ps1 -Workspace 'C:\MyNovelProjects'
```

That workspace starts without the included sample stories. Keep using the same workspace path when reopening it.

## Part A — make a complete video offline

### A1. Create the story and its reference documents

1. Click **+ New story**.
2. Enter `The Letter at the Blue Gate` and a short premise when requested.
3. Click **+ New episode** and give it a title such as `The Return`.
4. Open **Story bibles**. Select each document, write the information below, and click **Save document**.

You can use this small original practice story:

> Ama returns to her childhood street to sell an empty house. At its blue gate she finds a letter from her missing brother. It tells her to look under the old courtyard lamp before sunset. She lifts the lamp's loose stone and finds a key. When she turns back, someone inside the empty house calls her name.

Write a few useful facts in each bible:

| Document | Example content |
|---|---|
| Series bible | Family mystery; warm but tense tone; Ama searches for her brother; no supernatural events have been established |
| Character bible | Ama: adult woman, short dark hair, blue coat, cautious manner; brother: missing, known through letters |
| Location bible | Blue metal gate; cream wall; courtyard lamp to the left of the doorway; sunset lighting |
| Continuity log | Ama knows her brother disappeared. She does not yet know who placed the letter. |

This is your consistency reference. When you create a new image or episode, reuse these descriptions instead of inventing the character's appearance again.

### A2. Write a speakable script

Open **Writing** and paste this example:

```markdown
# The Return

## Scene 1

Ama had come to sell the house, not to remember it. But an envelope waited at the blue gate. Her name was written in her brother's handwriting. He had been missing for three years.

## Scene 2

Inside was a single instruction: look beneath the courtyard lamp before sunset. Ama crossed the silent yard. The old stone moved under her hand. Beneath it lay a small brass key, wrapped in a strip of blue cloth.

## Scene 3

She knew the cloth. It came from the coat her brother had worn the night he vanished. Ama closed her fist around the key. Then, from inside the empty house, a voice called her name.
```

1. Read it aloud. Replace words you cannot pronounce comfortably and remove unnecessary sentences.
2. Click **Build scenes from script**.
3. Open **Scenes / preview**. You should have three scenes containing the corresponding spoken paragraphs.
4. Check the title, opening hook and cliffhanger in Writing. Edit them if needed.

The offline breakdown is deterministic: it splits paragraphs/headings and estimates scene durations. It does not invent a story, create pictures or generate recordings. Rebuilding a script later disconnects previous recordings so that old audio is not silently used for new words. Create/import the revised recordings afterward.

### A3. Create or collect the visual assets

You need one visual for each scene. For this practice video:

1. Scene 1: Ama at the gate with an envelope.
2. Scene 2: a close-up of a hand lifting the lamp's loose stone.
3. Scene 3: Ama holding the key and looking toward the doorway.

**Option 1 — use your own photographs or drawings.** Save each image as PNG or JPEG. Portrait composition is easiest for the default vertical output. Keep important faces and objects away from the extreme edges because the renderer fills the screen by cropping.

**Option 2 — make simple practice art in Paint.** Create a portrait canvas, draw a blue gate against a cream wall, save it as `gate.png`, then create a key/lamp scene and a doorway scene. Simple original artwork is enough to learn importing, timing, captions and rendering. You can replace it with better art later.

**Option 3 — reuse bundled practice assets.** For a technical exercise, browse to `stories/the_letter_at_the_gate/episodes/episode_001/assets/` and select the three `Scene … Accra.png` files in order. Read their `PROVENANCE.md` before reusing them outside this exercise. These are existing assets; selecting them does not generate new artwork.

For each scene in **Scenes / preview**:

1. Select it in the scene list.
2. Click **Browse…** beside **Scene visual**.
3. Select the matching local image.
4. Verify that the preview shows the intended image and **Media type** is `image`.
5. Click **Save project**.

The import operation copies the asset into the episode's assets folder. Do not type a guessed filename and expect Studio to create the image.

### A4. Create the narration offline

Choose one of these methods. Separate recordings per scene are easiest to edit.

**Installed Windows speech:**

1. Open **Audio / output**.
2. Choose an **Installed offline voice**. Use the normal default speed initially; negative speeds are slower.
3. Return to **Scenes / preview** and select Scene 1.
4. Confirm that **Narration** contains only the words to speak.
5. Click **Create local voice**. Wait for the WAV file to be created.
6. Click **Fit to audio** if needed. Studio measures the recording and gives the scene enough time to play it.
7. Repeat for Scenes 2 and 3.

If no compatible voice appears, use your own recording. Modern Windows voices are not all exposed through the System.Speech interface used by this feature.

**Your own voice:**

1. Use a microphone/recording application to record Scene 1 alone.
2. Leave a short natural pause at the start/end, but remove long accidental silence.
3. Save/export a WAV or MP3 named `scene_001_voice.wav` or `.mp3`.
4. Record the other scenes in separate files.
5. In Studio, select the matching scene and click **Import voice…**.
6. Listen to the recording and check that the narration text is an exact transcript.

Do not reuse an old recording after changing the spoken text. Editing the text field does not rerecord the voice. For a deliberately silent shot, clear both the narration text and its voice clip reference.

**A single continuous episode recording** is also supported through **Audio / output → Import episode voice…**. Leave individual scene voice fields empty and align scene boundaries with the recording's actual positions. Do not use this approach for your first project: rearranging scenes cannot automatically rearrange words inside one long recording.

### A5. Set pacing, motion and transitions

Select each scene and adjust:

| Control | Suggested first setting | What it changes |
|---|---|---|
| Scene duration | Measured voice duration plus a short pause | How long the shot stays on screen |
| Camera motion | `slow_zoom_in` or `static` | Movement over a still image |
| Transition in | `cut` for the first scene, optional `crossfade` later | How a scene begins |
| Caption preset | `cinematic` | Caption weight/appearance |
| Use narration text for captions | Checked | Keeps caption words tied to the spoken text |

Do not shorten a scene below the length of its recording. Studio reports an error rather than cutting off the final words. In **Audio / output**, set **Target length (seconds)** if you have a desired runtime, then use **Fit scenes to target duration**. It adjusts image holds while preserving whole per-scene recordings. If the target is impossible, shorten and rerecord the script.

Title and end cards add time. For example, 58 seconds of scenes plus a 2-second title and a 2-second ending produces 62 seconds.

**Parallax** is optional. It needs a background image plus a separate transparent foreground PNG. Import the background normally, click **Layer…** to choose the foreground, and select `parallax`. An ordinary flattened image cannot become two depth layers merely by choosing that option.

### A6. Add music, effects and cards

Open **Audio / output**:

1. Add optional title text such as `The Return` and choose a short duration.
2. Add optional end text such as `What was waiting inside?`.
3. Click **Import music…** to select a local track you are entitled to use.
4. Begin with a low music volume, such as `0.10`, and enable **Lower music automatically while narration plays**.
5. Use **+ Import sound effect…** for a paper rustle, gate creak or footstep. Set its start time and volume in the effects table.
6. Remember that sound-effect start times include the title card offset.

Music loops to cover the episode. Effects play at their scheduled positions. Listen to the rendered mix: a track that sounds quiet in isolation can still mask a voice. Studio normalizes narration and limits the mix, but it cannot decide whether a sound is artistically appropriate.

For the first export, it is fine to leave music and effects empty. A silent background makes it easier to hear mistakes in the narration.

### A7. Generate and synchronize captions

1. Open **Timeline / captions**.
2. Click **Generate captions**. Short caption groups should appear in the table.
3. Click **Load waveform** to decode the local recording.
4. Click **Listen / pause narration** and follow the words.
5. If a caption begins too early or late, edit its start/end values or drag its edges in the timeline.
6. Use **Cue start here** or **Cue end here** at the playhead for finer adjustment.
7. Click **Save timings** to retain manual timing edits. The mode becomes `manual`.

Automatic captions distribute the transcript over each measured recording. This is **not speech recognition or forced alignment**. Long pauses, emphasis and uneven delivery can need correction. Do not assume a correct transcript guarantees correct timestamps.

Keep captions within the recording's actual window; do not overlap adjacent cues. If you change the narration, order, title-card duration or scene lengths, review the captions again. Use `auto` and regenerate when you want a new starting point.

The timeline's **Play last video** shows the previous rendered MP4. It does not instantly render your latest edits. Rerender to inspect changed captions burned into the picture.

### A8. Check and render

1. Click **Save project**.
2. Click **Check assets** and fix missing pictures, audio or impossible timing.
3. Open **Publishing** and run its check. Set its acceptable duration range to match your intended episode; short practice videos may legitimately fall outside the default range.
4. Click **Render preview · 360p**.
5. Wait until verification completes. Play the entire result, including the first and last seconds.
6. Check names, pronunciation, caption timing, image crops, audio balance and the ending.
7. Make corrections, save, and render another preview only if something changed.
8. In **Audio / output**, choose the final resolution, normally `1080 × 1920`, and frame rate, normally `30`.
9. Click **Render MP4**.
10. Open **Exports**, select the finished video, and click **Play selected** or **Open exports folder**.

The export includes an MP4, an SRT subtitle sidecar and a verification JSON report. Verification checks media streams, resolution, frame rate, duration and full decoding. It does not judge story quality or prove that a character looks identical in every shot.

### A9. Make cartoon or cinematic videos offline

The editing process is the same, but you import **real clips** instead of still images:

1. Create animation in your chosen local animation software, or film your scenes.
2. Export each shot as an MP4 or another supported video format.
3. In Studio, select a scene and click **Browse…** to import the clip.
4. Confirm **Media type** is `video`. Camera motion must be `static`; the clip already contains its own motion.
5. Set **Video trim start (s)** to skip unwanted material at the beginning.
6. Use **Fit scene to remaining video**, or enter a shorter duration that fits the available clip.
7. Import matching dialogue as the scene voice clip. The visual must be long enough to cover that recording.
8. If the clip already has usable sound, adjust **Video sound (0 = mute)**. Avoid playing the same dialogue twice through both clip audio and a separate voice recording.
9. Add/review captions and render as above.

Studio does not create a character rig, animate a drawing or perform offline lip-sync by itself. You can connect local generation tools for those tasks as described next.

### A10. Continue the series

After you approve Episode 1:

1. Update the continuity log with what happened and what each character now knows.
2. In **Series**, create stable character/location records and link them to scenes.
3. Save your preferred fonts, colours, music and voice as series defaults if you want later episodes to inherit them.
4. Click **+ New episode**. Review its previous-episode context in Writing.
5. Write the next episode and repeat the asset/audio/caption/export process.

Keep filenames descriptive, but use the continuity IDs to identify recurring people and places. A character changing coat is a deliberate continuity event, not a new character.

## Part B — connect AI APIs and local models

### B1. Choose an operating mode

Open **Connections / AI** and choose the mode, then click **Save connection mode**:

| Mode | Use it when |
|---|---|
| Disabled — offline studio | You only want editing, local speech, imported assets and rendering |
| Local services only — loopback HTTP | Ollama/ComfyUI or a tool service runs on this PC |
| Online and local services | At least one task uses a remote AI API |

Local mode restricts Studio's HTTP connections to loopback addresses. A separately launched MCP program has its own operating-system/network permissions; Studio's local mode cannot prevent that program from contacting the internet. For a genuinely offline setup, use tools/models configured for offline operation and disconnect the network when testing.

A **connection profile** stores a provider, endpoint, model ID and non-secret options. Create several profiles when you want different models or voices from the same provider. For example: `Planner`, `Scriptwriter`, `Reviewer`, `Illustrations`, `Video`, `Narrator` and `Ama voice`.

Enter API keys in **Secure API key** or use **Credential environment**. Do not put keys in prompts or Provider options. On Windows, stored credentials are encrypted outside the project. A blank key field preserves the existing stored key; use **Remove stored key** to delete it.

### B2. Connect an online text model

For OpenRouter:

1. Create an API account/key with OpenRouter and set an account spending limit there if available.
2. Select **Online and local services** and save the mode.
3. Select **OpenRouter** in the provider menu and click **Add connection**.
4. Name it `Planner`, enable it, and keep the preset base URL.
5. Enter your key in **Secure API key**.
6. Click **Save & test / discover**.
7. Choose a text model from the discovered list or enter its exact model ID.
8. Click **Save connection**.

Discovery only proves that the endpoint responded. It does not prove the model can follow the production JSON contracts. Test a small draft first. The adapter follows OpenRouter's [chat-completions API](https://openrouter.ai/docs/api/reference/overview).

For another service implementing the same `/chat/completions` interface, add an **OpenAI-compatible text** profile and use that service's documented base URL, model and credential. Compatibility must include the non-streaming response format used by this app. The profile is a text adapter; it does not expose that provider's image or audio endpoints.

Optional Provider options example:

```json
{"generation": {"temperature": 0.5, "max_tokens": 8000}}
```

These values must be supported by your model. Some use `max_completion_tokens` instead of `max_tokens`; some reject temperature. A whole episode's structured script needs a larger output allowance than a short chat answer. For a novel, choose a model with enough context for bibles, prior handoffs and several source sections. Begin with a short source and small episode count, then inspect actual saved prompts before scaling up.

### B3. Connect local text generation with Ollama

Install Ollama separately using its [Windows instructions](https://docs.ollama.com/windows). Download a suitable text model while connected to the internet. Confirm that `ollama list` shows the model and that it can answer a small prompt before opening Studio.

1. Keep Ollama running.
2. Choose **Local services only** in Studio.
3. Add an **Ollama** connection named `Local planner`.
4. Use `http://127.0.0.1:11434`, enable it, and click **Save & test / discover**.
5. Choose an installed model and save the connection.

Studio calls Ollama's [`/api/generate`](https://docs.ollama.com/api/generate) endpoint without streaming. It does not download models. If the local model produces incomplete JSON or forgets earlier context, use a shorter manuscript/episode or a model with greater capacity. Local AI still needs the corresponding service running, even when the internet is disconnected.

### B4. Generate a story or script one step at a time

Before trying full automation, learn the individual generation controls:

1. Create/open an episode.
2. Open **Connections / AI → Generate**.
3. Select your text connection and choose `story` for a bible or `script` for a structured episode.
4. Enter an instruction, for example:

```text
Write a three-scene, one-minute mystery episode about Ama discovering
a letter at her childhood home's gate. Preserve the attached character
and location descriptions. End when someone inside calls her name.
Use complete spoken narration and a clear visual direction for each scene.
```

5. Select **Story bibles** and **Continuity** if they contain useful context.
6. Click **Build prompt for review**. Read the exact prompt, including any attached context.
7. Click **Generate and save for review**.
8. Open **Jobs / review**. Check the result and correct factual or formatting problems.
9. For a script, click **Apply reviewed result to current episode** when satisfied.
10. Import/generate the visuals and recordings, then use the offline finishing steps.

Individual generation saves a draft first; it does not silently replace your episode. Automation, in contrast, applies its outputs to a **new run-owned story** as it proceeds.

### B5. Connect image generation through ComfyUI

ComfyUI must already have a working image workflow. Follow its [Windows installation guide](https://docs.comfy.org/installation/desktop/windows), install the workflow's required models/nodes, and generate one image in ComfyUI itself before connecting Studio. Use the actual local server address displayed by your installation; the Studio preset is `http://127.0.0.1:8188`.

1. In ComfyUI, prepare a workflow that ends in a saved image output, such as a SaveImage node.
2. Export the workflow in **API format**. A normal canvas file with a `nodes` array is not the required graph.
3. In Studio, add a **ComfyUI** profile named `Illustrations` and enable it.
4. Click **Load ComfyUI workflow…** and select the API JSON.
5. In Provider options, locate the positive text-prompt input inside `workflow` and replace its text with `{{prompt}}`.
6. Keep node IDs, model names, image dimensions and connection arrays intact.
7. Save/test the connection, then generate one `image` in the individual Generate page.
8. Review the result before using that profile for automation.

The adapter uses ComfyUI's [queue, history and file routes](https://docs.comfy.org/development/comfyui-server/comms_routes). It substitutes the prompt; it does not install models or rewrite the rest of your graph. If your graph has a fixed random seed, change its configuration deliberately when you want different samples.

Example art direction:

```text
Vertical illustrated mystery scene. Ama is an adult woman with short dark
hair and a blue coat. She stands beside a blue metal gate in a cream wall,
holding a cream envelope. Warm sunset light, medium shot, cautious expression.
Leave space below her face for captions. No text, logo or watermark.
```

The built-in ComfyUI adapter sends textual direction only. To consume automatically generated character-reference images, use a custom HTTP/MCP tool whose argument template accepts those references; see Part D.

### B6. Connect speech generation

For ElevenLabs:

1. Add an **ElevenLabs** connection, enable online mode and enter your API key.
2. Click **Save & test / discover** and inspect the returned voices.
3. Copy a voice's ID into **Voice ID (ElevenLabs)**.
4. Enter a supported speech model ID if your setup requires one.
5. Save the connection and generate a short `voice` test using **only the words to speak**.
6. Listen to the result before applying it or selecting it for automation.

The adapter requests a recording through [ElevenLabs Create speech](https://elevenlabs.io/docs/api-reference/text-to-speech/convert). Create separate profiles for different character voices. The text model's voice notes do not automatically select a licensed voice or modify provider voice settings; your chosen profile controls the actual voice.

You may also choose installed Windows speech in an otherwise online production. Text, images and video can use remote models while narration remains local.

### B7. Connect video generation

**Runway:** add a Runway profile, choose an available text-to-video model, enter the API key, and configure a duration/ratio that model accepts. Provider options might be:

```json
{"duration": 5, "ratio": "720:1280"}
```

These settings are not universal across models. Check the selected model's [current API contract](https://docs.dev.runwayml.com/api/). Studio's built-in adapter submits text-to-video, retains the returned task ID, polls completion and downloads the clip. It does not automatically switch to image-to-video or supply a character-reference upload.

**Local video through ComfyUI:** create a separate profile with a working video workflow. The workflow must save an MP4/WebM/MOV/MKV result exposed in its history, not only a preview image or GIF. Test the profile using the `video` task before selecting it for cartoon/cinematic automation.

For either provider, the source clip must cover the scene's duration. The automated runner can request additional continuation/cutaway clips and join them when one clip is too short. This can increase generation calls. The built-in Runway profile's configured duration remains the submitted duration; custom tools can consume the workflow's requested `duration` placeholder.

## Part C — automate a manuscript into videos

### C1. Prepare the manuscript

Supported direct imports are **UTF-8 TXT, Markdown and DOCX**. The file must be smaller than 20 MiB and contain no more than 2 million extracted characters. DOCX import reads normal document paragraphs; it does not interpret embedded pictures, tracked editorial intent, footnotes or layout as story content.

For PDF or EPUB, export to text or DOCX first. A scanned PDF needs OCR in another tool, followed by proofreading. Do not rename `.pdf` to `.txt`; conversion must extract the actual words.

Before attaching:

1. Remove unrelated cover text, advertisements and repeated page headers.
2. Keep useful chapter headings and character names.
3. Check that paragraphs are readable and dialogue punctuation survived conversion.
4. Save a copy of the cleaned source.
5. Start with a chapter or the supplied [practice manuscript](examples/blue_gate_manuscript.txt).

The source is copied into the run folder. Your original attachment is not edited. Long sources are split into numbered sections, all of which are analysed. Large summary sets are condensed in additional analysis stages. Episode scripts receive the selected source sections and earlier episode handoffs; this is still an adaptation and may compress or misinterpret details, so review source fidelity.

### C2. Select the series and format

Open **Manuscript → videos → Create videos**:

1. Click **Browse…** and select the manuscript.
2. Enter the series title.
3. Choose **Narrated visual novel**, **Animated cartoon** or **Realistic cinematic series**.
4. Choose the approach:
   - **Adapt this manuscript faithfully** preserves the supplied characters, setting and events as far as the duration allows.
   - **Create an original story from broad structural inspiration** asks for a distinct story rather than a renamed copy.
5. Set **Episodes** to `1` for the pilot.
6. Set an approximate target, such as `60` seconds.
7. Enter useful **Creative direction**, for example:

```text
English dialogue and narration. Warm illustrated mystery for adults.
Preserve Ama's short hair and blue coat. Keep the suspense grounded.
The blue gate and courtyard lamp must retain the same layout.
Use a clear ending rather than summarizing the entire novel.
```

The current guided workflow exports vertical video. It creates a separate story for each run, identified by the title plus a short run suffix. Existing stories are not used as production targets.

### C3. Assign a model to each task

Click **Refresh available connections** after saving your profiles in Connections / AI.

| Task | Required connection | Practical starting choice |
|---|---|---|
| Analysis / planning | Text model or configured text tool | A model that follows JSON and handles long context |
| Scripts | Text model/tool | Leave “Use Analysis…” initially, or choose a separate writer |
| Quality review | Text model/tool | A separate reviewer if available, otherwise use Analysis |
| Illustrations / references | Image-capable ComfyUI or configured tool | Your tested image workflow |
| Animated / cinematic clips | Runway, video ComfyUI or configured tool | Your tested short-video workflow |
| Speech | Installed Windows speech, ElevenLabs or configured tool | A tested voice profile |
| Lip-sync tool | Optional configured HTTP/MCP tool | Only select one that accepts final audio and video |

Narrated production requires illustrations but not a video connection. Cartoon/cinematic production requires video; image generation is needed only if you also enable reusable references. You can use entirely different providers for planning, writing, review, images, video and speech.

Connections not capable of a task are omitted from its picker. If a custom MCP/HTTP profile is missing, configure its `production` mapping as described in Part D.

### C4. Set optional production controls

Open **Advanced**:

1. Choose **360 × 640** for a fast pilot or **1080 × 1920** for a full export.
2. Set the **Maximum generation stages**. The default is 200. This counts new generation stages, including local speech, prompt-writing stages, reviews, reference images and continuation clips; it is not a currency budget.
3. Optionally enable **Pause after the series plan for review**.
4. Optionally enable **Generate reusable character and location reference images**. This adds one reference prompt and one image generation for each planned entity. A custom template must consume the references for them to condition later images/video.
5. For Windows speech, optionally enter an installed voice name exactly as listed in Audio / output. Blank uses the Windows default.
6. For different character voices, enter a JSON mapping using the profile IDs listed on the page:

```json
{
  "NARRATOR": "your-narrator-profile-id",
  "CHAR-001": "your-ama-voice-profile-id",
  "CHAR-002": "your-second-character-voice-profile-id"
}
```

Replace the example values with actual IDs. Unmapped characters use the default Speech selection. For a first run, use `{}` and a single voice. To map newly assigned character IDs accurately, pause after the plan and inspect its character list. Select that run in **Runs / resume**, enter the mapping in Advanced, then click **Apply voice overrides to selected paused plan**. Resume the run after saving the mapping. Other Advanced form changes affect **new runs**, not existing ones.

For long projects, account-level spending limits remain useful because a single generation stage may be expensive. Polling an existing provider task does not represent a new generation stage, but provider billing rules are outside Studio's control.

### C5. Start and follow progress

Click **Create videos**. This authorizes the selected profiles to receive the source/context and generate the requested outputs.

The runner performs these stages:

1. Copies and extracts the manuscript; saves numbered source sections.
2. Analyses every section and reduces large summary collections.
3. Creates a season plan, story/character/location/style/audio bibles and stable IDs.
4. Optionally pauses for plan review.
5. Optionally generates reusable character/location reference images.
6. Writes each episode using its source sections and earlier handoffs.
7. Runs textual quality review and makes one repair attempt if blocking issues are found.
8. Creates a recording for each spoken shot and measures its duration.
9. Writes a compact, model-facing visual prompt and generates the picture or video.
10. Extends insufficient video coverage with additional generated clips, within a bounded limit.
11. Runs the optional lip-sync tool on the assembled shot and final recording.
12. Builds normal editable episode files, proportional captions and scene breakdowns.
13. Renders the MP4, checks it and fully decodes it before publication to `exports`.
14. Saves the episode handoff and continues to the next episode.
15. Writes the production manifest and delivery notes.

The progress label identifies the active stage. Each stage is saved separately. Percentages during generation are not a reliable prediction of total remaining time; render percentages reflect the current rendering operation.

If the plan pause is enabled, open **Runs / resume → Open run folder** and inspect `season_plan.json`. Read the episode list, characters, locations and bibles. Click **Resume / accept plan** to proceed. That button accepts the saved plan; it does not read changes from the Create videos form.

### C6. Stop, resume and recover

Use **Cancel job** to stop waiting. A cloud job already submitted may keep running with its provider. To continue, select the same run in **Runs / resume** and click **Resume / accept plan**. Do not click Create videos again unless you want a separate production.

| Run status | Meaning | Next action |
|---|---|---|
| created | Source/configuration saved; work has not started | Resume |
| running | A worker owns the production lock | Wait or Cancel job |
| awaiting_plan | Plan is ready and review pause was requested | Inspect it, then Resume / accept plan |
| paused | Work was cancelled/stopped | Resume when ready |
| needs_attention | A model, connection, validation or local operation failed | Read the error and use the matching recovery below |
| complete | Requested episodes rendered and passed technical checks | Watch them; edit or publish manually |

**Saved provider task ID:** Resume retrieves the same Runway/ComfyUI task instead of submitting another one.

**Unknown submission outcome:** Studio deliberately stops. Check the provider/tool's history. If it did not complete or you deliberately want another attempt, tick the acknowledgement and click **Retry current failed stage**. This archives the previous attempt and can create a new charge. A generic tool that returns only a job ID is not sufficient for this integration; it must return its completed artifact.

**Malformed JSON:** Open the current stage's `draft.txt` under `stages/<stage>/`, correct the JSON against `prompt.txt`, save as UTF-8, and Resume. A valid saved response is reused. Do not edit an earlier successful script after its media stages have already been generated; those assets will still correspond to the earlier text.

**Editorial blockers after repair:** Read the final review and the episode's `…_repair` stage. Correct that repair stage's `draft.txt`, then explicitly retry the current review stage. This rechecks the repaired script before generating its media. Do not simply delete blocking findings to bypass the problem.

**Call limit reached:** While the run is stopped, open `run.json`, increase `config.max_calls` within the supported limit of 5000, save it and Resume. The stage causing the stop has not been submitted. Review the usage and likely remaining work first.

**Changed profile:** A run saves its connection settings. Restore those settings before resuming. Changing only the API key is allowed because keys are not in the snapshot. To deliberately choose different models/configuration, start a new run. This avoids mixing partially completed assets from different model setups without a clear record.

**Crash and stale lock:** Close the app and verify that no production worker is still running. Only then remove that run's `running.lock`; a provider generation may have its own lock too. Do not remove locks from a live job. Reopen Studio and Resume. A request whose outcome was not recorded still requires the unknown-outcome procedure above.

### C7. Review the generated story

On completion, the story opens in the normal editor. Use the same controls from Part A to inspect and fix it.

1. Open the generated bibles and check names, plot facts and location layout.
2. Watch each export from start to finish.
3. Check character appearance and object continuity between shots.
4. Listen for mispronunciation, repeated lines or the wrong character voice.
5. Adjust caption timing manually where the proportional timing misses pauses.
6. Add music/effects or cards if desired.
7. Replace weak pictures/clips by generating a new individual asset and importing it into that scene.
8. Rerender the edited episode at the desired resolution.

The generated continuity log is labelled as an adaptation handoff pending editorial approval. A language-model review sees text; it has not watched or listened to the resulting media. Do not treat “complete” as a guarantee of publishable creative quality.

## Part D — use MCP or a custom HTTP service

### D1. What MCP does here

An MCP server exposes named tools with defined input arguments. A tool might generate an image, synthesize a voice or run a lip-sync process. MCP itself is not an AI model and does not guarantee that a connected server has those capabilities.

Studio has two distinct roles:

- As a **client**, it connects to your chosen MCP server and calls an explicitly mapped tool for a production task.
- Its optional **Studio MCP server** lets another client inspect this workspace and, if enabled, save drafts or render existing episodes. That server does not automatically provide image/video generation.

The production runner never lets manuscript text or model output choose arbitrary tool names or executable commands. The mappings come from your saved connection profile.

### D2. Install and test MCP support

In the project folder:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-integrations.txt
```

Restart Studio. Add either:

1. **MCP local program** for a trusted program installed on this PC. Configure its executable, arguments and working directory in Provider options.
2. **MCP Streamable HTTP** for an already running server. Enter its actual `/mcp` URL and credential if required.

Use **Software tools** to list the tools, inspect the input schema and test one small call. Use the tool's actual name and exact argument names. Do not assume an image tool accepts an OpenAI-style request or a local Windows file path.

Example local-program options, with paths you must replace:

```json
{
  "command": "C:\\MyTools\\.venv\\Scripts\\python.exe",
  "args": ["C:\\MyTools\\media_server.py"],
  "cwd": "C:\\MyTools"
}
```

If the program requires a credential environment variable, add its expected name as `credential_env` and store the key in Studio's secure field. Do not paste a key into `args` or Provider options.

### D3. Map a tool to a production task

Add a `production` object to the same profile's Provider options. These are **adapter examples**, not promises that a server exposes tools with these names. Replace names/arguments to match the schema you inspected.

An image tool might use:

```json
{
  "production": {
    "image": {
      "tool": "generate_image",
      "arguments": {
        "prompt": "{{prompt}}",
        "model": "{{model}}",
        "request_id": "{{request_id}}",
        "output_path": "{{output_path}}",
        "references": "{{reference_images}}"
      }
    }
  }
}
```

For an MCP local program, retain its `command`, `args` and `cwd` alongside `production`. For HTTP MCP, the endpoint stays in the profile's URL field. Set the profile's Model ID if the mapped tool expects one. Save the profile, then refresh connections in Manuscript → videos.

Supported task keys are `story`, `image`, `voice`, `video` and `lipsync`. Analysis, writing and review all use the `story` contract. A single profile may expose several keys; separate profiles allow different models or options per task.

| Placeholder | Value supplied by Studio |
|---|---|
| `{{prompt}}` / `{{text}}` | The task prompt; for speech, only spoken words |
| `{{model}}` | The selected connection's Model ID |
| `{{kind}}` | The production task key |
| `{{request_id}}` | Stable ID for this attempt; the tool can use it for deduplication |
| `{{output_path}}` | Suggested file destination inside this stage's folder |
| `{{speaker}}` | `NARRATOR` or a stable character ID for voice/lip-sync tasks |
| `{{duration}}` | Requested video/lip-sync duration in seconds |
| `{{reference_paths}}` | Local paths to matching generated references |
| `{{reference_images}}` | Array of reference images encoded as data URIs |
| `{{audio_path}}` / `{{video_path}}` | Final local input files for lip-sync |
| `{{audio_data_uri}}` / `{{video_data_uri}}` | Those inputs encoded for a remote tool |

A placeholder occupying the whole JSON value preserves its type. For example, `"references": "{{reference_images}}"` becomes an array, not a string containing JSON. Omit arguments the tool does not accept. Reference and audio/video data are encoded only when the template requests them; each such input is limited to 8 MiB before encoding.

Local paths work only for a tool that can access Studio's filesystem. A remote tool normally needs data URIs or its own documented upload process. The current adapter does not automatically upload arbitrary files to every provider.

### D4. Required tool result format

Text tools should return a JSON object such as:

```json
{"text": "{\"summary\":\"The requested structured output...\"}"}
```

The text must follow the specific production prompt's JSON contract. A tool can also return the structured production object directly. MCP `structuredContent` and JSON in text content are supported.

Media tools must return **a completed artifact**, using one of these forms:

```json
{"path": "C:\\VideoNovelStudio\\.production_runs\\RUN_ID\\stages\\STAGE\\result.png"}
```

```json
{"url": "https://your-media-host.example/completed-image.png", "extension": ".png"}
```

```json
{"base64": "ENCODED_FILE_BYTES", "mime_type": "image/png"}
```

The example URL and base64 string are placeholders, not usable media. A local path must be inside the directory provided by `output_path`. The adapter rejects arbitrary local file reads. Downloads are bounded and do not forward provider credentials to the artifact host; use an accessible signed URL if the result needs temporary authorization. Redirects are not followed.

For audio, return WAV/MP3/OGG/M4A; for video/lip-sync, MP4/WebM/MOV; for images, PNG/JPEG/WebP. The content is probed/decoded as the requested media type. A web page named `.mp4` will not pass validation.

A tool returning `{"job_id":"..."}` without its finished result is not enough. Implement waiting/polling in the tool or use the built-in provider adapter that knows that provider's task API. MCP calls currently have a four-minute overall guard and a 120-second read timeout; long-running tools need an integration designed around those limits.

### D5. Lip-sync mapping

Only select a tool that actually supports your style of video and the supplied audio. For example:

```json
{
  "production": {
    "lipsync": {
      "tool": "sync_dialogue",
      "arguments": {
        "video": "{{video_data_uri}}",
        "audio": "{{audio_data_uri}}",
        "speaker": "{{speaker}}",
        "request_id": "{{request_id}}"
      }
    }
  }
}
```

The tool must return a completed video at least as long as the planned shot. Studio uses the separately finalized voice recording in its mix and mutes the clip's own sound. Inspect synchronization, face identity and expressions yourself. If the tool cannot handle a shot, replace it or use reaction/cutaway coverage; do not assume a successful API response proves correct lip movement.

### D6. Generic JSON HTTP production

A **JSON HTTP API** profile can use the same contract without MCP:

```json
{
  "production": {
    "image": {
      "path": "/generate-image",
      "arguments": {
        "prompt": "{{prompt}}",
        "model": "{{model}}",
        "request_id": "{{request_id}}"
      }
    }
  }
}
```

Studio POSTs the substituted arguments to that path on the configured base URL. The service must implement that endpoint and return one of the result objects above. Use a local loopback URL for a local service or HTTPS for a remote service. Studio supplies Bearer authentication from the configured credential; services needing a different request/authentication scheme need a compatible bridge or a dedicated adapter.

### D7. Let another MCP client inspect Studio

To expose Studio's existing workspace tools:

```powershell
.\.venv\Scripts\python.exe -m src.studio_mcp --workspace 'C:\VideoNovelStudio'
```

This starts a stdio server intended to be launched by an MCP client, not a web page. Configure your client to run that executable/module with the workspace argument. By default it exposes read/validation tools. Add `--allow-drafts` for saving script drafts and `--allow-render` for rendering existing episodes. Those switches grant capabilities to the connected client; choose them deliberately.

The server remains distinct from the manuscript automation page. See [CONNECTIONS.md](CONNECTIONS.md) for the full connection/storage details.

## Review, export and back up

### What to check before sharing

- The adaptation preserves the intended events and does not invent important source facts.
- Characters, costumes, props and locations remain consistent.
- Generated hands/faces/movement are acceptable at normal playback speed.
- Every spoken word is audible and pronunciation is correct.
- Captions match the final recording and remain readable.
- Music/effects do not mask dialogue; supplied media is cleared for your intended use.
- The opening and ending are not cut off, and the delivery file has the intended resolution.

Studio exports locally. Uploading to a video platform, writing descriptions, selecting thumbnails and publishing remain your actions. `delivery.md` contains delivery notes, not evidence that an upload occurred.

### Where the files live

```text
workspace/
  stories/<series>/
    story.json
    series_bible.md
    character_bible.md
    location_bible.md
    continuity_log.md
    continuity.json
    season_plan.json                 # automated productions
    production_manifest.json         # automated productions
    delivery.md                      # automated productions
    assets/                          # optional reusable references
    episodes/episode_001/
      scenes.json
      script.md
      subtitles.srt
      scene_breakdown.md
      assets/
  exports/
    <series>_episode_001.mp4
    <series>_episode_001.srt
    <series>_episode_001.verification.json
  .production_runs/<run-id>/
    run.json
    manuscript.txt / manuscript.md / manuscript.docx
    source.txt
    source_chunks.json
    prompt_library.json
    season_plan.json
    stages/<stage>/prompt.txt
    stages/<stage>/draft.txt or media output
    attempts/                        # archived explicit retries
  .generation_jobs/<job-id>/          # built-in provider request history
  .studio_connections.json            # profiles, no saved keys
```

Back up the whole workspace with the app closed, including hidden/dot-prefixed folders if you want to resume productions. `.production_runs`, `.generation_jobs` and connection settings are ignored by Git; committing code alone does not back them up. Original manuscripts and generated content may be sensitive, so choose an appropriate backup destination.

Credentials are outside the project and tied to the Windows user. Re-enter keys on a fresh computer. Reinstall dependencies and local AI models there too; a copied `.venv` is not a reliable portable installation. Finished stories use relative asset paths, but unfinished runs retain some local/provider paths and configuration snapshots; the safest recovery is on the original workspace path. Review those paths before migrating an unfinished run.

## Troubleshooting

| Symptom | What to do |
|---|---|
| Python is not recognized | Reopen the terminal after installation; verify the installed runtime and PATH; try the `py` launcher for environment creation |
| Setup cannot install a dependency | Use the supported 64-bit Python runtime, check the internet connection or matching offline wheels, and run pip through `.venv\Scripts\python.exe` |
| FFmpeg/FFprobe not found | Add the actual `bin` directory to PATH or set both `VNS_…` variables; restart Studio |
| Doctor reports a missing filter/encoder | Install a full FFmpeg build with the reported feature; do not skip the failed check |
| No local voice | Install a compatible Windows speech voice or import a recorded WAV/MP3; local AI speech is a separate connection |
| A scene is blank/missing | Use Browse to import a real image/video; check the file exists and the selected media type matches |
| Narration is longer than the scene | Fit to audio, lengthen the shot, or shorten/rerecord speech; do not expect automatic word truncation |
| Video ends before narration | Import a longer clip, reduce its trim start, or generate more coverage; a clip is not automatically looped by the editor |
| Caption timing feels wrong | Listen to the waveform and save manual timings; auto captions are proportional, not speech-aligned |
| Preview shows old edits | The player is showing the last export; save and rerender |
| Publishing warns about duration | Change the expected range to your actual delivery goal, or adjust the episode length |
| Provider returns 401/403 | Check the API endpoint, account access and key; a consumer chat subscription may not include API use |
| Provider returns 429 | Check quota/rate limits/account spending; inspect submission history before retrying |
| Model output is cut off | Increase that model's supported output allowance or reduce episode complexity; automation will not apply incomplete JSON |
| ComfyUI workflow rejected | Export API format, install the exact nodes/models, include `{{prompt}}`, and save the requested media type |
| Video model rejects settings | Verify model ID, duration, ratio and availability in that provider's current documentation |
| Tool says an argument is unknown | Compare the mapping with its actual input schema; remove unsupported arguments |
| Remote tool cannot find a local file | Use supported data URI inputs or a tool-specific upload process instead of Windows paths |
| Production connection picker is empty | Save/enable the profile, choose the appropriate connection mode, configure its capability and click Refresh available connections |
| Run needs attention | Read the exact current-stage error in Runs / resume; use the recovery procedure in C6 |
| Two people try the same production | Wait for the active worker; the per-run lock prevents concurrent execution |

For a technical report, include the app error, relevant stage name, provider type/model ID, doctor output and whether the sample episode renders. Do not include API keys. The implementation and tested boundaries are described in [AUTOMATION.md](AUTOMATION.md).
