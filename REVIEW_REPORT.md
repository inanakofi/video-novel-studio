# Project follow-up review — 12 October 2026

The exercised workflows pass after the fixes below. The full suite passed
**109 tests with no failures or skips**, including native desktop interaction,
playback, Windows speech, actual FFmpeg renders, and local HTTP/MCP fixtures.
Eleven regression tests were added in `tests/test_review_followup.py`.

## Fixes

| Finding | Result |
| --- | --- |
| Broken connection settings, generation history, story metadata or export reports could prevent startup. | Validate saved records, ignore damaged history/report entries, and label damaged story metadata while keeping the library accessible. Original files remain available for repair. |
| Story bible edits disappeared when switching stories before creating an episode. | Story documents now save independently of episode existence. |
| A failed save left the sidebar pointing at a different story or episode. | Restore the selection to the project whose edits remain open. |
| Character voice overrides skipped checks applied to the default voice. | Check every selected voice provider's required configuration before production starts. |
| Cancellation during a completed HTTP submission discarded its response and blocked safe resume. | Capture and save the bounded response before honoring cancellation at the next stage. No automatic resubmission is introduced. |
| A worker could start with stale production state after another worker completed. | Reload the saved state after acquiring the exclusive run lock. |
| DOCX manual line breaks and tabs joined separate words together. | Preserve those separators during manuscript extraction. |
| Export freshness checked only the scene JSON. | New reports include content signatures for manual captions and all referenced media; both export views use them, including after moving the workspace. |
| Changes to source files during rendering could publish a misleading verification report. | Recheck inputs before publication and preserve the existing MP4 and sidecars when inputs changed. Output checksums are streamed rather than reading the whole MP4 into memory. |

## Verification

Environment: Windows, Python 3.14.2, Pillow 12.3.0, PySide6 6.10.1,
FFmpeg/FFprobe 9.0, optional MCP 2.3.0.

- Full suite with `VNS_GUI_TESTS=1`: 109 passed in 106.940 seconds. See [test output](verification/review-tests.txt).
- After the final source-snapshot adjustment, all 11 follow-up regression tests passed again in 10.158 seconds; Ruff, compilation and whitespace checks also passed again.
- Source Ruff checks (`F,E9`), test/tool checks (`E9,F63,F7,F82`), Python compilation and Git whitespace checks passed.
- Environment doctor and `pip check` passed.
- Wheel build, installation into a temporary target, and seven installed-module startup checks passed outside the checkout.
- `pip-audit` reported no known vulnerabilities in the 31 installed packages in the application and MCP dependency trees. See [audit output](verification/review-dependency-audit.json) and [audited versions](verification/review-dependencies.txt).
- A targeted scan found no common embedded API-key or private-key patterns in tracked text files. This is not an exhaustive secret-history scan.
- The three completed demonstration projects passed asset and caption validation.

Tests use temporary projects. Historical screenshots and verification files were
restored after tests refreshed them. Existing stories, exports, credentials and
the pre-existing edit to `stories/fiifi/episodes/episode_001/scene_breakdown.md`
were preserved.

Repeat the main checks from the repository root:

```powershell
$env:VNS_GUI_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m src.doctor
.\.venv\Scripts\python.exe -m pip check
```

## Outstanding content and testing limits

| Draft episode | Missing or incomplete content |
| --- | --- |
| `ama_and_the_secret_heir/episode_001` | Two images (`ama_mansion_night.png`, `mansion_gates.png`) and a complete narration recording; the current recording lasts 0.25 seconds. |
| `ama_and_the_secret_heir/episode_002` | `assets/scene_001.png` and `narration.wav`. |
| `fiifi/episode_001` | `assets/scene_001.png`. |

Details are in [the asset inventory](verification/review-project-assets.json).
These drafts cannot render until their intended source content is supplied.

Cloud generation and live model inference were not exercised with paid accounts.
Provider tests use local protocol fixtures; desktop playback automation is muted.
Older export reports retain their original scene-file-only freshness check until
rerendered. Passing these checks establishes the tested behavior in this
environment; it does not prove the absence of every possible bug.
