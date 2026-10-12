"""Capture the actual Qt studio in an isolated sample workspace, without services.

Run with --offscreen for headless review, and --scale 1.25 or 1.5 for DPI checks.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offscreen', action='store_true')
    parser.add_argument('--scale', type=float, choices=(1, 1.25, 1.5), default=1)
    parser.add_argument('--output', type=Path, default=ROOT / 'verification/ui-refresh')
    args = parser.parse_args()
    if args.offscreen:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    os.environ['QT_SCALE_FACTOR'] = str(args.scale)

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication

    from src.app import StudioWindow

    app = QApplication([])
    app.setStyle('Fusion')
    app.setQuitOnLastWindowClosed(False)
    # The Windows offscreen plugin has no system font enumeration. Register the
    # existing fonts for faithful captures; the normal Windows app needs no copy.
    if args.offscreen:
        for name in ('segoeui.ttf', 'segoeuib.ttf', 'segoeuisl.ttf'):
            font = Path('C:/Windows/Fonts') / name
            if font.is_file():
                QFontDatabase.addApplicationFont(str(font))

    evidence = args.output.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    suffix = '' if args.scale == 1 else f'-{round(args.scale * 100)}'
    checks = []
    with tempfile.TemporaryDirectory(prefix='VNS appearance capture ') as folder:
        workspace = Path(folder)
        shutil.copytree(ROOT / 'stories/the_letter_at_the_gate',
                        workspace / 'stories/the_letter_at_the_gate',
                        ignore=shutil.ignore_patterns('.vns-cache'))
        window = StudioWindow(workspace)
        if not args.offscreen:
            window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        window.resize(1440, 900)
        window.show()
        app.processEvents()
        try:
            for theme in ('light', 'dark'):
                window.theme_combo.setCurrentIndex(window.theme_combo.findData(theme))
                for tab, name in ((0, 'scenes'), (3, 'output'), (4, 'timeline'), (7, 'publishing'),
                                  (8, 'connections'), (9, 'manuscript')):
                    window.tabs.setCurrentIndex(tab)
                    app.processEvents()
                    assert window.grab().save(str(evidence / f'{theme}-{name}{suffix}.png'))
                if hasattr(window, 'scene_sections'):
                    window.tabs.setCurrentIndex(0)
                    window.scene_sections['Narration'].set_expanded(False)
                    window.scene_sections['Timing'].set_expanded(True)
                    app.processEvents()
                    window.grab().save(str(evidence / f'{theme}-timing{suffix}.png'))
                    window.scene_sections['Timing'].set_expanded(False)
                    window.scene_sections['Narration'].set_expanded(True)
                    window.tabs.setCurrentIndex(9)
                    window.production_sections['Manuscript'].set_expanded(False)
                    window.production_sections['Video format'].set_expanded(False)
                    app.processEvents()
                    window.grab().save(str(evidence / f'{theme}-task-models{suffix}.png'))
                    window.production_sections['Manuscript'].set_expanded(True)
                    window.production_sections['Video format'].set_expanded(True)
                for width, height in ((1280, 800), (1440, 900)):
                    window.tabs.setCurrentIndex(0)
                    window.resize(width, height)
                    app.processEvents()
                    check = {
                        'theme': theme, 'scale': args.scale,
                        'requested_window': [width, height],
                        'actual_window': list(window.size().toTuple()),
                        'preview': list(window.preview_stack.size().toTuple()),
                        'render_button': list(window.render_button.size().toTuple()),
                        'idle_progress_hidden': window.progress_bar.isHidden(),
                        'idle_cancel_hidden': window.cancel_button.isHidden(),
                        'idle_details_hidden': window.log.isHidden(),
                        'image_video_controls_hidden': window.video_start_spin.isHidden(),
                        'all_navigation_pages': window.tabs.count(),
                    }
                    assert window.size().toTuple() == (width, height), check
                    assert window.preview_stack.height() >= 320, check
                    assert window.preview_stack.width() >= 230, check
                    assert window.progress_bar.isHidden() and window.cancel_button.isHidden(), check
                    assert window.render_button.width() >= window.render_button.fontMetrics().horizontalAdvance(window.render_button.text()) + 24, check
                    checks.append(check)
                    if width == 1280:
                        window.grab().save(str(evidence / f'{theme}-laptop{suffix}.png'))
            window._set_busy(True)
            window._task_progress(.42, 'Rendering scene 2 of 3')
            app.processEvents()
            window.grab().save(str(evidence / f'dark-job{suffix}.png'))
            window._set_busy(False)
            window._error('Example error state: choose a valid scene visual, then render again.')
            app.processEvents()
            window.grab().save(str(evidence / f'dark-error{suffix}.png'))
        finally:
            window.episode = None
            window.story = None
            window.close()
            window.deleteLater()
            app.processEvents()
    report = {'platform': 'offscreen' if args.offscreen else 'native hidden window',
              'checks': checks, 'note': 'Actual Qt widgets and supplied sample art in a temporary workspace. '
              'Job/error captures demonstrate simulated states; no render or service call is made.'}
    (evidence / f'appearance-checks{suffix}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'scale': args.scale, 'checks': len(checks), 'output': str(evidence)}, indent=2))


if __name__ == '__main__':
    main()
