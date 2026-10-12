**Video Novel Studio UI review**

Original audit recorded on 12 October 2026 before application changes. The first visual pass is now implemented and documented in [UI_REFRESH.md](UI_REFRESH.md).

The current UI reads as a functional desktop utility. Its strongest foundations are the green primary action, clear story/episode context, real media preview, and editable timeline. A modern, elegant result would come from stronger hierarchy, consistent controls, and a workspace that gives the story artwork more attention.

Reading this as: a redesign of a native creative studio for storytellers, with a calm, polished visual language, leaning toward a restrained studio workspace aesthetic.

The requested design-taste-frontend skill explicitly excludes dense product UI and multi-step workflows. Its color, typography, spacing, and consistency principles inform this review. Its marketing heroes, bento grids, scroll effects, and image-generation requirements are not relevant to this audit. The appropriate implementation foundation is the existing PySide6/Qt Widgets application with a shared theme and component styles.

The recommended mode is visual modernization that preserves the brand and existing workflows. Proposed structural changes are identified separately below. The application is native, so web SEO, route migration, Core Web Vitals, and Lighthouse checks do not apply.

| Design dial | Current reading | Proposed direction | Reason |
| --- | --- | --- | --- |
| DESIGN_VARIANCE | 2 | 3 | Predictable alignment helps editing; visual hierarchy can improve without experimental layouts. |
| MOTION_INTENSITY | 1 | 3 | Native feedback, hover, and pressed states are sufficient for a focused studio. |
| VISUAL_DENSITY | 7 | 5 | Keep useful editing controls while reducing persistent instructions, advanced fields, and idle job chrome. |

These dial readings are qualitative design judgments, not measured performance scores.

The review uses saved application captures and the current source. The captures span 11-12 October and do not all include the newest controls. Current-source findings are distinguished from what is visible in those images. No live keyboard, DPI, or theme-switching session was performed.

| Evidence | What it shows |
| --- | --- |
| [Scenes / preview](verification/desktop-workflow.png) | Scene list, long central inspector, narrow right preview, large footer. |
| [Timeline / captions](verification/timeline-workflow.png) | Two rows of controls, dark painted timeline, caption table, playback panel. |
| [Publishing](verification/publishing-production.png) | Full-width settings and a dense findings table. |
| [Connections / AI](exports/verification/connections-settings.png) | Nested tabs and a long provider configuration form; this capture predates some current model controls. |
| [Task model selection](verification/project-review-models.png) | Repeated connection/model rows with model-count labels. |
| [Application shell and stylesheet](src/app.py) | Current ten-page navigation, fixed sidebar, light-only application stylesheet, render footer. |
| [Timeline painting](src/timeline_widget.py) | Independently hardcoded dark surface and track colors. |

The current brand tokens are Segoe UI at 13px for most controls, 22px for the wordmark, and 24px for the episode heading. The page uses `#f3f5f7`, the sidebar `#142234`, body text `#263346`, muted text `#65758a`, and the primary action `#20735e`. Inputs use 5px corners, buttons and lists 6px, and the preview 8px. The wordmark is plain text split over two lines.

The primary information structure is story selection, episode selection, then ten pages: Scenes / preview, Writing, Story bibles, Audio / output, Timeline / captions, Exports, Series, Publishing, Connections / AI, and Manuscript to videos (displayed with an arrow in the app). Each page shares Save project, Check assets, render actions, progress, status, and logs. This is a working foundation; the visual refresh should retain these destinations and actions.

| Priority | Finding | Suggested improvement |
| --- | --- | --- |
| High | Most actions are similarly sized white bordered buttons. Utility actions compete with the actual creative task. | Define primary, secondary, quiet, and destructive treatments. Keep Render MP4 prominent in the editor. In manuscript production, make Create videos the dominant action and visually subordinate the unrelated episode render controls. |
| High | The central scene form dominates the composition. The preview is pushed to the side. | First, rebalance the existing splitters and collapse advanced inspector groups. A subsequent structural option is scene list, central preview, right inspector. |
| High | The application combines a permanently dark sidebar, a light editing surface, and a separately dark timeline. | Create complete light and dark themes from shared tokens. Use a graphite dark theme as the proposed visual direction, with a matching light option and System preference. Dark media mattes remain appropriate in either theme. |
| High | An idle progress bar, disabled Cancel job, and log pane occupy space on every page. | Use a compact job/status strip at idle. Expand progress and cancellation during a job, with a Details disclosure for logs. Keep failures visible and the full diagnostic output accessible. |
| High | Current helper text is too faint on the page background. Control borders are also visually weak. | Strengthen helper text and meaningful control boundaries. Add explicit keyboard focus, pressed, error, and selected states, and verify them with actual keyboard navigation. |
| Medium | The current source has ten long tab labels; the saved captures show heavy native tab separators. | Flatten tab styling, reduce unused horizontal padding, and make overflow obvious at smaller widths. Keep every existing destination discoverable. |
| Medium | Scene rows use narrative fragments, timing, and readiness text, with considerable empty list space. | Add small thumbnails from actual scene media. Give each row a stable Scene 01 label, a short narrative excerpt, duration, and clear asset status. Selection should use a restrained tint and a visible marker. |
| Medium | The scene form shows video trim and video sound fields even for still images. | Make the inspector respond to the selected media type. Show video controls for video and relevant image-motion options for stills. Preserve saved values when groups are hidden. |
| Medium | Long ungrouped forms make connection and output configuration feel mechanical. | Group related fields with short headings and spacing. Use expandable advanced groups for provider JSON and less common options. Keep required setup, defaults, credentials, and the next useful action easy to find. |
| Medium | Raw enum values such as slow_zoom_in appear in the UI. | Display friendly text such as Slow zoom in while keeping the existing stored value. Show a filename as the primary asset label and make the full path available on demand. |

The proposed visual language is graphite and sage: matte surfaces, readable sans-serif type, a single green interaction accent, restrained borders, and real scene artwork. The light version uses silver-gray surfaces with the same green identity. Error and warning colors, and distinct timeline track colors, have semantic roles and should remain distinguishable with text labels.

| Token | Light | Dark |
| --- | --- | --- |
| Application canvas | `#f0f3f6` | `#151c26` |
| Panel surface | `#f8fafb` | `#1c2633` |
| Primary text | `#263346` | `#e8edf3` |
| Secondary text | `#5d6a7b` | `#a4b0bf` |
| Accent | `#20735e` | `#75c8ac` |
| Text on accent button | `#f8fafb` | `#151c26` |
| Decorative separator | `#d8dfe6` | `#344151` |
| Essential control boundary | `#78889b` | `#637388` |

These are proposed tokens, not a finished theme. They still require rendered validation for selection, disabled controls, menus, errors, tables, and the custom timeline.

Contrast calculations from the current stylesheet give body text about 11.69:1 on the page background and white primary-button text about 5.71:1 on green. Those are strong. Muted text `#65758a` on `#f3f5f7` measures about 4.30:1, below the 4.5:1 small-text benchmark; its contrast on white is higher, so the finding depends on the actual background. The current input border `#d4dce3` on white measures about 1.39:1 and needs attention where it is the essential cue identifying the control.

Use WCAG's [text contrast targets](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) and [meaningful control contrast targets](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html) as design benchmarks for this native application. This is a limited color audit, not a claim of full accessibility conformance. The source lacks app-defined focus and pressed rules; native controls may still provide some feedback, which needs live verification.

For typography, retain Segoe UI as the reliable Windows baseline, with Segoe UI Variable where available. Use a deliberate scale: approximately 24px for the episode heading, 16-18px for panel headings, 13-14px for controls/body, and 12px for secondary text. Keep labels readable and use monospace selectively for timecodes and model IDs. The existing 24px heading is already sensible; the greater gain is distinguishing the levels below it.

Use 8px corners for controls, 12px for preview/dialog containers, and a consistent 4/8/12/16/24 spacing scale. Standard editing controls should be approximately 34-36 logical pixels tall, with smaller utility controls where appropriate. Keep destructive actions visually distinct. Use spacing to group settings rather than adding a card around every subsection.

The current source fixes the sidebar at 235px and the minimum window at 1140 by 760. Improve laptop use with an explicitly collapsible sidebar, sensible splitter minimums, persistent splitter positions, clear navigation overflow, and no desktop CTA wrapping. Check 1280 by 800 and 1440 by 900 at 100%, 125%, and 150% display scaling, and verify that a preview and essential editing actions remain usable. Mobile landing-page breakpoints are not relevant to this native desktop app.

The scene workspace should put visual review and scene editing in a clear relationship. Its first pass can preserve the current pane order, reduce the scene list's initial width, increase the preview's share, and organize the inspector into Visual, Narration, Timing, Captions, and Continuity groups. Put labels above stacked inputs within the narrow inspector. Fold infrequent options rather than hiding required controls below a long uninterrupted form.

If a stronger layout change is chosen later, use a compact scene list on the left, a flexible central media canvas, and an approximately 300-340px inspector on the right, with resizable boundaries. These are starting widths, not rigid dimensions. Moving panes changes muscle memory and should be reviewed as a structural proposal. Combining or relabeling the ten navigation destinations is a separate information-architecture decision, not part of the first cosmetic pass.

For Timeline / captions, retain the actual waveform, editable tracks, seek behavior, and caption table. Reduce the prose above the timeline to short contextual instructions. Give playback, cue editing, and import/save actions distinct toolbar groups. Use compact, labeled icon controls for repeated transport operations, keeping accessible names and tooltips. Preserve track category colors; use the app accent for interaction and selection. Make the playhead and selected cue clear without relying only on color.

For Connections / AI and manuscript production, retain searchable model IDs, shown/total counts, explicit service actions, and task-specific assignments. Structure model rows with aligned Task, Connection, and Model columns. Keep counts as secondary text. Separate provider setup from optional advanced configuration, and retain the existing explanations about default models, key reuse, service contact, and charges where they affect the user's decision. A long form can become calmer without removing its capabilities.

For Publishing, make the real error/warning summary easier to scan and retain the findings table, timecodes, and double-click-to-inspect behavior. A table is appropriate here. Use clear severity labels, restrained semantic color, and quiet row dividers. Duration and pause thresholds can sit in a compact settings group rather than stretching across the entire window.

Preserve the distinction between scene artwork, current narration audition, and a previous rendered video. The current application already explains that edits require a rerender; a modern design must keep that fact visible. Keep explicit Save project behavior until actual unsaved-change tracking or autosave exists. Missing media should show a contextual recovery action. A failed connection or render should show its cause and the next available action, while detailed logs remain available.

The highest-value implementation order is:

1. Extract shared theme tokens and apply them to the shell, widgets, and painted timeline. Add complete control states and correct weak helper contrast.
2. Flatten tabs, establish button hierarchy, unify spacing/radii, and collapse idle job details.
3. Add scene thumbnails, improve splitter proportions, and introduce grouped, media-aware inspector controls.
4. Apply the same hierarchy to connections, model assignment, publishing, and output settings.
5. Validate both themes, keyboard focus, display scaling, window resizing, and empty/loading/error/job states. Recheck scene edits, waveform/caption controls, model selections, and rendering for behavioral regressions.

Start in [src/app.py](src/app.py) for the shell and shared stylesheet, [src/studio_panels.py](src/studio_panels.py) for timeline and publishing surfaces, [src/connection_panels.py](src/connection_panels.py) for provider configuration, [src/production_panels.py](src/production_panels.py) for manuscript setup, and [src/timeline_widget.py](src/timeline_widget.py) for painted theme colors. A small shared theme module would prevent the current inline colors from drifting. Qt officially supports the required widget states and subcontrols through [Qt Style Sheets](https://doc.qt.io/qt-6/stylesheet-examples.html).

The first two steps offer the clearest visual improvement with the least workflow disruption. The proposed themes, new layouts, and interactions have not been implemented or tested; this review provides the concrete direction for that work.
