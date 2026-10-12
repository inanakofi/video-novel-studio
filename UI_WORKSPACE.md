**Video Novel Studio workspace improvements**

Implemented on 12 October 2026, following the [appearance refresh](UI_REFRESH.md).

Scene rows now show thumbnails from actual media, a clear scene heading, a narration excerpt, duration, and file-presence status. Images are decoded into a bounded thumbnail cache, and replacing an asset invalidates its thumbnail. Video rows reuse existing cached preview frames. An uncached video shows a native file icon until its normal scene preview creates a frame; browsing the list does not start additional FFmpeg processes.

The scene inspector is organized into Visual, Narration, Timing, Captions, and Continuity. Narration stays open initially for a scene with existing artwork. Missing visuals open the Visual section so Browse is available. Section headers support mouse and keyboard activation. Collapsing a section hides its controls without losing their values. Video scenes hide image-only camera motion and foreground controls. Motion and transition menus show readable names while saving the existing canonical codes.

Audio / output settings are grouped into episode timing, output, narration, music, captions, and sound effects. Provider settings are grouped into provider, model defaults, credentials, and advanced options. MCP and ComfyUI configurations open the advanced group when their required options are relevant. All existing settings remain editable.

Manuscript setup now separates the manuscript, video format, and task model assignments. The task grid aligns Task, Connection, Model, and Available columns, preserving searchable IDs, filters, inheritance, and saved choices. Create videos and the existing explanation about service contact, charges, and submitted jobs remain visible outside the scrolling setup form. Publishing thresholds use a compact three-column group above the check action and findings table.

The existing pane order, navigation destinations, project format, and rendering workflow remain in place. Disclosure choices persist while the window is open; they are not saved as workspace preferences.

Actual native Qt captures:

- [Dark scene workspace](verification/ui-workspace/dark-scenes.png)
- [Light laptop layout](verification/ui-workspace/light-laptop.png)
- [Timing and camera controls](verification/ui-workspace/dark-timing.png)
- [Task model assignments](verification/ui-workspace/dark-task-models.png)
- [Manuscript setup with visible creation action](verification/ui-workspace/dark-manuscript.png)
- [Provider settings](verification/ui-workspace/dark-connections.png)
- [Audio / output groups](verification/ui-workspace/light-output.png)
- [Publishing settings](verification/ui-workspace/light-publishing.png)

The full suite passed **145 tests** with native GUI checks enabled. It covers real MP4 rendering/decoding, caption editing, video imports, model routing, and the new workspace behaviors. After tightening the final disclosure layout, **15 affected tests** passed again, including manuscript production and model assignment. [Full suite result](verification/ui-workspace/test-summary.json), [final layout result](verification/ui-workspace/final-layout-summary.json).

Both themes passed layout checks at 1280 by 800 and 1440 by 900, at 100%, 125%, and 150% scaling. Screenshots were visually reviewed for thumbnail/text overlap, collapsed spacing, control visibility, and readable themes. [100% checks](verification/ui-workspace/appearance-checks.json), [125% checks](verification/ui-workspace/appearance-checks-125.json), [150% checks](verification/ui-workspace/appearance-checks-150.json).

Ruff passed for the new native widget module, regression tests, shared theme, and capture tool. Critical Python checks passed for the edited existing modules. UI captures use a temporary sample workspace, Qt's offscreen platform, and registered Windows Segoe UI fonts. Live provider behavior and OS window chrome are outside these visual checks.

Reproduce the captures with `.\.venv\Scripts\python.exe tools\verify_ui_refresh.py --offscreen --output verification\ui-workspace`. Add `--scale 1.25` or `--scale 1.5` for additional scaling checks. Restart the studio to use the updated workspace.
