# Project documentation and bug review — 12 October 2026

The README now describes the product, its intended users, capabilities, manual
and manuscript workflows, installation, configuration, project files, architecture,
command-line tools, testing and limitations. Existing detailed timing and media
guidance remains available. No provider generation requests were made during this
review.

## Corrected behavior

| Finding | Fix and regression coverage |
| --- | --- |
| Deleting an episode in a copied workspace could make its export appear current by checking the surviving original checkout. | Resolve recognized story paths to the current workspace even when the local file is missing. A copied-workspace deletion test verifies that the export becomes outdated. |
| A shot-cache manifest containing valid JSON of the wrong type crashed a render. | Treat non-object manifests as cache misses. Tests exercise arrays, null, strings and numbers. |
| Missing or malformed waveform fields could crash analysis or pass through to the timeline. | Validate envelope structure, numeric ranges and array lengths before reuse; rebuild damaged entries. Include waveform code in the cache version so algorithm changes invalidate old data. |
| An unavailable shot-cache directory stopped an otherwise valid export. | Render without cached shots when the cache cannot be created, and report the cache as disabled. A real FFmpeg render verifies this fallback. |
| Choosing an export filename matching a source video or a manual SRT sidecar could overwrite that input. | Check the MP4 and both publication sidecars against all source inputs before creating output directories or starting the render. Tests preserve a real source clip and manual caption file. |
| A generated script could repeat character IDs and fail only after media generation, when saving scenes. | Reject duplicate cast IDs during script validation, before speech/image/video generation. |
| Importing a large asset with an existing filename loaded the entire source into memory to hash it. | Stream the content hash while preserving the existing destination and naming the imported copy by its checksum. |
| A failed story-bible save displayed a success message. | Display success only after the save completes; preserve the failure details and editor contents. |
| Switching story-bible documents after a save failure discarded unsaved text. | Read the next document and save the current one before switching. Restore the selector on failure and keep the current notes. |

These behaviors are covered by nine regression tests in
[tests/test_project_review.py](tests/test_project_review.py), including native
desktop save actions and real media generation/rendering. Normal export input
hashing and the new overwrite protection share the same source-input inventory.

## Installer and dependencies

The installed project environment contained pip 25.3. The dependency audit
flagged its known installer advisories; upstream fixes are described in the
[pip changelog](https://pip.pypa.io/en/stable/news/). The project's `.venv` now
uses pip 26.2.1. `Setup.ps1` updates pip to `>=26.2,<27` before installing the
application dependencies, and the README includes that step for manual and
offline installation.

The repeat audit found **no known vulnerabilities in 36 installed packages**.
Evidence: [before the update](verification/project-maintenance-dependencies-before.json)
and [after the update](verification/project-maintenance-dependencies.json).
The auditor ran outside the project environment; application dependency versions
and the system Python installation were preserved. Advisory scans are limited to
the installed packages and the database available at the time of the check.

## Validation

- Baseline: 145 tests ran successfully, with 28 desktop checks skipped by default.
- All nine new regression tests pass with `VNS_GUI_TESTS=1`.
- Full suite with desktop tests: **154 passed in 127.694 seconds, no failures or
  skips**. See the [full test output](verification/project-maintenance-tests.txt).
- Environment doctor, `pip check`, source Ruff checks (`F,E9`), test/tool Ruff
  checks (`E9,F63,F7,F82`), Python compilation and Git whitespace checks passed.
- `Setup.ps1` passed PowerShell syntax parsing, and its new pip upgrade command
  was exercised successfully in the project environment.
- README/review links resolve, and application, renderer and MCP command-line
  help starts successfully.
- A targeted scan of tracked text files found no common embedded API-token or
  private-key patterns. This does not cover all secret formats or Git history.

Environment: Windows, Python 3.14.2, Pillow 12.3.0, PySide6 6.10.1,
FFmpeg/FFprobe 9.0 and optional MCP 2.3.0. Desktop tests use temporary workspaces,
real local media and provider protocol fixtures. The suite includes native
playback and installed Windows speech; it does not establish successful live
inference for every cloud or local-model provider.

## Remaining content gaps and limits

Three completed demonstration projects pass the current asset check. Three
existing drafts still need their intended source content:

| Draft | Required content |
| --- | --- |
| `ama_and_the_secret_heir/episode_001` | `ama_mansion_night.png`, `mansion_gates.png` and a complete narration recording; the existing recording lasts 0.25 seconds. |
| `ama_and_the_secret_heir/episode_002` | `assets/scene_001.png` and `narration.wav`. |
| `fiifi/episode_001` | `assets/scene_001.png`. |

See the [current asset inventory](verification/project-maintenance-assets.json).
These drafts remain editable but cannot render until their source media is supplied.
Existing story edits, the untracked manuscript and original exports were preserved.
Historical desktop screenshots and workflow evidence refreshed by the tests were
restored from a pre-test copy; the new test log and audit files contain this review's
results.

Caption alignment remains proportional/manual, generated media needs creative
review, each manuscript run uses one adaptation format, and optional lip-sync
needs a configured tool. No automatic publishing, bundled model weights or
automatic music/Foley generation were added. Details are in the README and
[AUTOMATION.md](AUTOMATION.md).
