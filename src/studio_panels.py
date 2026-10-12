"""Production editing panels mixed into the native StudioWindow."""
from dataclasses import replace
import json

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QDoubleSpinBox, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QTabWidget, QFormLayout, QLineEdit, QComboBox,
    QListWidgetItem, QColorDialog, QGridLayout)

from .media import audio_duration, atomic_json
from .render_cache import digest
from .scene_builder import save_episode
from .series_tools import load_style, save_style, apply_style, load_continuity, save_continuity
from .settings import settings_for, card_durations
from .subtitle_generator import Cue
from .timeline import prepare_waveform, edit_timeline
from .timeline_widget import TimelineWidget
from .publishing import publishing_check
from .exports import export_source, export_changed
from .ui_widgets import FormSection


def action(text, callback):
    button = QPushButton(text)
    button.clicked.connect(callback)
    return button


class ProductionPanels:
    def _caption_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        note = QLabel('Drag caption edges or centres, scene/transition right edges, or sound effects. Click the ruler/waveform to seek. Scene trims move later captions; use separate scene recordings. Video shows the last render.')
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        self.generate_captions_button = action('Generate captions', self.generate_captions)
        self.save_captions_button = action('Save timings', self.save_manual_captions)
        row.addWidget(self.generate_captions_button)
        row.addWidget(self.save_captions_button)
        row.addWidget(action('Import SRT…', self.import_subtitles))
        self.subtitle_mode = QComboBox()
        self.subtitle_mode.addItems(['auto', 'manual'])
        row.addWidget(self.subtitle_mode)
        self.wave_button = action('Load waveform', self.load_waveform)
        row.addWidget(self.wave_button)
        row.addStretch()
        layout.addLayout(row)
        toolbar = QHBoxLayout()
        self.listen_button = action('Listen / pause narration', self.listen_narration)
        toolbar.addWidget(self.listen_button)
        toolbar.addWidget(action('Play last video', self.timeline_play_video))
        self.timeline_time = QDoubleSpinBox()
        self.timeline_time.setRange(0, 100000)
        self.timeline_time.setDecimals(3)
        self.timeline_time.setSuffix(' s')
        self.timeline_time.valueChanged.connect(self.timeline_seek)
        toolbar.addWidget(self.timeline_time)
        toolbar.addWidget(action('Cue start here', lambda: self.cue_boundary('start')))
        toolbar.addWidget(action('Cue end here', lambda: self.cue_boundary('end')))
        toolbar.addWidget(QLabel('Zoom'))
        self.timeline_zoom = QSpinBox()
        self.timeline_zoom.setRange(8, 160)
        self.timeline_zoom.setValue(28)
        toolbar.addWidget(self.timeline_zoom)
        layout.addLayout(toolbar)
        area = QSplitter()
        self.timeline = TimelineWidget()
        self.timeline.edited.connect(self._timeline_edit)
        self.timeline.selected.connect(self._timeline_selected)
        self.timeline.seek.connect(self.timeline_seek)
        self.timeline_zoom.valueChanged.connect(self.timeline.set_zoom)
        self.timeline_scroll = QScrollArea()
        self.timeline_scroll.setWidget(self.timeline)
        self.timeline_scroll.setWidgetResizable(True)
        self.timeline_scroll.setMinimumHeight(262)
        area.addWidget(self.timeline_scroll)
        video_column = QWidget()
        video_layout = QVBoxLayout(video_column)
        video_layout.setContentsMargins(0, 0, 0, 0)
        self.timeline_video = self.video_widget.__class__()
        self.timeline_video.setMinimumSize(135, 180)
        self.timeline_video.setText('Render a preview\nthen play the last video')
        self.video_widget.videoSink().videoFrameChanged.connect(self.timeline_video._frame)
        video_layout.addWidget(self.timeline_video, 1)
        self.timeline_video_note = QLabel('Last rendered video · edits need a rerender')
        self.timeline_video_note.setWordWrap(True)
        video_layout.addWidget(self.timeline_video_note)
        self.live_caption = QLabel('Current cue appears here while you listen.')
        self.live_caption.setWordWrap(True)
        self.live_caption.setObjectName('liveCaption')
        video_layout.addWidget(self.live_caption)
        self._audition_scene = None
        area.addWidget(video_column)
        area.setSizes([760, 185])
        layout.addWidget(area, 2)
        self.wave_status = QLabel('Waveform not loaded. No automatic speech alignment; listen and adjust the cues.')
        self.wave_status.setWordWrap(True)
        layout.addWidget(self.wave_status)
        self.caption_table = QTableWidget(0, 3)
        self.caption_table.setHorizontalHeaderLabels(['Start (s)', 'End (s)', 'Caption text'])
        self.caption_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.caption_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.caption_table.setMinimumHeight(130)
        self.caption_table.itemChanged.connect(self._caption_edited)
        self.caption_table.currentCellChanged.connect(self._table_caption_selected)
        layout.addWidget(self.caption_table, 1)
        self.wave_data, self.wave_signature = None, None
        self.effect_lengths = {}
        self.narration_player = QMediaPlayer(self)
        self.narration_output = QAudioOutput(self)
        self.narration_player.setAudioOutput(self.narration_output)
        self.narration_output.setVolume(.7)
        self.narration_player.positionChanged.connect(self._timeline_position)
        self.player.positionChanged.connect(self._timeline_position)
        self.narration_player.errorOccurred.connect(lambda error, message: self._set_status('Narration playback: ' + message))
        return tab

    def _table_cues(self):
        return [Cue(float(self.caption_table.item(row, 0).text()), float(self.caption_table.item(row, 1).text()),
                    self.caption_table.item(row, 2).text(), self.caption_table.item(row, 0).data(Qt.ItemDataRole.UserRole) or 'cinematic')
                for row in range(self.caption_table.rowCount())]

    def _wave_signature(self):
        settings = settings_for(self.episode)
        records = []
        for scene in self.episode.scenes:
            path = self.episode.resolve_asset(scene.narration_audio or settings['narration_asset'])
            stamp = (path.stat().st_size, path.stat().st_mtime_ns) if path.is_file() else None
            records.append((scene.scene_id, scene.duration_seconds, str(path), stamp, bool(scene.narration.strip())))
        return (str(self.episode.directory), records, card_durations(settings), settings['narration_volume'])

    def _refresh_timeline(self):
        if not self.episode:
            self.timeline.set_data(None, [])
            return
        if self.wave_signature != self._wave_signature():
            self.wave_data = None
            self.narration_player.stop()
            self.narration_player.setSource(QUrl())
            self.wave_status.setText('Load waveform for the current scene/audio timing. Video remains the last render.')
        try:
            cues = self._table_cues()
        except (ValueError, AttributeError):
            return  # A partially typed table value is not a committed timing edit.
        effects = []
        for effect in settings_for(self.episode)['sound_effects']:
            try:
                path = self.episode.resolve_asset(effect['asset'])
                key = (str(path), path.stat().st_mtime_ns, path.stat().st_size)
                if key not in self.effect_lengths:
                    self.effect_lengths[key] = audio_duration(path)
                effects.append({**effect, 'duration': self.effect_lengths[key], 'label': path.name})
            except (OSError, ValueError, RuntimeError, KeyError):
                effects.append({**effect, 'duration': .2, 'label': 'Missing/invalid effect'})
        self.timeline.set_data(self.episode, cues, self.wave_data, effects)

    def load_waveform(self):
        if not self.episode or not self.save_all(quiet=True):
            return
        self.narration_player.stop()
        self.narration_player.setSource(QUrl())
        episode = self.episode
        signature = self._wave_signature()
        def completed(data):
            self.wave_data, self.wave_signature = data, signature
            self.narration_player.setSource(QUrl.fromLocalFile(data['path']))
            self._refresh_timeline()
            self.wave_status.setText('Current narration waveform · drag cues, then listen to check their timing. Music/SFX are heard in the rendered video.')
            self._set_status('Decoded narration waveform ready. Nothing was sent online.')
        self._run_task(lambda progress, cancel: prepare_waveform(episode, cancel=cancel,
                       progress=lambda value: progress(value, 'Decoding narration waveform')), completed)

    def listen_narration(self):
        if not self.episode:
            return
        if not self.save_all(quiet=True):
            return
        if not self.wave_data:
            self._set_status('Load waveform first; it also prepares current narration for listening.')
            return
        self.player.pause()
        if self.narration_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.narration_player.pause()
        else:
            self.narration_player.setPosition(round(self.timeline.playhead * 1000))
            self.narration_player.play()

    def timeline_seek(self, seconds):
        self._timeline_position(round(seconds * 1000))
        if not self.narration_player.source().isEmpty():
            self.narration_player.setPosition(round(seconds * 1000))
        if not self.player.source().isEmpty():
            self.player.setPosition(round(seconds * 1000))

    def _timeline_position(self, milliseconds):
        self.timeline.set_position(milliseconds / 1000)
        self.timeline_time.blockSignals(True)
        self.timeline_time.setValue(milliseconds / 1000)
        self.timeline_time.blockSignals(False)
        if self.episode:
            seconds = milliseconds / 1000
            cue = next((c for c in self.timeline.cues if c.start <= seconds < c.end), None)
            self.live_caption.setText(cue.text if cue else '—')
            if self.narration_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                title, _ = card_durations(settings_for(self.episode))
                shot = next((s.scene for s in self.episode.timeline() if title+s.start_seconds <= seconds < title+s.end_seconds), None)
                if shot and shot.scene_id != self._audition_scene:
                    from .video_assets import visual_preview
                    try:
                        pixmap = QPixmap(str(visual_preview(self.episode, shot)))
                    except (ValueError, OSError, RuntimeError):
                        pixmap = QPixmap()
                    self.timeline_video.setPixmap(pixmap.scaled(self.timeline_video.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    self._audition_scene = shot.scene_id
                    self.timeline_video_note.setText('Narration audition · scene artwork')

    def timeline_play_video(self):
        if not self.episode or not self.save_all(quiet=True):
            return
        self.narration_player.pause()
        source = (self.episode.directory / 'scenes.json').resolve()
        for path in sorted((self.library.root / 'exports').glob('*.verification.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                report = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(report, dict):
                    continue
                output = path.with_name(path.name.removesuffix('.verification.json') + '.mp4')
                if export_source(report, self.library.root).resolve() == source and report.get('verified') and output.is_file():
                    target = QUrl.fromLocalFile(str(output.resolve()))
                    if self.player.source() == target:
                        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                            self.player.pause()
                        else:
                            self.player.play()
                    else:
                        self.play_export(output)
                    self._audition_scene = None
                    self.tabs.setCurrentIndex(4)
                    changed = export_changed(report, self.library.root)
                    self.timeline_video_note.setText('Project changed · rerender to see edits' if changed else 'Playing the last verified export')
                    return
            except (OSError, ValueError, KeyError):
                continue
        self._set_status('Render a preview for this episode before playing video here.')

    def _timeline_selected(self, kind, index):
        if kind == 'caption':
            self.caption_table.selectRow(index)
        elif kind in ('scene', 'transition'):
            self.scene_list.setCurrentRow(index)

    def _table_caption_selected(self, row, column, old_row, old_column):
        if row >= 0:
            self.timeline.selection = ('caption', row)
            self.timeline.update()

    def cue_boundary(self, edge):
        row = self.caption_table.currentRow()
        if row < 0:
            self._set_status('Select a caption first.')
            return
        def edit():
            cue = self._table_cues()[row]
            self._timeline_edit('caption', row, self.timeline.playhead if edge == 'start' else cue.start,
                                self.timeline.playhead if edge == 'end' else cue.end)
        self._guard(edit)

    def _timeline_edit(self, kind, index, start, end):
        if not self.episode or not self.save_all(quiet=True):
            self._refresh_timeline()
            return
        def edit():
            updated, cues = edit_timeline(self.episode, self._table_cues(), kind, index, start, end)
            self.episode = updated
            self._populate_scene(self.scene_index)
            self.effects_table.setRowCount(0)
            for effect in settings_for(updated)['sound_effects']:
                self._add_effect_row(effect)
            self._populate_captions(cues)
            if kind in ('caption', 'scene'):
                self.captions_dirty = True
            if not self.save_all(quiet=True):
                return
            self._set_status('Timeline edit saved. Load waveform again after scene trims; rerender to update video.')
        self._guard(edit)
        self._refresh_timeline()

    def _series_tab(self):
        tabs = QTabWidget()
        style = QWidget()
        layout = QVBoxLayout(style)
        note = QLabel('Save this episode’s fonts, colours, voice, music and card settings as defaults for this series. New episodes inherit them. Apply explicitly to update an existing episode.')
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.title_template = QLineEdit('{series} · Episode {episode}')
        self.end_template = QLineEdit('To be continued')
        form.addRow('Title template', self.title_template)
        form.addRow('End template', self.end_template)
        form.addRow(QLabel('Supported fields: {series}, {episode}, {title}'))
        for key, label in (('caption_color', 'Caption colour'), ('card_background', 'Card background'),
                           ('card_accent', 'Card accent'), ('card_text', 'Card text')):
            row = QHBoxLayout()
            edit = QLineEdit()
            self.settings_widgets[key] = edit
            row.addWidget(edit)
            row.addWidget(action('Choose colour', lambda checked=False, widget=edit: self._choose_colour(widget)))
            form.addRow(label, row)
        layout.addLayout(form)
        self.series_style_note = QLabel()
        self.series_style_note.setWordWrap(True)
        layout.addWidget(self.series_style_note)
        row = QHBoxLayout()
        self.save_style_button = action('Save as series defaults', self.save_series_style)
        self.apply_style_button = action('Apply defaults to this episode', self.apply_series_style)
        row.addWidget(self.save_style_button)
        row.addWidget(self.apply_style_button)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()
        tabs.addTab(style, 'Series style')
        continuity = QWidget()
        layout = QVBoxLayout(continuity)
        help_text = QLabel('Enter stable IDs, then link characters and locations in the scene editor. Track plot threads as open/resolved. Previous endings and open threads appear in Writing. These records supplement your Markdown bibles.')
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        tables = QTabWidget()
        self.continuity_tables = {}
        self.continuity_columns = {'characters': ('id', 'name', 'notes'), 'locations': ('id', 'name', 'notes'),
            'threads': ('id', 'name', 'status', 'opened_episode', 'resolved_episode', 'notes')}
        for category, columns in self.continuity_columns.items():
            page = QWidget()
            inner = QVBoxLayout(page)
            table = QTableWidget(0, len(columns))
            table.setHorizontalHeaderLabels([c.replace('_', ' ').title() for c in columns])
            table.horizontalHeader().setSectionResizeMode(len(columns)-1, QHeaderView.ResizeMode.Stretch)
            self.continuity_tables[category] = table
            inner.addWidget(table)
            controls = QHBoxLayout()
            controls.addWidget(action('+ Add', lambda checked=False, c=category: self._add_continuity_row(c)))
            controls.addWidget(action('Remove selected', lambda checked=False, t=table: t.removeRow(t.currentRow()) if t.currentRow() >= 0 else None))
            controls.addStretch()
            inner.addLayout(controls)
            tables.addTab(page, category.title())
        layout.addWidget(tables)
        self.save_continuity_button = action('Save continuity and refresh scene links', self.save_series_continuity)
        layout.addWidget(self.save_continuity_button)
        tabs.addTab(continuity, 'Continuity tracker')
        return tabs

    def _choose_colour(self, widget):
        from PySide6.QtGui import QColor
        color = QColorDialog.getColor(QColor(widget.text()), self, 'Choose colour')
        if color.isValid():
            widget.setText(color.name())

    def _load_series_panels(self):
        data = load_continuity(self.story)
        for category, table in self.continuity_tables.items():
            table.setRowCount(0)
            for record in data[category]:
                self._add_continuity_row(category, record)
        profile = load_style(self.story)
        self.title_template.setText(profile.get('title_template', '') if profile else '{series} · Episode {episode}')
        self.end_template.setText(profile.get('end_template', '') if profile else 'To be continued')
        self.series_style_note.setText('Defaults saved for this series. Font, voice and music controls are in Audio / output.' if profile else 'No series defaults saved yet. Set this episode’s presentation, then save defaults here.')

    def _add_continuity_row(self, category, record=None):
        table = self.continuity_tables[category]
        row = table.rowCount()
        table.insertRow(row)
        values = record or {'status': 'open', 'opened_episode': self.episode.episode_id if self.episode else ''}
        for col, key in enumerate(self.continuity_columns[category]):
            table.setItem(row, col, QTableWidgetItem(values.get(key, '')))

    def _save_series_data(self):
        if not self.story:
            return
        data = {}
        for category, table in self.continuity_tables.items():
            data[category] = [{key: table.item(row, col).text().strip() for col, key in enumerate(self.continuity_columns[category])}
                              for row in range(table.rowCount())]
        save_continuity(self.story, data)

    def _populate_scene_references(self, scene):
        data = load_continuity(self.story)
        self.scene_characters.clear()
        names = {row['id']: row['name'] for row in data['characters']}
        for key in dict.fromkeys([*names, *scene.characters]):
            item = QListWidgetItem(f'{names.get(key, "Missing reference")} ({key})')
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if key in scene.characters else Qt.CheckState.Unchecked)
            self.scene_characters.addItem(item)
        self.scene_location.clear()
        self.scene_location.addItem('No location linked', '')
        for row in data['locations']:
            self.scene_location.addItem(row['name'], row['id'])
        if scene.location and self.scene_location.findData(scene.location) < 0:
            self.scene_location.addItem(f'Missing reference ({scene.location})', scene.location)
        self.scene_location.setCurrentIndex(max(0, self.scene_location.findData(scene.location or '')))

    def save_series_continuity(self):
        if self.episode and self.save_all(quiet=True):
            self._populate_scene_references(self.episode.scenes[self.scene_index])
            self.refresh_continuity()
            self._set_status('Continuity saved. Link characters and locations in Scenes / preview.')

    def save_series_style(self):
        if not self.episode or not self.save_all(quiet=True):
            return
        def save():
            save_style(self.episode, voice=self.voice_combo.currentText() if self.voices else '', rate=self.voice_rate.value(),
                       subtitle_style=self.style_combo.currentText(), title_template=self.title_template.text(), end_template=self.end_template.text())
            self.series_style_note.setText('Series defaults saved. New episodes inherit this presentation and voice choice.')
            self._set_status('Series style saved; existing episodes retain their settings until you apply it.')
        self._guard(save)

    def apply_series_style(self):
        if not self.episode or not self.save_all(quiet=True):
            return
        def apply():
            if not load_style(self.story):
                raise ValueError('Save series defaults first.')
            updated = apply_style(self.episode, self.library.story_title(self.story))
            # Preserve manual cue positions relative to narration if title time changes.
            old_title = card_durations(settings_for(self.episode))[0]
            new_title = card_durations(settings_for(updated))[0]
            if settings_for(updated)['subtitle_mode'] == 'manual' and abs(old_title-new_title) > .0001:
                from .subtitle_generator import validate_cues, cues_to_srt
                from .timeline import cue_windows, total_duration
                from .story_manager import atomic_text
                cues = [replace(cue, start=round(cue.start+new_title-old_title, 3), end=round(cue.end+new_title-old_title, 3)) for cue in self._table_cues()]
                validate_cues(cues, total_duration(updated), cue_windows(updated))
                atomic_text(updated.directory / 'subtitles.srt', cues_to_srt(cues))
            save_episode(updated)
            self.load_project(updated.directory / 'scenes.json')
            self._set_status('Series style applied. Manual captions follow the title offset. Existing voice recordings are unchanged.')
        self._guard(apply)

    def _publishing_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        note = QLabel('Check assets, timing, narration pauses and mobile captions before publishing. Warnings are editorial guidance; safe margins are not a guarantee about platform overlays.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.publish_settings = FormSection('Check settings')
        thresholds = QWidget()
        grid = QGridLayout(thresholds)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(24)
        for column, (key, label, value) in enumerate((('publish_min_duration', 'Minimum duration (s)', 60),
                                  ('publish_max_duration', 'Maximum duration (s)', 90),
                                  ('pause_warning_seconds', 'Warn about narration pauses longer than (s)', 1.5))):
            widget = QDoubleSpinBox()
            widget.setRange(.1, 10000)
            widget.setValue(value)
            self.settings_widgets[key] = widget
            heading = QLabel(label)
            heading.setWordWrap(True)
            heading.setBuddy(widget)
            grid.addWidget(heading, 0, column)
            grid.addWidget(widget, 1, column)
            grid.setColumnStretch(column, 1)
        self.publish_settings.form.addRow(thresholds)
        layout.addWidget(self.publish_settings)
        self.publish_check_button = action('Run publishing check', self.run_publishing_check)
        self.publish_check_button.setObjectName('primary')
        actions = QHBoxLayout()
        actions.addWidget(self.publish_check_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.publish_summary = QLabel('No publishing check run for this episode yet.')
        self.publish_summary.setWordWrap(True)
        layout.addWidget(self.publish_summary)
        self.publish_table = QTableWidget(0, 3)
        self.publish_table.setHorizontalHeaderLabels(['Level', 'Time', 'Finding / action'])
        self.publish_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.publish_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.publish_table.cellDoubleClicked.connect(self._jump_issue)
        layout.addWidget(self.publish_table, 1)
        return tab

    def run_publishing_check(self):
        if not self.episode or not self.save_all(quiet=True):
            return
        self.narration_player.stop()
        self.narration_player.setSource(QUrl())
        episode = self.episode
        def completed(report):
            self.publish_report = report
            self.publish_table.setRowCount(len(report['issues']))
            for row, issue in enumerate(report['issues']):
                for col, value in enumerate((issue['level'].upper(), '' if issue['seconds'] is None else f'{issue["seconds"]:.2f}s', issue['message'])):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.ItemDataRole.UserRole, issue['seconds'])
                    self.publish_table.setItem(row, col, item)
            self.publish_table.resizeRowsToContents()
            warnings = sum(i['level'] == 'warning' for i in report['issues'])
            errors = sum(i['level'] == 'error' for i in report['issues'])
            self.publish_summary.setText(f'{errors} errors · {warnings} warnings · {report["duration_seconds"]:.2f}s. ' + ('Ready to render; review warnings.' if report['ready'] else 'Fix errors before rendering.'))
            atomic_json(episode.directory / 'publishing_check.json', {**report, 'source_sha256': digest(episode.directory / 'scenes.json')})
            self._set_status('Publishing check saved. Double-click a timed finding to inspect it in the timeline.')
        self._run_task(lambda progress, cancel: publishing_check(episode, progress=progress, cancel=cancel), completed)

    def _jump_issue(self, row, column):
        seconds = self.publish_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if seconds is not None:
            self.tabs.setCurrentIndex(4)
            self.timeline_seek(seconds)
            self.timeline_scroll.ensureVisible(round(self.timeline.x_at(seconds)), 180, 70, 20)
