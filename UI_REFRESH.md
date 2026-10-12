**Video Novel Studio visual refresh**

Implemented on 12 October 2026 as the first pass from [the design review](UI_DESIGN_REVIEW.md). The subsequent [workspace improvements](UI_WORKSPACE.md) add thumbnails, grouped settings, and more focused creation controls. Restart the studio with `Start-Studio.ps1`, then choose System, Light, or Dark using Appearance at the bottom of the sidebar. The choice is saved in the workspace's existing local UI state.

The workspace now uses coordinated silver-gray light and graphite/sage dark themes. Shared tokens cover controls, menus, placeholders, helper text, selection, focus, error messages, and the painted timeline. Native Qt Fusion provides the common control foundation. Primary actions, quiet utilities, and destructive actions have distinct treatments, and tabs use a flat treatment with visible overflow controls. Existing navigation names and destinations are retained.

The idle render area is compact. Progress, percentage, and cancellation appear during jobs. Details toggles the full log, and failures open it automatically while keeping the error visible in the status strip. The primary episode render action becomes secondary on the connections and manuscript pages, where generation actions need greater emphasis.

The sidebar is slightly narrower and scene pane proportions give the preview more space. Long episode and scene labels elide rather than creating horizontal scrollbars. Still-image scenes hide video trim, video sound, and video-fit controls without discarding their values. Both artwork and decoded video frames adapt to pane resizing. Expanding job details keeps the complete artwork visible with its original aspect ratio.

The implementation uses a modest design direction: DESIGN_VARIANCE 3, MOTION_INTENSITY 3, and VISUAL_DENSITY 5. Feedback comes from control states rather than decorative animations. Scene thumbnails, a grouped inspector, and broader changes to the information architecture are outside this first pass.

Preview the actual Qt application captures:

- [Dark scene workspace](verification/ui-refresh/dark-scenes.png)
- [Light scene workspace](verification/ui-refresh/light-scenes.png)
- [Light laptop layout](verification/ui-refresh/light-laptop.png)
- [Dark timeline](verification/ui-refresh/dark-timeline.png)
- [Light timeline](verification/ui-refresh/light-timeline.png)
- [Dark manuscript setup](verification/ui-refresh/dark-manuscript.png)
- [Dark connections](verification/ui-refresh/dark-connections.png)
- [Example active job](verification/ui-refresh/dark-job.png)
- [Example error and expanded details](verification/ui-refresh/dark-error.png)

These captures use a temporary sample workspace and the supplied real artwork. The job and error images demonstrate simulated UI states. Real rendering, decoding, editing, and cancellation are checked separately by the native workflow tests. No live AI service calls were used for appearance verification.

Verification completed:

- The full suite passed 138 tests with GUI checks enabled. After the final preview-resizing correction and additional regression test, all 12 affected native/appearance tests passed again, including MP4 rendering, decoded playback, caption gestures, connection workflows, cancellation, and saved preferences. [Full run](verification/ui-refresh/test-summary.json), [final desktop run](verification/ui-refresh/final-desktop-summary.json).
- Both themes passed layout checks at 1280 by 800 and 1440 by 900, at 100%, 125%, and 150% scaling. Checks confirm usable preview dimensions, single-line render buttons, all ten navigation pages, and the compact idle state. [100%](verification/ui-refresh/appearance-checks.json), [125%](verification/ui-refresh/appearance-checks-125.json), [150%](verification/ui-refresh/appearance-checks-150.json).
- Contrast tests cover body/helper text, placeholders, accent-button states, selection, essential control boundaries, and timeline labels in both palettes. They are targeted checks, not a full accessibility certification.
- Ruff passed for the new theme module, regression tests, and appearance capture tool. Critical Python lint checks passed for the edited existing modules.
- A wheel build passed and includes all six theme icon assets. [Packaging check](verification/ui-refresh/packaging-check.json).

The captures and DPI checks use Qt's offscreen platform with the installed Windows Segoe UI fonts registered for rendering. OS title-bar appearance and actual system-theme notifications were not visually tested. Preference-following behavior is covered by the native tests.

To reproduce captures, run `.\.venv\Scripts\python.exe tools\verify_ui_refresh.py --offscreen`. Add `--scale 1.25` or `--scale 1.5` for the additional scaling checks. This creates an isolated workspace and does not render videos or contact providers.
