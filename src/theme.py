"""Shared native Qt themes for the studio shell, controls and painted timeline."""
from pathlib import Path

from PySide6.QtGui import QColor, QPalette

# Controls use 8px corners; media surfaces use 12px. Track colors communicate
# media categories, while the green accent identifies actions and selection.
THEMES = {
    'light': {
        'canvas': '#f0f3f6', 'surface': '#f8fafb', 'raised': '#e8edf2',
        'text': '#263346', 'muted': '#5d6a7b', 'disabled': '#8995a4',
        'border': '#d8dfe6', 'control_border': '#78889b',
        'accent': '#20735e', 'accent_hover': '#195d4c', 'accent_pressed': '#154e40',
        'on_accent': '#f8fafb', 'selection': '#dceee7', 'selection_text': '#174c3e',
        'hover': '#e5eeeb', 'warning': '#8a4b22', 'danger': '#a63842',
        'media': '#151c26', 'media_text': '#c2ccda',
        'timeline_grid': '#d8dfe6', 'waveform': '#20735e', 'playhead': '#8a4b22',
        'track_scene': '#38678c', 'track_transition': '#80593d',
        'track_card': '#526378', 'track_music': '#5e558a',
        'track_effect': '#94552e', 'track_caption': '#24795f',
        'track_text': '#f8fafb',
    },
    'dark': {
        'canvas': '#151c26', 'surface': '#1c2633', 'raised': '#293546',
        'text': '#e8edf3', 'muted': '#a4b0bf', 'disabled': '#748196',
        'border': '#344151', 'control_border': '#637388',
        'accent': '#75c8ac', 'accent_hover': '#8dd5bb', 'accent_pressed': '#60b797',
        'on_accent': '#151c26', 'selection': '#28483f', 'selection_text': '#c8ecdf',
        'hover': '#283a3e', 'warning': '#efbc7d', 'danger': '#f39ba4',
        'media': '#101720', 'media_text': '#c2ccda',
        'timeline_grid': '#344151', 'waveform': '#75c8ac', 'playhead': '#efbc7d',
        'track_scene': '#38678c', 'track_transition': '#80593d',
        'track_card': '#526378', 'track_music': '#5e558a',
        'track_effect': '#94552e', 'track_caption': '#24795f',
        'track_text': '#f8fafb',
    },
}


def palette_for(theme):
    """Set native colors too, including popups, placeholders and disabled text."""
    c = THEMES[theme]
    palette = QPalette()
    roles = {
        'Window': 'canvas', 'WindowText': 'text', 'Base': 'surface',
        'AlternateBase': 'raised', 'Text': 'text', 'PlaceholderText': 'muted',
        'Button': 'surface', 'ButtonText': 'text', 'BrightText': 'on_accent',
        'Highlight': 'accent', 'HighlightedText': 'on_accent', 'Accent': 'accent',
        'ToolTipBase': 'surface', 'ToolTipText': 'text', 'Link': 'accent',
        'Light': 'surface', 'Midlight': 'raised', 'Mid': 'control_border',
        'Dark': 'border', 'Shadow': 'border',
    }
    for role, key in roles.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(c[key]))
    for role in ('WindowText', 'Text', 'ButtonText', 'PlaceholderText'):
        palette.setColor(QPalette.ColorGroup.Disabled,
                         getattr(QPalette.ColorRole, role), QColor(c['disabled']))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(c['raised']))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor(c['muted']))
    return palette


def stylesheet_for(theme):
    c = THEMES[theme]
    assets = Path(__file__).with_name('theme_assets').as_posix()
    return f'''
QWidget {{ color: {c['text']}; font-family: "Segoe UI", sans-serif; font-size: 13px; }}
QMainWindow, QWidget#shell {{ background: {c['canvas']}; }}
QLabel {{ background: transparent; }}
QWidget#sidebar {{ background: {c['surface']}; border-right: 1px solid {c['border']}; }}
QLabel#brand {{ font-size: 22px; font-weight: 700; }}
QLabel#heading {{ font-size: 24px; font-weight: 600; }}
QLabel#muted, QLabel#status {{ color: {c['muted']}; }}
QLabel#sectionHeading {{ font-size: 14px; font-weight: 600; padding: 4px 0; }}
QLabel#warning, QLabel[tone="warning"] {{ color: {c['warning']}; }}
QLabel[tone="success"], QLabel#liveCaption {{ color: {c['accent']}; }}
QLabel#liveCaption {{ font-weight: 600; }}
QLabel[tone="error"], QLabel#status[tone="error"] {{ color: {c['danger']}; }}
QLabel#preview {{ background: {c['media']}; color: {c['media_text']}; border-radius: 12px; }}
QWidget#jobBar {{ background: {c['surface']}; border-top: 1px solid {c['border']}; }}
QPushButton {{
    background: {c['surface']}; border: 1px solid {c['border']};
    border-radius: 8px; padding: 6px 12px; min-height: 20px;
}}
QPushButton:hover {{ background: {c['hover']}; border-color: {c['control_border']}; }}
QPushButton:pressed, QPushButton:checked {{ background: {c['selection']}; color: {c['selection_text']}; }}
QPushButton:focus {{ border-color: {c['accent']}; }}
QPushButton#primary {{
    background: {c['accent']}; color: {c['on_accent']};
    border-color: {c['accent']}; font-weight: 600;
}}
QPushButton#primary:hover {{ background: {c['accent_hover']}; border-color: {c['accent_hover']}; }}
QPushButton#primary:pressed {{ background: {c['accent_pressed']}; }}
QPushButton#primary:focus {{ border: 2px solid {c['text']}; padding: 5px 11px; }}
QPushButton[variant="quiet"] {{ background: transparent; border-color: transparent; color: {c['muted']}; }}
QPushButton[variant="quiet"]:hover, QPushButton[variant="quiet"]:checked {{
    background: {c['hover']}; color: {c['text']};
}}
QPushButton[variant="quiet"]:focus {{ border-color: {c['accent']}; }}
QPushButton[variant="danger"] {{ color: {c['danger']}; }}
QPushButton[variant="section"], QPushButton[variant="section"]:checked {{
    background: transparent; color: {c['text']}; text-align: left;
    border: 0; border-bottom: 1px solid {c['border']}; border-radius: 0;
    font-size: 14px; font-weight: 600; padding: 6px 0;
}}
QPushButton[variant="section"]:hover {{ background: {c['hover']}; }}
QPushButton[variant="section"]:focus {{ border-bottom: 2px solid {c['accent']}; padding-bottom: 5px; }}
QLabel#tableHeading {{ color: {c['muted']}; font-weight: 600; padding-bottom: 4px; }}
QPushButton:disabled, QPushButton#primary:disabled {{
    color: {c['disabled']}; background: {c['raised']}; border-color: {c['border']};
}}
QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox, QSpinBox, QFontComboBox {{
    background: {c['surface']}; border: 1px solid {c['control_border']};
    border-radius: 8px; padding: 6px 8px; min-height: 20px;
    selection-background-color: {c['accent']}; selection-color: {c['on_accent']};
    placeholder-text-color: {c['muted']};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QDoubleSpinBox:focus,
QSpinBox:focus, QFontComboBox:focus {{ border: 2px solid {c['accent']}; padding: 5px 7px; }}
QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, QSpinBox:disabled,
QDoubleSpinBox:disabled {{ background: {c['raised']}; color: {c['disabled']}; border-color: {c['border']}; }}
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: 24px; border: 0; }}
QComboBox::down-arrow {{ image: url("{assets}/{theme}-down.png"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {c['surface']}; color: {c['text']}; border: 1px solid {c['control_border']};
    selection-background-color: {c['selection']}; selection-color: {c['selection_text']};
    outline: 0; padding: 4px;
}}
QSpinBox, QDoubleSpinBox {{ padding-right: 24px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right;
    width: 20px; border: 0; background: transparent;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 20px; border: 0; background: transparent;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{assets}/{theme}-up.png"); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{assets}/{theme}-down.png"); width: 10px; height: 10px; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{ background: {c['hover']}; }}
QCheckBox {{ spacing: 8px; padding: 3px; border: 1px solid transparent; border-radius: 4px; }}
QCheckBox:focus {{ border-color: {c['accent']}; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border: 1px solid {c['control_border']};
    border-radius: 4px; background: {c['surface']};
}}
QCheckBox::indicator:checked {{
    background: {c['accent']}; border-color: {c['accent']};
    image: url("{assets}/{theme}-check.png");
}}
QCheckBox::indicator:disabled {{ background: {c['raised']}; border-color: {c['border']}; }}
QTabWidget::pane {{ border: 0; background: {c['canvas']}; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent; color: {c['muted']}; border: 0;
    border-bottom: 2px solid transparent; padding: 10px 12px; margin-right: 2px;
}}
QTabBar::tab:hover {{ background: {c['hover']}; color: {c['text']}; }}
QTabBar::tab:selected {{ color: {c['accent']}; border-bottom-color: {c['accent']}; font-weight: 600; }}
QTabBar QToolButton {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; }}
QListWidget, QTableWidget {{
    background: {c['surface']}; alternate-background-color: {c['raised']};
    border: 1px solid {c['border']}; border-radius: 8px;
    selection-background-color: {c['selection']}; selection-color: {c['selection_text']};
    gridline-color: {c['border']}; outline: 0;
}}
QListWidget:focus, QTableWidget:focus {{ border-color: {c['accent']}; }}
QListWidget::item {{ padding: 12px 10px; border-bottom: 1px solid {c['border']}; }}
QListWidget::item:hover {{ background: {c['hover']}; }}
QListWidget::item:selected {{ background: {c['selection']}; color: {c['selection_text']}; }}
QWidget#sidebar QListWidget {{ border: 0; background: transparent; }}
QWidget#sidebar QListWidget::item {{ border-bottom: 0; margin: 2px 0; border-radius: 8px; }}
QHeaderView::section {{ background: {c['raised']}; color: {c['muted']}; border: 0; padding: 8px; }}
QTableCornerButton::section {{ background: {c['raised']}; border: 0; }}
QProgressBar {{
    border: 0; background: {c['raised']}; border-radius: 3px;
    min-height: 6px; max-height: 8px;
}}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 3px; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {c['control_border']}; border-radius: 3px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {c['muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSlider::groove:horizontal {{ height: 4px; background: {c['border']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {c['accent']}; border: 2px solid {c['surface']};
    width: 12px; margin: -6px 0; border-radius: 8px;
}}
QSlider::handle:horizontal:focus {{ border-color: {c['text']}; }}
QSplitter::handle {{ background: {c['border']}; }}
QSplitter::handle:hover {{ background: {c['accent']}; }}
QMenu, QToolTip {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 6px; }}
QMenu::item {{ padding: 6px 18px; }}
QMenu::item:selected {{ background: {c['selection']}; color: {c['selection_text']}; }}
'''
