"""Video Novel Studio: an offline PySide6 desktop editor and real media player."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import threading

from PySide6.QtCore import Qt, QObject, QThread, Signal, QUrl, Slot
from PySide6.QtGui import QFont, QPixmap, QDesktopServices
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink, QVideoFrame
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QListWidget, QListWidgetItem, QLineEdit,
    QPlainTextEdit, QDoubleSpinBox, QSpinBox, QCheckBox, QTabWidget, QSplitter,
    QScrollArea, QFormLayout, QFileDialog, QInputDialog,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView, QSlider,
    QStackedWidget, QFontComboBox, QAbstractItemView, QSizePolicy,
)

from .audio_manager import installed_voices, synthesize_local, inspect_narration
from .batch import render_batch
from .media import MediaError, atomic_json, audio_duration
from .scene_builder import Scene, load_episode, save_episode
from .settings import settings_for, card_durations
from .story_manager import StoryLibrary, BIBLES, atomic_text, fit_scene_to_audio, fit_episode_to_target
from .subtitle_generator import make_cues, cues_to_srt, parse_srt, validate_cues
from .video_renderer import render_episode, asset_errors
from .studio_panels import ProductionPanels
from .connection_panels import ConnectionPanels
from .exports import export_source


STYLE = '''
QMainWindow, QWidget { background: #f3f5f7; color: #263346; font-family: "Segoe UI"; font-size: 13px; }
QWidget#sidebar { background: #142234; color: #dce7ee; }
QWidget#sidebar QLabel { color: #c9d7e2; background: transparent; }
QWidget#sidebar QListWidget { background: #1a2c40; color: #dce7ee; border: 0; }
QWidget#sidebar QListWidget::item:selected { background: #28584f; color: #ffffff; }
QLabel#brand { font-size: 22px; font-weight: 700; color: #ffffff; }
QLabel#heading { font-size: 24px; font-weight: 650; }
QLabel#muted { color: #65758a; }
QLabel#preview { background: #111b2d; color: #b6c6d4; border-radius: 8px; }
QLabel#warning { color: #9b512b; }
QPushButton { background: #ffffff; border: 1px solid #d4dce3; padding: 8px 12px; border-radius: 6px; }
QPushButton:hover { background: #e4f1ec; border-color: #60b69c; }
QPushButton:disabled { color: #9aa5ae; background: #edf0f2; }
QPushButton#primary { background: #20735e; color: white; border: 1px solid #20735e; font-weight: 600; }
QPushButton#primary:hover { background: #195d4c; }
QLineEdit, QPlainTextEdit, QComboBox, QDoubleSpinBox, QSpinBox, QFontComboBox {
 background: #ffffff; border: 1px solid #d4dce3; border-radius: 5px; padding: 6px; selection-background-color: #20735e; }
QTabWidget::pane { background: #ffffff; border: 1px solid #dce2e7; border-radius: 6px; }
QTabBar::tab { padding: 10px 15px; margin-right: 3px; color: #52647a; }
QTabBar::tab:selected { background: #ffffff; color: #20735e; border-bottom: 3px solid #20735e; }
QListWidget, QTableWidget { background: #ffffff; border: 1px solid #dce2e7; border-radius: 6px; }
QListWidget::item { padding: 12px 8px; border-bottom: 1px solid #e8edf0; }
QListWidget::item:selected { background: #dceee7; color: #174c3e; }
QHeaderView::section { background: #eaf0f3; color: #52647a; border: 0; padding: 8px; }
QProgressBar { border: 0; background: #e0e7eb; border-radius: 5px; min-height: 10px; text-align: center; }
QProgressBar::chunk { background: #298d73; border-radius: 5px; }
QScrollArea { border: 0; }
'''


class Task(QObject):
    progress = Signal(float, str)
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, function, cancel):
        super().__init__()
        self.function, self.cancel = function, cancel

    @Slot()
    def run(self):
        try:
            result = self.function(self.progress.emit, self.cancel)
            self.succeeded.emit(result)
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.finished.emit()


class VideoPreview(QLabel):
    """Display the player's real decoded frames, including in desktop captures."""
    def __init__(self):
        super().__init__()
        self.setObjectName('preview')
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(230, 390)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.sink = QVideoSink(self)
        self.last_image = None
        self.sink.videoFrameChanged.connect(self._frame)

    def videoSink(self):
        return self.sink

    @Slot(QVideoFrame)
    def _frame(self, frame):
        if frame.isValid():
            image = frame.toImage()
            if not image.isNull():
                self.last_image = image
                self.setPixmap(QPixmap.fromImage(image).scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


def button(text, action=None, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName('primary')
    if action:
        widget.clicked.connect(action)
    return widget


def double_spin(minimum=0, maximum=3600, value=0, decimals=3):
    widget = QDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setDecimals(decimals)
    widget.setValue(value)
    return widget


class StudioWindow(ProductionPanels, ConnectionPanels, QMainWindow):
    def __init__(self, root: Path):
        super().__init__()
        self.library = StoryLibrary(root)
        self.episode = None
        self.story = None
        self.scene_index = -1
        self._loading = False
        self._document_name = BIBLES[0]
        self._thread = None
        self._closing = False
        self._completion = None
        self._cancel = threading.Event()
        self.last_error = ''
        self.last_report = None
        self.captions_dirty = False
        self.state_path = self.library.root / '.studio_state.json'
        self.state = {}
        if self.state_path.is_file():
            try:
                state = json.loads(self.state_path.read_text(encoding='utf-8'))
                if isinstance(state, dict):
                    self.state = {key: value for key, value in state.items()
                                  if key in ('story', 'episode') and isinstance(value, str)}
            except (ValueError, OSError):
                pass
        self.setWindowTitle('Video Novel Studio')
        self.resize(1440, 940)
        self.setMinimumSize(1140, 760)
        self.setStyleSheet(STYLE)
        self.voices = installed_voices()
        self._build()
        self.refresh_library()

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sidebar = QWidget()
        self.sidebar.setObjectName('sidebar')
        self.sidebar.setFixedWidth(235)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(18, 24, 18, 20)
        brand = QLabel('Video Novel\nStudio')
        brand.setObjectName('brand')
        side.addWidget(brand)
        side.addWidget(QLabel('LOCAL STORIES. REAL VIDEOS.'))
        side.addSpacing(22)
        side.addWidget(QLabel('STORY LIBRARY'))
        self.story_combo = QComboBox()
        self.story_combo.currentIndexChanged.connect(self._story_changed)
        side.addWidget(self.story_combo)
        self.new_story_button = button('+ New story', self.new_story)
        side.addWidget(self.new_story_button)
        side.addSpacing(14)
        side.addWidget(QLabel('EPISODES'))
        self.episode_list = QListWidget()
        self.episode_list.currentRowChanged.connect(self._episode_changed)
        side.addWidget(self.episode_list, 1)
        self.new_episode_button = button('+ New episode', self.new_episode)
        side.addWidget(self.new_episode_button)
        side.addSpacing(10)
        side.addWidget(button('Open workspace', lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.library.root)))))
        offline = QLabel('Offline by design\nImages + voice + FFmpeg')
        offline.setWordWrap(True)
        side.addWidget(offline)
        outer.addWidget(self.sidebar)

        main = QVBoxLayout()
        main.setContentsMargins(24, 22, 24, 18)
        header = QHBoxLayout()
        text_column = QVBoxLayout()
        self.heading = QLabel('Your next story starts here')
        self.heading.setObjectName('heading')
        self.summary = QLabel('Create a story or open an episode from the library.')
        self.summary.setObjectName('muted')
        text_column.addWidget(self.heading)
        text_column.addWidget(self.summary)
        header.addLayout(text_column, 1)
        self.save_button = button('Save project', self.save_all)
        self.check_button = button('Check assets', self.check_assets)
        header.addWidget(self.save_button)
        header.addWidget(self.check_button)
        main.addLayout(header)
        main.addSpacing(12)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._scene_tab(), 'Scenes / preview')
        self.tabs.addTab(self._writing_tab(), 'Writing')
        self.tabs.addTab(self._bible_tab(), 'Story bibles')
        self.tabs.addTab(self._audio_tab(), 'Audio / output')
        self.tabs.addTab(self._caption_tab(), 'Timeline / captions')
        self.tabs.addTab(self._exports_tab(), 'Exports')
        self.tabs.addTab(self._series_tab(), 'Series')
        self.tabs.addTab(self._publishing_tab(), 'Publishing')
        self.tabs.addTab(self._connections_tab(), 'Connections / AI')
        main.addWidget(self.tabs, 1)
        footer = QHBoxLayout()
        self.preview_button = button('Render preview · 360p', lambda: self.start_render(preview=True))
        self.render_button = button('Render MP4', lambda: self.start_render(), True)
        self.batch_button = button('Render story batch', self.start_batch)
        self.cancel_button = button('Cancel job', self.cancel_job)
        self.cancel_button.setEnabled(False)
        for widget in (self.preview_button, self.render_button, self.batch_button):
            footer.addWidget(widget)
        footer.addStretch()
        footer.addWidget(self.cancel_button)
        main.addLayout(footer)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        main.addWidget(self.progress_bar)
        self.status = QLabel('Ready · all work stays on this computer')
        self.status.setWordWrap(True)
        self.status.setObjectName('muted')
        main.addWidget(self.status)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(80)
        self.log.setPlaceholderText('Render and validation details appear here.')
        main.addWidget(self.log)
        outer.addLayout(main, 1)

    def _scene_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        splitter = QSplitter()
        scene_column = QWidget()
        column = QVBoxLayout(scene_column)
        column.setContentsMargins(0, 6, 4, 0)
        column.addWidget(QLabel('SCENE TIMELINE'))
        self.scene_list = QListWidget()
        self.scene_list.currentRowChanged.connect(self._scene_changed)
        column.addWidget(self.scene_list, 1)
        self.add_scene_button = button('+ Add scene', self.add_scene)
        column.addWidget(self.add_scene_button)
        row = QHBoxLayout()
        self.up_button = button('↑', lambda: self.move_scene(-1))
        self.down_button = button('↓', lambda: self.move_scene(1))
        self.remove_scene_button = button('Remove', self.remove_scene)
        for widget in (self.up_button, self.down_button, self.remove_scene_button):
            row.addWidget(widget)
        column.addLayout(row)
        splitter.addWidget(scene_column)

        editor = QWidget()
        form = QFormLayout(editor)
        form.setContentsMargins(10, 8, 14, 8)
        self.visual_path = QLineEdit()
        self.visual_path.setPlaceholderText('Choose a local image or video')
        image_row = QHBoxLayout()
        image_row.addWidget(self.visual_path, 1)
        self.import_image_button = button('Browse…', self.import_image)
        image_row.addWidget(self.import_image_button)
        form.addRow('Scene visual', image_row)
        self.media_type_combo = QComboBox()
        self.media_type_combo.addItems(['image', 'video'])
        self.media_type_combo.currentTextChanged.connect(self._media_type_changed)
        form.addRow('Media type', self.media_type_combo)
        self.video_start_spin = double_spin(0, 86400, 0)
        self.video_volume_spin = double_spin(0, 1, 0)
        self.video_volume_spin.setSingleStep(.05)
        form.addRow('Video trim start (s)', self.video_start_spin)
        form.addRow('Video sound (0 = mute)', self.video_volume_spin)
        form.addRow(button('Fit scene to remaining video', lambda: self._guard(self._fit_video)))
        self.asset_status = QLabel('Choose an image and narration recording.')
        self.asset_status.setWordWrap(True)
        self.asset_status.setObjectName('warning')
        form.addRow(self.asset_status)
        shared = button('Use shared character / background…', self.use_shared_image)
        form.addRow(shared)
        self.narration_text = QPlainTextEdit()
        self.narration_text.setPlaceholderText('The spoken narration for this scene…')
        self.narration_text.setMinimumHeight(115)
        self.narration_text.setMaximumHeight(180)
        form.addRow('Narration', self.narration_text)
        self.audio_path = QLineEdit()
        self.audio_path.setPlaceholderText('Uses episode recording when empty')
        form.addRow('Voice clip', self.audio_path)
        audio_row = QHBoxLayout()
        self.import_audio_button = button('Import voice…', self.import_scene_audio)
        self.tts_button = button('Create local voice', self.create_voice)
        self.tts_button.setEnabled(bool(self.voices))
        self.tts_button.setToolTip('Installed Windows System.Speech; no internet service.' if self.voices else 'No supported installed voice. Import recorded narration instead.')
        audio_row.addWidget(self.import_audio_button)
        audio_row.addWidget(self.tts_button)
        form.addRow(audio_row)
        timing = QHBoxLayout()
        self.duration_spin = double_spin(1 / 60, 3600, 6)
        self.duration_spin.setSingleStep(1 / 30)
        self.duration_spin.setSuffix(' s')
        self.fit_button = button('Fit to audio', self.fit_audio)
        timing.addWidget(self.duration_spin)
        timing.addWidget(self.fit_button)
        form.addRow('Scene duration', timing)
        self.motion_combo = QComboBox()
        self.motion_combo.addItems(['static', 'slow_zoom_in', 'slow_zoom_out', 'pan_left', 'pan_right', 'parallax'])
        form.addRow('Camera motion', self.motion_combo)
        transitions = QHBoxLayout()
        self.transition_combo = QComboBox()
        self.transition_combo.addItems(['cut', 'crossfade', 'fade_black'])
        self.transition_duration = double_spin(.033, 3, .5)
        self.transition_duration.setSuffix(' s')
        transitions.addWidget(self.transition_combo)
        transitions.addWidget(self.transition_duration)
        form.addRow('Transition in', transitions)
        foreground = QHBoxLayout()
        self.foreground_path = QLineEdit()
        self.foreground_path.setPlaceholderText('Optional transparent PNG for parallax')
        foreground.addWidget(self.foreground_path)
        foreground.addWidget(button('Layer…', self.import_foreground))
        form.addRow('Foreground', foreground)
        self.caption_default = QCheckBox('Use narration text for captions')
        self.caption_default.setChecked(True)
        form.addRow(self.caption_default)
        self.caption_text = QPlainTextEdit()
        self.caption_text.setMaximumHeight(80)
        self.caption_text.setEnabled(False)
        self.caption_default.toggled.connect(lambda checked: self.caption_text.setEnabled(not checked))
        form.addRow('Caption override', self.caption_text)
        self.style_combo = QComboBox()
        self.style_combo.addItems(['cinematic', 'standard'])
        form.addRow('Caption preset', self.style_combo)
        self.scene_characters = QListWidget()
        self.scene_characters.setMaximumHeight(100)
        form.addRow('Linked characters', self.scene_characters)
        self.scene_location = QComboBox()
        form.addRow('Linked location', self.scene_location)
        hint = QLabel('Text edits do not change a recording. Re-record or create a local voice after revising narration.')
        hint.setWordWrap(True)
        hint.setObjectName('muted')
        form.addRow(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(editor)
        splitter.addWidget(scroll)

        preview_column = QWidget()
        preview = QVBoxLayout(preview_column)
        preview.addWidget(QLabel('EPISODE PREVIEW'))
        self.preview_stack = QStackedWidget()
        self.image_preview = QLabel('Select a scene\nto preview its artwork')
        self.image_preview.setObjectName('preview')
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setMinimumSize(230, 390)
        self.image_preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.preview_stack.addWidget(self.image_preview)
        self.video_widget = VideoPreview()
        self.preview_stack.addWidget(self.video_widget)
        preview.addWidget(self.preview_stack, 1)
        self.preview_label = QLabel('Still artwork · render a preview to see motion and captions')
        self.preview_label.setWordWrap(True)
        self.preview_label.setObjectName('muted')
        preview.addWidget(self.preview_label)
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(.65)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoSink(self.video_widget.videoSink())
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.sliderMoved.connect(self.player.setPosition)
        self.player.positionChanged.connect(lambda position: self.seek_slider.setValue(position))
        self.player.durationChanged.connect(lambda duration: self.seek_slider.setRange(0, duration))
        self.player.errorOccurred.connect(lambda error, message: self._set_status('Playback error: ' + message))
        preview.addWidget(self.seek_slider)
        controls = QHBoxLayout()
        self.play_button = button('Play / pause', self.toggle_play)
        controls.addWidget(self.play_button)
        controls.addWidget(button('Scene still', self.show_still))
        preview.addLayout(controls)
        splitter.addWidget(preview_column)
        splitter.setSizes([205, 430, 280])
        layout.addWidget(splitter)
        return tab

    def _writing_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()
        self.title_edit = QLineEdit()
        self.hook_edit = QLineEdit()
        self.cliffhanger_edit = QLineEdit()
        form.addRow('Episode title', self.title_edit)
        form.addRow('Opening hook', self.hook_edit)
        form.addRow('Cliffhanger', self.cliffhanger_edit)
        layout.addLayout(form)
        self.script_editor = QPlainTextEdit()
        self.script_editor.setPlaceholderText('Write one paragraph per scene, or use ## Scene 1 headings. The breakdown uses your words.')
        layout.addWidget(self.script_editor, 2)
        row = QHBoxLayout()
        self.breakdown_button = button('Build scenes from script', self.breakdown_script)
        row.addWidget(self.breakdown_button)
        row.addWidget(button('Import manuscript…', self.import_manuscript))
        row.addWidget(button('Save writing', self.save_all))
        row.addWidget(button('Refresh previous continuity', self.refresh_continuity))
        row.addStretch()
        layout.addLayout(row)
        warning = QLabel('Build scenes uses a deterministic paragraph breakdown and estimates timing at 138 words/minute. It creates editable hook/cliffhanger drafts from your first and last sentences. Import new narration after rebuilding.')
        warning.setWordWrap(True)
        warning.setObjectName('muted')
        layout.addWidget(warning)
        self.continuity_preview = QPlainTextEdit()
        self.continuity_preview.setReadOnly(True)
        layout.addWidget(self.continuity_preview, 1)
        return tab

    def _bible_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        row = QHBoxLayout()
        self.bible_combo = QComboBox()
        self.bible_combo.addItems(BIBLES)
        self.bible_combo.currentTextChanged.connect(self._bible_changed)
        row.addWidget(self.bible_combo)
        row.addStretch()
        row.addWidget(button('Save document', self.save_bible))
        layout.addLayout(row)
        self.bible_editor = QPlainTextEdit()
        layout.addWidget(self.bible_editor)
        return tab

    def _audio_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        form = QFormLayout()
        self.settings_widgets = {}
        for key, label, minimum, maximum, value in (
            ('target_duration', 'Target length (seconds)', 1, 3600, 75),
            ('title_duration', 'Title card duration', 0, 30, 2),
            ('end_duration', 'End card duration', 0, 30, 2),
            ('narration_volume', 'Narration volume (0–2)', 0, 2, 1),
            ('music_volume', 'Music volume (0–1)', 0, 1, .16),
        ):
            widget = double_spin(minimum, maximum, value)
            self.settings_widgets[key] = widget
        self.settings_widgets['title_card'] = QLineEdit()
        self.settings_widgets['end_card'] = QLineEdit()
        form.addRow('Target length (seconds)', self.settings_widgets['target_duration'])
        target_hint = QLabel('Default target: 75 seconds (60–90). Durations follow your scenes; the studio never cuts narration to meet a target.')
        target_hint.setWordWrap(True)
        form.addRow(target_hint)
        form.addRow(button('Fit scenes to target duration', self.fit_target))
        form.addRow('Title card text (optional)', self.settings_widgets['title_card'])
        form.addRow('Title card duration', self.settings_widgets['title_duration'])
        form.addRow('End card text (optional)', self.settings_widgets['end_card'])
        form.addRow('End card duration', self.settings_widgets['end_duration'])
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(['1080 × 1920', '720 × 1280', '360 × 640'])
        form.addRow('MP4 resolution', self.resolution_combo)
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(['30', '24', '60'])
        form.addRow('Frames per second', self.fps_combo)
        self.episode_audio_path = QLineEdit()
        row = QHBoxLayout()
        row.addWidget(self.episode_audio_path)
        row.addWidget(button('Import episode voice…', self.import_episode_audio))
        form.addRow('Episode recording', row)
        form.addRow('Narration volume (0–2)', self.settings_widgets['narration_volume'])
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(self.voices or ['No supported installed voice — import a recording'])
        form.addRow('Installed offline voice', self.voice_combo)
        self.voice_rate = QSpinBox()
        self.voice_rate.setRange(-10, 10)
        self.voice_rate.setValue(-1)
        form.addRow('Local voice speed (−10 to 10)', self.voice_rate)
        self.music_path = QLineEdit()
        row = QHBoxLayout()
        row.addWidget(self.music_path)
        row.addWidget(button('Import music…', self.import_music))
        row.addWidget(button('Clear', lambda: self.music_path.clear()))
        form.addRow('Background music', row)
        form.addRow('Music volume (0–1)', self.settings_widgets['music_volume'])
        self.duck_music = QCheckBox('Lower music automatically while narration plays')
        self.duck_music.setChecked(True)
        form.addRow(self.duck_music)
        self.caption_font = QFontComboBox()
        form.addRow('Caption font', self.caption_font)
        for key, label, minimum, maximum, value in (
            ('font_size', 'Caption font size (1080p units)', 10, 120, 58),
            ('margin_bottom', 'Bottom safe margin (1080p units)', 0, 1000, 360),
            ('margin_left', 'Left margin', 0, 400, 90),
            ('margin_right', 'Right safe margin', 0, 400, 180),
            ('outline', 'Caption outline', 0, 10, 3),
            ('shadow', 'Caption shadow', 0, 10, 1),
            ('wrap_chars', 'Characters per caption line', 10, 60, 30),
            ('caption_words', 'Maximum words per cue', 1, 20, 9),
        ):
            widget = QSpinBox()
            widget.setRange(minimum, maximum)
            widget.setValue(value)
            self.settings_widgets[key] = widget
            form.addRow(label, widget)
        layout.addLayout(form)
        layout.addWidget(QLabel('SOUND EFFECTS · start times include the title card'))
        self.effects_table = QTableWidget(0, 3)
        self.effects_table.setHorizontalHeaderLabels(['Asset', 'Start (s)', 'Volume (0–1)'])
        self.effects_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.effects_table.setMinimumHeight(150)
        layout.addWidget(self.effects_table)
        row = QHBoxLayout()
        row.addWidget(button('+ Import sound effect…', self.import_effect))
        row.addWidget(button('Remove effect', lambda: self.effects_table.removeRow(self.effects_table.currentRow()) if self.effects_table.currentRow() >= 0 else None))
        row.addStretch()
        layout.addLayout(row)
        scroll.setWidget(content)
        return scroll

    def _caption_tab(self):
        return ProductionPanels._caption_tab(self)

    def _exports_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.export_table = QTableWidget(0, 4)
        self.export_table.setHorizontalHeaderLabels(['Export', 'Resolution / FPS', 'Duration', 'Verification'])
        self.export_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.export_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.export_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.export_table)
        row = QHBoxLayout()
        row.addWidget(button('Play selected', self.play_selected_export))
        row.addWidget(button('Open exports folder', lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.library.root / 'exports')))))
        row.addWidget(button('Refresh', self.refresh_exports))
        row.addStretch()
        layout.addLayout(row)
        return tab

    def _set_status(self, message):
        self.status.setText(str(message))

    def _error(self, error):
        self.last_error = str(error).strip() or (type(error).__name__ if isinstance(error, BaseException) else 'Operation failed.')
        self._set_status(self.last_error.splitlines()[0])
        self.log.appendPlainText(self.last_error)

    def _guard(self, function):
        try:
            return function()
        except Exception as error:
            self._error(error)
            return None

    def refresh_library(self, select_story=None, select_episode=None):
        stories = self.library.stories()
        self.story_combo.blockSignals(True)
        self.story_combo.clear()
        for story in stories:
            self.story_combo.addItem(self.library.story_title(story), str(story))
        self.story_combo.blockSignals(False)
        desired = str(select_story) if select_story else self.state.get('story', '')
        index = self.story_combo.findData(desired)
        if index < 0:
            index = next((i for i, story in enumerate(stories) if story.name == 'the_letter_at_the_gate'), 0)
        if stories:
            self.story_combo.blockSignals(True)
            self.story_combo.setCurrentIndex(index)
            self.story_combo.blockSignals(False)
            self._story_changed(index, select_episode=select_episode)
        self.refresh_exports()

    def _story_changed(self, index, select_episode=None):
        if self._loading or index < 0:
            return
        if self.episode and not self.save_all(quiet=True):
            return
        self.story = Path(self.story_combo.itemData(index))
        self.episode = None
        self.scene_index = -1
        self.episode_list.blockSignals(True)
        self.episode_list.clear()
        paths = self.library.episodes(self.story)
        for path in paths:
            try:
                episode = load_episode(path)
                label = f'{episode.episode_id.replace("episode_", "EP ")}\n{episode.title}'
            except Exception:
                label = f'{path.parent.name}\nInvalid scene file — open to see error'
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.episode_list.addItem(item)
        self.episode_list.blockSignals(False)
        self._document_name = self.bible_combo.currentText()
        self._load_bible()
        wanted = str(select_episode) if select_episode else self.state.get('episode', '')
        row = next((i for i, path in enumerate(paths) if str(path) == wanted), 0)
        if paths:
            self.episode_list.setCurrentRow(row)
        else:
            self.heading.setText(self.library.story_title(self.story))
            self.summary.setText('Create the first episode to begin.')
            self.scene_list.clear()

    def _episode_changed(self, row):
        if self._loading or row < 0:
            return
        if self.episode and not self.save_all(quiet=True):
            return
        item = self.episode_list.item(row)
        self._guard(lambda: self.load_project(Path(item.data(Qt.ItemDataRole.UserRole))))

    def load_project(self, path: Path):
        episode = load_episode(path)
        self.player.stop()
        self.player.setSource(QUrl())
        self.narration_player.stop()
        self.narration_player.setSource(QUrl())
        self.wave_data, self.wave_signature = None, None
        self._audition_scene = None
        self.timeline_video.clear()
        self.timeline_video.setText('Play the last rendered video\nfor this episode')
        self.timeline_video_note.setText('Last rendered video · edits need a rerender')
        self.live_caption.setText('Current cue appears here while you listen.')
        self.episode = episode
        self.story = episode.directory.parent.parent
        self.scene_index = -1
        self._loading = True
        try:
            # Keep the sidebar accurate when opening a path directly or applying
            # a reviewed draft with a changed episode title.
            self.story_combo.blockSignals(True)
            self.story_combo.setCurrentIndex(self.story_combo.findData(str(self.story)))
            self.story_combo.blockSignals(False)
            self.episode_list.blockSignals(True)
            self.episode_list.clear()
            for candidate in self.library.episodes(self.story):
                try:
                    item_episode = load_episode(candidate)
                    title = item_episode.title
                except (ValueError, OSError):
                    title = 'Invalid scene file'
                item = QListWidgetItem(f'{candidate.parent.name.replace("episode_", "EP ")}\n{title}')
                item.setData(Qt.ItemDataRole.UserRole, str(candidate))
                self.episode_list.addItem(item)
                if candidate.resolve() == path.resolve():
                    self.episode_list.setCurrentItem(item)
            self.episode_list.blockSignals(False)
            self._load_series_panels()
            self.title_edit.setText(episode.title)
            self.hook_edit.setText(episode.metadata.get('hook', ''))
            self.cliffhanger_edit.setText(episode.metadata.get('cliffhanger', ''))
            script = episode.directory / 'script.md'
            self.script_editor.setPlainText(script.read_text(encoding='utf-8') if script.is_file() else '')
            settings = settings_for(episode)
            for key, widget in self.settings_widgets.items():
                if isinstance(widget, QLineEdit):
                    widget.setText(settings[key])
                else:
                    widget.setValue(settings[key])
            resolution = f'{settings["width"]} × {settings["height"]}'
            if self.resolution_combo.findText(resolution) < 0:
                self.resolution_combo.addItem(resolution)
            self.resolution_combo.setCurrentText(resolution)
            fps = str(settings['fps'])
            if self.fps_combo.findText(fps) < 0:
                self.fps_combo.addItem(fps)
            self.fps_combo.setCurrentText(fps)
            self.episode_audio_path.setText(settings['narration_asset'])
            self.music_path.setText(settings['music_asset'])
            self.duck_music.setChecked(settings['duck_music'])
            self.caption_font.setCurrentFont(QFont(settings['font']))
            self.voice_combo.setCurrentText(episode.metadata.get('voice', self.voices[0] if self.voices else self.voice_combo.currentText()))
            self.voice_rate.setValue(episode.metadata.get('voice_rate', -1))
            self.subtitle_mode.setCurrentText(settings['subtitle_mode'])
            self.effects_table.setRowCount(0)
            for effect in settings['sound_effects']:
                self._add_effect_row(effect)
            self._refresh_scene_list(0)
            self._populate_scene(0)
            subtitle_path = episode.directory / 'subtitles.srt'
            try:
                cues = parse_srt(subtitle_path.read_text(encoding='utf-8-sig')) if subtitle_path.is_file() else []
            except ValueError as error:
                self._error(error)
                cues = []
            self._populate_captions(cues)
            self._sync_auto_captions()
            self._load_bible()
            self.library.refresh_continuity(episode)
            self.continuity_preview.setPlainText((episode.directory / 'continuity_context.md').read_text(encoding='utf-8'))
        finally:
            self._loading = False
        self._update_summary()
        self._refresh_timeline()
        self.publish_table.setRowCount(0)
        self.publish_summary.setText('Run a publishing check for this episode.')
        self.state.update({'story': str(self.story), 'episode': str(path)})
        atomic_json(self.state_path, self.state)
        self._set_status(f'Opened {episode.title}')

    def _update_summary(self):
        if not self.episode:
            return
        settings = settings_for(self.episode)
        title, end = card_durations(settings)
        length = self.episode.timeline()[-1].end_seconds + title + end
        self.heading.setText(self.episode.title)
        self.summary.setText(f'{len(self.episode.scenes)} scenes  ·  {length:.1f}s / {settings["target_duration"]:g}s target  ·  {settings["width"]} × {settings["height"]}  ·  {settings["fps"]} FPS')

    def _refresh_scene_list(self, select=None):
        self.scene_list.blockSignals(True)
        self.scene_list.clear()
        if self.episode:
            for timed in self.episode.timeline():
                scene = timed.scene
                ready = self.episode.resolve_asset(scene.visual_asset).is_file()
                label = f'{scene.scene_id:02}   {scene.narration[:35] or "Untitled scene"}\n{timed.start_seconds:.1f}–{timed.end_seconds:.1f}s  ·  {scene.media_type.title()} {"ready" if ready else "missing"}'
                self.scene_list.addItem(label)
            selected = select if select is not None else self.scene_index
            self.scene_list.setCurrentRow(max(0, min(selected, len(self.episode.scenes)-1)))
        self.scene_list.blockSignals(False)

    def _scene_changed(self, row):
        if self._loading or not self.episode or row < 0:
            return
        self._guard(self._commit_scene)
        self._populate_scene(row)
        self._refresh_scene_list(row)

    def _populate_scene(self, row):
        if not self.episode or not 0 <= row < len(self.episode.scenes):
            return
        self.scene_index = row
        scene = self.episode.scenes[row]
        self.visual_path.setText(scene.visual_asset)
        self.media_type_combo.setCurrentText(scene.media_type)
        self.video_start_spin.setValue(scene.video_start_seconds)
        self.video_volume_spin.setValue(scene.video_audio_volume)
        self.narration_text.setPlainText(scene.narration)
        self.audio_path.setText(scene.narration_audio or '')
        self.duration_spin.setValue(scene.duration_seconds)
        self.motion_combo.setCurrentText(scene.camera_motion)
        self.transition_combo.setCurrentText(scene.transition)
        self.transition_duration.setValue(scene.transition_seconds)
        self.foreground_path.setText(scene.foreground_asset or '')
        self.caption_default.setChecked(scene.subtitle is None)
        self.caption_text.setPlainText(scene.subtitle or '')
        self.style_combo.setCurrentText(scene.subtitle_style)
        self._populate_scene_references(scene)
        missing = []
        if not self.episode.resolve_asset(scene.visual_asset).is_file():
            missing.append('Image missing')
        audio = scene.narration_audio or self.episode.settings.get('narration_asset', 'narration.wav')
        if scene.narration and not self.episode.resolve_asset(audio).is_file():
            missing.append('Narration missing')
        self.asset_status.setText(' · '.join(missing) if missing else 'Files present · use Check assets to validate timing and formats')
        self.asset_status.setStyleSheet('color: #9b512b;' if missing else 'color: #20735e;')
        self.show_still()

    def _commit_scene(self):
        if not self.episode or self.scene_index < 0:
            return
        scenes = list(self.episode.scenes)
        fps = int(self.fps_combo.currentText())
        duration = max(1, round(self.duration_spin.value() * fps)) / fps
        scenes[self.scene_index] = replace(scenes[self.scene_index],
            duration_seconds=duration, visual_asset=self.visual_path.text().strip() or 'assets/scene.png',
            narration=self.narration_text.toPlainText(), narration_audio=self.audio_path.text().strip() or None,
            camera_motion=self.motion_combo.currentText(), transition=self.transition_combo.currentText(),
            transition_seconds=self.transition_duration.value(), foreground_asset=self.foreground_path.text().strip() or None,
            subtitle=None if self.caption_default.isChecked() else self.caption_text.toPlainText(),
            subtitle_style=self.style_combo.currentText(),
            characters=tuple(self.scene_characters.item(i).data(Qt.ItemDataRole.UserRole)
                             for i in range(self.scene_characters.count())
                             if self.scene_characters.item(i).checkState() == Qt.CheckState.Checked),
            location=self.scene_location.currentData() or None,
            media_type=self.media_type_combo.currentText(), video_start_seconds=self.video_start_spin.value(),
            video_audio_volume=self.video_volume_spin.value())
        self.episode = replace(self.episode, scenes=tuple(scenes))

    def _collect_settings(self):
        settings = dict(self.episode.settings)
        for key, widget in self.settings_widgets.items():
            settings[key] = widget.text() if isinstance(widget, QLineEdit) else widget.value()
        width, height = [int(part.strip()) for part in self.resolution_combo.currentText().split('×')]
        settings.update({'width': width, 'height': height, 'fps': int(self.fps_combo.currentText()),
                         'narration_asset': self.episode_audio_path.text().strip(), 'music_asset': self.music_path.text().strip(),
                         'duck_music': self.duck_music.isChecked(), 'font': self.caption_font.currentFont().family(),
                         'subtitle_mode': self.subtitle_mode.currentText()})
        settings['sound_effects'] = [{'asset': self.effects_table.item(row, 0).text(),
                                      'start_seconds': float(self.effects_table.item(row, 1).text()),
                                      'volume': float(self.effects_table.item(row, 2).text())}
                                     for row in range(self.effects_table.rowCount())]
        return settings

    def _save(self, *, regenerate_captions=False):
        if not self.episode:
            return True
        self._commit_scene()
        settings = self._collect_settings()
        self._save_series_data()
        metadata = {**self.episode.metadata, 'hook': self.hook_edit.text(), 'cliffhanger': self.cliffhanger_edit.text(),
                    'voice': self.voice_combo.currentText() if self.voices else '', 'voice_rate': self.voice_rate.value()}
        self.episode = replace(self.episode, title=self.title_edit.text().strip() or self.episode.title, settings=settings, metadata=metadata)
        if regenerate_captions:
            # Explicit regeneration must recover even when the edited table has
            # invalid timestamps. Validate replacement cues before discarding it.
            cues = make_cues(self.episode, inspect_narration(self.episode))
            self.episode = replace(self.episode, settings={**settings, 'subtitle_mode': 'auto'})
            self.subtitle_mode.setCurrentText('auto')
            self._populate_captions(cues)
            atomic_text(self.episode.directory / 'subtitles.srt', cues_to_srt(cues))
        elif self.captions_dirty:
            self._save_manual_captions()
        elif settings['subtitle_mode'] == 'auto':
            self._sync_auto_captions()
        save_episode(self.episode)
        self.library.write_outline(self.episode)
        atomic_text(self.episode.directory / 'script.md', self.script_editor.toPlainText())
        self._save_bible()
        self._refresh_scene_list()
        self._update_summary()
        self._refresh_timeline()
        self.publish_summary.setText('Project saved. Run publishing check again after edits.')
        self.state.update({'story': str(self.story), 'episode': str(self.episode.directory / 'scenes.json')})
        atomic_json(self.state_path, self.state)
        return True

    def save_all(self, checked=False, *, quiet=False):
        result = self._guard(self._save)
        if result and not quiet:
            self._set_status('Saved project, script, scene breakdown and story document.')
        return bool(result)

    def new_story(self):
        title, accepted = QInputDialog.getText(self, 'New story', 'Story title')
        if not accepted or not title.strip() or not self.save_all(quiet=True):
            return
        def create():
            story = self.library.create_story(title)
            episode = self.library.create_episode(story)
            self.refresh_library(story, episode.directory / 'scenes.json')
        self._guard(create)

    def new_episode(self):
        if not self.story or not self.save_all(quiet=True):
            return
        def create():
            episode = self.library.create_episode(self.story)
            self.refresh_library(self.story, episode.directory / 'scenes.json')
        self._guard(create)

    def add_scene(self):
        if not self.episode:
            return
        self._commit_scene()
        number = max(scene.scene_id for scene in self.episode.scenes) + 1
        scene = Scene(number, 6, f'assets/scene_{number:03}.png', '', 'slow_zoom_in', self.style_combo.currentText(), transition='crossfade')
        self.episode = replace(self.episode, scenes=(*self.episode.scenes, scene))
        self._refresh_scene_list(len(self.episode.scenes)-1)
        self._populate_scene(len(self.episode.scenes)-1)
        self.save_all()

    def move_scene(self, direction):
        if not self.episode:
            return
        self._commit_scene()
        target = self.scene_index + direction
        if not 0 <= target < len(self.episode.scenes):
            return
        scenes = list(self.episode.scenes)
        scenes[self.scene_index], scenes[target] = scenes[target], scenes[self.scene_index]
        self.episode = replace(self.episode, scenes=tuple(scenes))
        self._refresh_scene_list(target)
        self._populate_scene(target)
        self.save_all()

    def remove_scene(self):
        if not self.episode or len(self.episode.scenes) < 2:
            self._set_status('Keep at least one scene in an episode.')
            return
        self._commit_scene()
        scenes = list(self.episode.scenes)
        del scenes[self.scene_index]
        self.episode = replace(self.episode, scenes=tuple(scenes))
        index = min(self.scene_index, len(scenes)-1)
        self._refresh_scene_list(index)
        self._populate_scene(index)
        self.save_all()

    def _choose(self, title, filter='All files (*)', directory=None):
        path, _ = QFileDialog.getOpenFileName(self, title, str(directory or self.library.root), filter)
        return Path(path) if path else None

    def import_image(self):
        source = self._choose('Import scene visual', 'Images / video (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.mp4 *.mov *.mkv *.webm);;All files (*)')
        if source and self.episode:
            self.media_type_combo.setCurrentText('video' if source.suffix.lower() in ('.mp4', '.mov', '.mkv', '.webm') else 'image')
            self.video_start_spin.setValue(0)
            self._guard(lambda: self.visual_path.setText(self.library.import_asset(self.episode, source)))
            self._commit_scene()
            self._populate_scene(self.scene_index)
            self.save_all()

    def _media_type_changed(self, value):
        # Called after construction, when the user changes the media selector.
        if value == 'video' and hasattr(self, 'motion_combo'):
            self.motion_combo.setCurrentText('static')
            self.foreground_path.clear()

    def use_shared_image(self):
        source = self._choose('Choose reusable character or background', 'Images (*.png *.jpg *.jpeg *.webp)', self.library.root / 'assets')
        if source and self.episode:
            self.media_type_combo.setCurrentText('image')
            self.visual_path.setText(Path(os.path.relpath(source, self.episode.directory)).as_posix())
            self._commit_scene()
            self._populate_scene(self.scene_index)
            self.save_all()

    def _fit_video(self):
        if not self.episode or self.scene_index < 0 or self.media_type_combo.currentText() != 'video':
            raise ValueError('Select a video scene first')
        from .video_assets import video_info
        self._commit_scene()
        scene = self.episode.scenes[self.scene_index]
        info = video_info(self.episode.resolve_asset(scene.visual_asset))
        fps = int(self.fps_combo.currentText())
        remaining = math.floor((info['duration'] - scene.video_start_seconds) * fps) / fps
        if remaining < 1 / fps:
            raise ValueError('No video remains after this trim start')
        title, _ = card_durations(settings_for(self.episode))
        start = title + self.episode.timeline()[self.scene_index].start_seconds
        self._timeline_edit('scene', self.scene_index, start, start + remaining)

    def import_foreground(self):
        source = self._choose('Import transparent foreground layer', 'PNG images (*.png)')
        if source and self.episode:
            self._guard(lambda: self.foreground_path.setText(self.library.import_asset(self.episode, source)))
            self.save_all()

    def import_scene_audio(self):
        source = self._choose('Import recorded scene narration', 'Audio (*.wav *.mp3 *.m4a *.aac *.flac *.ogg *.aiff);;All files (*)')
        if source and self.episode:
            def do_import():
                audio_duration(source)
                self.audio_path.setText(self.library.import_asset(self.episode, source))
                self._commit_scene()
                self.episode = fit_scene_to_audio(self.episode, self.scene_index)
                self._populate_scene(self.scene_index)
                self.save_all()
            self._guard(do_import)

    def import_episode_audio(self):
        source = self._choose('Import complete episode narration', 'Audio (*.wav *.mp3 *.m4a *.aac *.flac *.ogg);;All files (*)')
        if source and self.episode:
            def do_import():
                audio_duration(source)
                self.episode_audio_path.setText(self.library.import_asset(self.episode, source))
                self.save_all()
            self._guard(do_import)

    def import_music(self):
        source = self._choose('Import background music', 'Audio (*.wav *.mp3 *.m4a *.aac *.flac *.ogg);;All files (*)')
        if source and self.episode:
            self._guard(lambda: self.music_path.setText(self.library.import_asset(self.episode, source, category='music')))
            self.save_all()

    def _add_effect_row(self, effect):
        row = self.effects_table.rowCount()
        self.effects_table.insertRow(row)
        for column, key in enumerate(('asset', 'start_seconds', 'volume')):
            self.effects_table.setItem(row, column, QTableWidgetItem(str(effect[key])))

    def import_effect(self):
        source = self._choose('Import a sound effect', 'Audio (*.wav *.mp3 *.m4a *.aac *.flac *.ogg);;All files (*)')
        if source and self.episode:
            def do_import():
                audio_duration(source)
                asset = self.library.import_asset(self.episode, source, category='sound_effects')
                self._add_effect_row({'asset': asset, 'start_seconds': 0, 'volume': .2})
                self.save_all()
            self._guard(do_import)

    def fit_audio(self):
        if not self.episode:
            return
        self._commit_scene()
        def fit():
            self.episode = fit_scene_to_audio(self.episode, self.scene_index)
            self._populate_scene(self.scene_index)
            self.save_all()
        self._guard(fit)

    def fit_target(self):
        if not self.episode or not self.save_all(quiet=True):
            return
        def fit():
            self.episode = fit_episode_to_target(self.episode)
            self._populate_scene(self.scene_index)
            self.save_all()
            self._set_status('Scene durations fitted to the target while preserving complete narration. Regenerate manual captions after timing changes.')
        self._guard(fit)

    def import_manuscript(self):
        source = self._choose('Import a written episode or chapter', 'Text and Markdown (*.txt *.md);;All files (*)')
        if source and self.episode:
            def load():
                self.script_editor.setPlainText(source.read_text(encoding='utf-8-sig'))
                self.save_all()
                self._set_status('Manuscript saved. Use Build scenes from script to create an editable breakdown.')
            self._guard(load)

    def create_voice(self):
        if not self.episode or not self.save_all(quiet=True):
            return
        index = self.scene_index
        scene = self.episode.scenes[index]
        output = self.episode.directory / 'assets' / f'local_voice_{scene.scene_id:03}.wav'
        voice, rate = self.voice_combo.currentText(), self.voice_rate.value()
        def create(progress, cancel):
            progress(.1, 'Creating speech with the installed Windows voice')
            return synthesize_local(scene.narration, output, voice=voice, rate=rate, cancel=cancel)
        def completed(path):
            scenes = list(self.episode.scenes)
            scenes[index] = replace(scenes[index], narration_audio=Path(path).relative_to(self.episode.directory).as_posix())
            self.episode = replace(self.episode, scenes=tuple(scenes))
            self.episode = fit_scene_to_audio(self.episode, index)
            self._populate_scene(index)
            self.save_all()
            self._set_status('Local voice created and scene duration fitted to the recording.')
        self._run_task(create, completed)

    def _load_bible(self):
        if self.story:
            path = self.story / self._document_name
            self.bible_editor.setPlainText(path.read_text(encoding='utf-8') if path.is_file() else f'# {self._document_name.replace("_", " ").removesuffix(".md").title()}\n\n')

    def _save_bible(self):
        if self.story:
            atomic_text(self.story / self._document_name, self.bible_editor.toPlainText())

    def save_bible(self):
        self._guard(self._save_bible)
        self._set_status('Story document saved.')

    def _bible_changed(self, name):
        if self._loading:
            return
        self._guard(self._save_bible)
        self._document_name = name
        self._load_bible()

    def refresh_continuity(self):
        if self.episode and self.save_all(quiet=True):
            self.library.refresh_continuity(self.episode)
            self.continuity_preview.setPlainText((self.episode.directory / 'continuity_context.md').read_text(encoding='utf-8'))

    def breakdown_script(self):
        if not self.episode or not self.save_all(quiet=True):
            return
        def breakdown():
            updated = self.library.breakdown_script(self.episode, self.script_editor.toPlainText())
            self.load_project(updated.directory / 'scenes.json')
            self._set_status('Scene breakdown, hook, cliffhanger and continuity files created. Add or recreate narration for the new text.')
        self._guard(breakdown)

    def _populate_captions(self, cues):
        self.caption_table.blockSignals(True)
        self.caption_table.setRowCount(len(cues))
        for row, cue in enumerate(cues):
            for column, value in enumerate((f'{cue.start:.3f}', f'{cue.end:.3f}', cue.text)):
                self.caption_table.setItem(row, column, QTableWidgetItem(value))
            self.caption_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, cue.style)
        self.caption_table.resizeRowsToContents()
        self.caption_table.blockSignals(False)
        self.captions_dirty = False
        if hasattr(self, 'timeline'):
            self._refresh_timeline()

    def _caption_edited(self, item):
        if not self._loading:
            self.captions_dirty = True
            self._refresh_timeline()

    def generate_captions(self):
        if not self.episode:
            return
        if self._guard(lambda: self._save(regenerate_captions=True)):
            self._set_status(f'Generated {self.caption_table.rowCount()} cues using the actual narration duration. Review and adjust timing as needed.')

    def _sync_auto_captions(self):
        """Keep the timeline and saved auto SRT consistent with actual rendering."""
        if self.subtitle_mode.currentText() != 'auto' or self.captions_dirty:
            return
        try:
            cues = make_cues(self.episode, inspect_narration(self.episode))
        except (ValueError, OSError, MediaError):
            self._populate_captions([])
            return  # Missing recordings remain visible in asset/render validation.
        self._populate_captions(cues)
        atomic_text(self.episode.directory / 'subtitles.srt', cues_to_srt(cues))

    def _save_manual_captions(self):
        cues = self._table_cues()
        spans = inspect_narration(self.episode)
        title, end = card_durations(settings_for(self.episode))
        windows = [(title + timed.start_seconds, title + timed.start_seconds + (span.duration if span.path else timed.scene.duration_seconds))
                   for timed, span in zip(self.episode.timeline(), spans)]
        validate_cues(cues, title + self.episode.timeline()[-1].end_seconds + end, windows)
        atomic_text(self.episode.directory / 'subtitles.srt', cues_to_srt(cues))
        self.episode = replace(self.episode, settings={**self.episode.settings, 'subtitle_mode': 'manual'})
        self.subtitle_mode.setCurrentText('manual')
        self.captions_dirty = False

    def save_manual_captions(self):
        if not self.episode:
            return
        self.captions_dirty = True
        if self.save_all(quiet=True):
            self._set_status('Manual subtitle timings saved and selected for rendering.')

    def import_subtitles(self):
        source = self._choose('Import subtitles', 'SRT subtitles (*.srt)')
        if source and self.episode:
            def load():
                self._populate_captions(parse_srt(source.read_text(encoding='utf-8-sig')))
                self.save_manual_captions()
            self._guard(load)

    def _run_task(self, function, completion):
        if self._thread is not None:
            self._set_status('A job is already running. Finish it or cancel it first.')
            return
        self.narration_player.pause()
        self.player.pause()
        self._completion = completion
        self._cancel = threading.Event()
        self.last_error = ''
        self.last_report = None
        self.progress_bar.setValue(0)
        self._set_busy(True)
        self._thread = QThread(self)
        self._worker = Task(function, self._cancel)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._task_progress)
        self._worker.succeeded.connect(self._task_result)
        self._worker.failed.connect(self._task_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._task_finished)
        self._thread.start()

    def _set_busy(self, busy):
        self.tabs.setEnabled(not busy)
        self.sidebar.setEnabled(not busy)
        for widget in (self.save_button, self.check_button, self.preview_button, self.render_button, self.batch_button):
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

    @Slot(float, str)
    def _task_progress(self, fraction, message):
        self.progress_bar.setValue(round(fraction * 100))
        self._set_status(message)

    @Slot(object)
    def _task_result(self, result):
        if self._completion:
            self._guard(lambda: self._completion(result))

    @Slot(str)
    def _task_error(self, message):
        self._error(message)
        self.progress_bar.setValue(0)

    @Slot()
    def _task_finished(self):
        thread = self._thread
        self._thread = None
        self._set_busy(False)
        if thread:
            thread.deleteLater()
        self.refresh_exports()
        self._guard(self._refresh_generation_jobs)
        if self._closing:
            self.close()

    def cancel_job(self):
        self._cancel.set()
        self._set_status('Stopping this operation. A submitted provider job may continue; its saved ID can be resumed.')

    def check_assets(self):
        if not self.episode or not self.save_all(quiet=True):
            return
        episode = self.episode
        def check(progress, cancel):
            progress(.1, 'Checking images and narration')
            errors = asset_errors(episode)
            if errors:
                raise MediaError('\n'.join(errors))
            progress(1, 'Required scene assets and narration timing are valid.')
            return 'Required scene assets and narration timing are valid.'
        self._run_task(check, self._set_status)

    def output_path(self, preview=False):
        name = f'{self.story.name}_{self.episode.episode_id}' + ('.preview' if preview else '') + '.mp4'
        return self.library.root / 'exports' / name

    def start_render(self, preview=False):
        if not self.episode or not self.save_all(quiet=True):
            return
        source = self.episode.directory / 'scenes.json'
        output = self.output_path(preview)
        self.player.stop()
        self.player.setSource(QUrl())
        self.narration_player.stop()
        overrides = {'width': 360, 'height': 640, 'preset': 'ultrafast', 'crf': 24} if preview else None
        self._run_task(lambda progress, cancel: render_episode(source, output, progress=progress, cancel=cancel, overrides=overrides), self._render_completed)

    def _render_completed(self, report):
        self.last_report = report
        self.log.appendPlainText(f'VERIFIED: {report["output"]}\n{report["width"]} × {report["height"]}, {report["fps"]} FPS, H.264/AAC, {report["video_duration_seconds"]:.2f}s. Full decode passed.')
        self.play_export(Path(report['output']))
        self.progress_bar.setValue(100)
        self._set_status('Verified MP4 saved. Preview is playing the actual exported file.')

    def start_batch(self):
        if not self.story or not self.save_all(quiet=True):
            return
        paths = self.library.episodes(self.story)
        output = self.library.root / 'exports'
        self.player.stop()
        self.player.setSource(QUrl())
        def complete(results):
            self.log.appendPlainText(json.dumps(results, indent=2, ensure_ascii=False))
            successes = sum(item['status'] == 'verified' for item in results)
            self._set_status(f'Batch finished: {successes}/{len(paths)} verified. See the log for failures or cancellation.')
        self._run_task(lambda progress, cancel: render_batch(paths, output, progress=progress, cancel=cancel), complete)

    def show_still(self):
        if not self.episode or self.scene_index < 0:
            return
        self.player.pause()
        self.preview_stack.setCurrentIndex(0)
        scene = self.episode.scenes[self.scene_index]
        from .video_assets import visual_preview
        try:
            pixmap = QPixmap(str(visual_preview(self.episode, scene)))
        except (MediaError, OSError, ValueError):
            pixmap = QPixmap()
        if pixmap.isNull():
            self.image_preview.setPixmap(QPixmap())
            self.image_preview.setText('Visual missing or unreadable\n\nUse Browse to add an image or video')
        else:
            self.image_preview.setPixmap(pixmap.scaled(self.image_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.preview_label.setText('Scene artwork · render a preview for motion, voice and captions')

    def play_export(self, path: Path):
        if not path.is_file():
            self._error(f'Export file is missing: {path}')
            return
        self.narration_player.pause()
        self.tabs.setCurrentIndex(0)
        self.preview_stack.setCurrentIndex(1)
        self.player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        self.player.play()
        self.preview_label.setText('Playing verified export: ' + path.name)

    def toggle_play(self):
        self.narration_player.pause()
        if self.player.source().isEmpty():
            self._set_status('Render a preview or select an existing export first.')
        elif self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.preview_stack.setCurrentIndex(1)
            self.player.play()

    def refresh_exports(self):
        self.export_table.setRowCount(0)
        for path in sorted((self.library.root / 'exports').glob('*.verification.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                report = json.loads(path.read_text(encoding='utf-8'))
                # Reports retain historical render paths. The paired MP4 moves
                # with its sidecar when a workspace is cloned or copied.
                output = path.with_name(path.name.removesuffix('.verification.json') + '.mp4')
                if not report.get('verified') or not output.is_file():
                    continue
                status = 'Verified · full decode passed'
                source = export_source(report, self.library.root)
                if source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() != report.get('source_sha256'):
                    status = 'Verified export · project changed since render'
                row = self.export_table.rowCount()
                self.export_table.insertRow(row)
                for column, value in enumerate((output.name, f'{report["width"]} × {report["height"]} / {report["fps"]}', f'{report["video_duration_seconds"]:.2f}s', status)):
                    item = QTableWidgetItem(value)
                    if column == 0:
                        item.setData(Qt.ItemDataRole.UserRole, str(output))
                    self.export_table.setItem(row, column, item)
            except (OSError, ValueError, KeyError):
                continue

    def play_selected_export(self):
        row = self.export_table.currentRow()
        if row >= 0:
            self.play_export(Path(self.export_table.item(row, 0).data(Qt.ItemDataRole.UserRole)))

    def closeEvent(self, event):
        if self._thread is not None:
            self._closing = True
            self.cancel_job()
            event.ignore()
            return
        if not self.save_all(quiet=True):
            event.ignore()
            return
        self.player.stop()
        self.player.setSource(QUrl())
        self.narration_player.stop()
        self.narration_player.setSource(QUrl())
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'preview_stack') and self.preview_stack.currentIndex() == 0:
            self.show_still()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    app.setApplicationName('Video Novel Studio')
    app.setOrganizationName('Local Studio')
    window = StudioWindow(args.workspace)
    window.show()
    raise SystemExit(app.exec())


if __name__ == '__main__':
    main()
