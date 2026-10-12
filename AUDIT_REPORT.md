# Project review — 2026-10-12

The reviewed Windows workflows pass after the fixes below. The complete suite
passed **80 tests, with no failures or skips**, including real desktop interaction,
FFmpeg renders, playback, installed speech, and local HTTP/MCP integration tests.
Ten new regression tests reproduced the review findings before the fixes.

## Fixes

| Finding | Result |
| --- | --- |
| Invalid edited caption timestamps prevented the Generate captions action from recovering. | Explicit regeneration now validates replacement cues without first saving the invalid caption table. |
| Opening a valid 25 FPS project silently selected 30 FPS and changed it on save. | The editor preserves valid frame rates beyond its three presets. |
| Timeline playback and change detection used historical absolute paths after copying a workspace. | They resolve the source in the current workspace and play the MP4 beside its verification report. |
| Rebuilding a manuscript reused the old continuous recording and manual caption mode. | Rebuilding detaches previous recordings and resets captions to automatic mode. Original media stays on disk. |
| Malformed sound-effect records reached the editor and failed during use. | Project loading validates required fields, asset text, finite times, and volume bounds. |
| The published JSON schema rejected video fields emitted by the application. | The schema includes media type, video trim start, and original audio volume. |
| A valid JSON array in the session-state file crashed startup. | Only a settings object with string story/episode paths is restored. |
| Exceptions without a message caused the error handler itself to raise IndexError. | A nonempty fallback error is displayed. |
| Command-line asset checking required narration for intentionally silent scenes. | Silent scenes have no planned narration asset. |
| Command-line asset checking omitted parallax foreground files. | Missing foreground assets are reported. |

Unused source imports were removed. Build and linter artifacts are ignored by Git.

## Dependency remediation

The installed Pillow 12.1.0 had known vulnerabilities. Requirements in both
`requirements.txt` and `pyproject.toml` now require **Pillow >=12.3.0,<13**.
See the maintainers' [12.3.0 security release notes](https://pillow.readthedocs.io/en/stable/releasenotes/12.3.0.html).

A project-local `.venv` now uses Pillow 12.3.0. It was created with access to the
existing system packages, reusing PySide6 6.10.1 and optional MCP 2.3.0 without
changing the global Python installation. `Start-Studio.ps1` selects this environment.
Normal fresh setup continues to install requirements into its own virtual environment.

`pip-audit` checked the 31 installed packages in the dependency trees for Pillow,
PySide6, and MCP after the update: **no known vulnerabilities found**.
`pip check` found no broken requirements. A targeted tracked-source scan found
no common hardcoded API-key or private-key patterns; credential files were not printed.

## Verification

Environment: Windows, Python 3.14.2, Pillow 12.3.0, PySide6 6.10.1,
FFmpeg/FFprobe 9.0, MCP 2.3.0. The environment doctor found all required media
features and three installed Windows speech voices.

| Check | Result |
| --- | --- |
| Full unittest suite with `VNS_GUI_TESTS=1` | 80 passed in 119.154 seconds; no skips |
| Source Ruff checks (`F,E9`) | Passed |
| Test Ruff checks (`E9,F63,F7,F82`) | Passed |
| Compilation of `src`, `tests`, and `tools` | Passed |
| Wheel build and installation into a temporary target | Passed |
| Installed-package CLI startup (`--help`) | App, renderer, subtitles, batch, publishing, and MCP passed outside the checkout |
| Full production render from a temporary copy of Connections and Video Demo | Passed with caching disabled |
| Production output | 1080 × 1920, 30 FPS, H.264/AAC, 75.0 seconds for both video and audio, 18 captions |
| Production output verification | Full FFmpeg decode passed; all five shots freshly encoded; 124.74 seconds elapsed |

The production render used temporary files. Existing stories, media, exports,
and historical verification evidence were preserved. Generated `build/`,
`video_novel_studio.egg-info/`, and `.ruff_cache/` remain ignored locally because
automatic approval review rejected their cleanup with “blocked by policy.”

To repeat the main checks:

```powershell
$env:VNS_GUI_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m src.doctor
```

The existing desktop tests refresh several files under `verification/`; this
review restored the historical versions after running them.

## Remaining content requirements and verification limits

Three existing draft episodes cannot render until their source media is supplied:

| Episode | Required content |
| --- | --- |
| `ama_and_the_secret_heir/episode_001` | `ama_mansion_night.png`, `mansion_gates.png`, and a complete narration recording; the existing recording is only 0.25 seconds. |
| `ama_and_the_secret_heir/episode_002` | `assets/scene_001.png` and narration. |
| `fiifi/episode_001` | `assets/scene_001.png`. |

The Letter at the Gate, Studio Prototype, and Connections and Video Demo all
passed asset and caption checks. Missing draft assets were not substituted with
invented content.

Provider protocol behavior was exercised against local fixtures, and real MCP
stdio/HTTP transports passed. Paid cloud generation and live model inference
were not run. The results establish that the exercised workflows pass in this
environment, rather than proving the absence of every possible defect.
