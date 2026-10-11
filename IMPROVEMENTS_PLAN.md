# Editing and production improvements

Extend the existing services and native PySide6 interface; retain the verified
FFmpeg export contract and backward compatibility with existing projects.

1. Add a waveform/timeline service using decoded local narration. Provide draggable
   captions, scene duration/transition handles, sound-effect placement, zoom,
   scrubbing, narration audition and the actual rendered video preview.
2. Store reusable series styles separately from episode settings. New episodes
   inherit explicit defaults; existing episodes change only through Apply style.
3. Add structured character/location references and unresolved plot threads beside
   the existing Markdown bibles. Display previous endings and open threads while
   writing. Preserve user-authored continuity documents.
4. Cache content-addressed scene encodes. Invalidate on media bytes, motion,
   timing, transition dependencies, output settings and renderer/tool versions.
   Verify cache checksums, publish atomically and keep final-export verification.
5. Add a publishing checklist with asset/timing errors and configurable advisory
   checks for duration, caption safe margins/readability and narration pauses.
6. Exercise actual drag gestures, persistence, style inheritance, continuity,
   cache invalidation/recovery and verified rerenders. Document measured results.

Automatic captions remain proportional timing, with manual waveform correction;
this change does not claim speech recognition or forced alignment. Safe margins
are configurable editorial guides, not a guarantee about changing platform UI.

## Completed

All six implementation phases are complete. The upgraded desktop was exercised
through real drag gestures, narration audition, style inheritance and continuity
controls. Forty-six tests pass. Real 75-second 1080p renders measured scene-cache
reuse and passed full decoding; publishing checks exposed a wrapping edge case
which was corrected and regression-tested. See [UPGRADE_REPORT.md](UPGRADE_REPORT.md).
