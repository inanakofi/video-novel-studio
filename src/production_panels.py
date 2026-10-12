"""A guided manuscript production page; advanced controls stay optional."""
import json
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
                              QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QCheckBox, QFileDialog,
                              QScrollArea, QListWidget, QListWidgetItem, QTabWidget)

from .production.adapters import capability
from .production.prompts import FORMATS, PROMPTS, VERSION
from .production.runner import ProductionRunner, ROLE_KINDS


def action(text, callback):
    button = QPushButton(text)
    button.clicked.connect(callback)
    return button


def note(text):
    label = QLabel(text)
    label.setWordWrap(True)
    return label


class AutomationPanels:
    def _automation_tab(self):
        self.production_runner = ProductionRunner(self.library.root, self.generation_service)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(note('Manuscript → series plan → scripts → speech and visuals → verified videos. '
                              'Each run creates a new story. Start with one short episode to check your models and style.'))
        tabs = QTabWidget()
        layout.addWidget(tabs)
        setup = QWidget()
        form = QFormLayout(setup)
        source_row = QWidget()
        source_layout = QHBoxLayout(source_row)
        source_layout.setContentsMargins(0, 0, 0, 0)
        self.production_source = QLineEdit()
        self.production_source.setPlaceholderText('Attach a TXT, Markdown or DOCX manuscript')
        source_layout.addWidget(self.production_source, 1)
        source_layout.addWidget(action('Browse…', self._choose_manuscript))
        form.addRow('1. Manuscript', source_row)
        self.production_title = QLineEdit()
        self.production_title.setPlaceholderText('Name your series')
        form.addRow('Series title', self.production_title)
        self.production_format = QComboBox()
        for key, title in FORMATS.items():
            self.production_format.addItem(title, key)
        form.addRow('2. Video type', self.production_format)
        self.production_approach = QComboBox()
        self.production_approach.addItem('Adapt this manuscript faithfully', 'faithful')
        self.production_approach.addItem('Create an original story from broad structural inspiration', 'original')
        form.addRow('Approach', self.production_approach)
        self.production_count = QSpinBox()
        self.production_count.setRange(1, 24)
        self.production_seconds = QSpinBox()
        self.production_seconds.setRange(15, 1200)
        self.production_seconds.setValue(60)
        self.production_seconds.setSuffix(' seconds per episode (approximate)')
        form.addRow('Episodes', self.production_count)
        form.addRow('Target length', self.production_seconds)
        self.production_direction = QPlainTextEdit()
        self.production_direction.setPlaceholderText('Optional: language, audience, visual style, tone, pronunciation…')
        self.production_direction.setMaximumHeight(85)
        form.addRow('Creative direction', self.production_direction)
        form.addRow('3. AI connections', action('Refresh available connections', lambda: self._guard(self._refresh_production_routes)))
        self.production_routes = {}
        labels = {'analysis': 'Analysis / planning', 'writing': 'Scripts', 'review': 'Quality review',
                  'image': 'Illustrations / references', 'video': 'Animated / cinematic clips', 'voice': 'Speech',
                  'lipsync': 'Lip-sync tool (optional)'}
        for role, label in labels.items():
            picker = self.production_routes[role] = QComboBox()
            form.addRow(label, picker)
        form.addRow(note('Create and test profiles in Connections / AI first. Each profile has its own model. '
                         'Cartoon/cinematic production needs a video connection. Precise lip-sync requires a separate configured tool. '
                         'Generated footage and captions still need creative review.'))
        self.production_start = action('Create videos', lambda: self._guard(self._start_production))
        self.production_start.setObjectName('primary')
        form.addRow(self.production_start)
        form.addRow(note('Starting sends manuscript sections and production context to the selected text models, and prompts to media models. '
                         'Connected tools may incur charges. Stop pauses the run; submitted provider jobs may continue. '
                         'The call limit in Advanced bounds submissions, not their price.'))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(setup)
        tabs.addTab(scroll, 'Create videos')

        advanced = QWidget()
        extra = QFormLayout(advanced)
        self.production_resolution = QComboBox()
        self.production_resolution.addItem('360 × 640 — faster first draft', 'preview')
        self.production_resolution.addItem('1080 × 1920 — full export', 'full')
        extra.addRow('Output size (vertical)', self.production_resolution)
        self.production_limit = QSpinBox()
        self.production_limit.setRange(5, 5000)
        self.production_limit.setValue(200)
        extra.addRow('Maximum generation stages', self.production_limit)
        self.production_plan_pause = QCheckBox('Pause after the series plan for review')
        extra.addRow(self.production_plan_pause)
        self.production_references = QCheckBox('Generate reusable character and location reference images')
        extra.addRow(self.production_references)
        extra.addRow(note('Reference images are passed only to custom HTTP/MCP templates that consume reference_images or reference_paths. '
                          'Built-in media adapters use the canonical text descriptions. Reference generation is optional and adds calls.'))
        self.production_local_voice = QLineEdit()
        self.production_local_voice.setPlaceholderText('Blank uses the installed Windows default voice')
        extra.addRow('Installed voice name', self.production_local_voice)
        self.production_speakers = QPlainTextEdit('{}')
        self.production_speakers.setMaximumHeight(110)
        extra.addRow('Voice overrides (JSON)', self.production_speakers)
        extra.addRow(note('Optional mapping: {"CHAR-001":"connection-id", "NARRATOR":"connection-id"}. '
                          'Use separate voice profiles for distinct characters. Connection IDs appear below when refreshed. '
                          'The default Speech connection serves unmapped speakers.'))
        self.production_profile_ids = QPlainTextEdit()
        self.production_profile_ids.setReadOnly(True)
        self.production_profile_ids.setMaximumHeight(120)
        extra.addRow('Available profile IDs', self.production_profile_ids)
        extra.addRow(action('Apply voice overrides to selected paused plan', lambda: self._guard(self._update_production_speakers)))
        tabs.addTab(advanced, 'Advanced')

        history = QWidget()
        history_layout = QVBoxLayout(history)
        history_layout.addWidget(action('Refresh production history', lambda: self._guard(self._refresh_production_runs)))
        self.production_history = QListWidget()
        self.production_history.currentItemChanged.connect(self._production_selected)
        history_layout.addWidget(self.production_history, 1)
        self.production_details = QPlainTextEdit()
        self.production_details.setReadOnly(True)
        history_layout.addWidget(self.production_details, 1)
        row = QHBoxLayout()
        row.addWidget(action('Resume / accept plan', lambda: self._guard(self._resume_production)))
        row.addWidget(action('Open run folder', lambda: self._guard(self._open_production_folder)))
        row.addWidget(action('Open generated story', lambda: self._guard(self._open_production_story)))
        history_layout.addLayout(row)
        self.production_retry_ack = QCheckBox('I checked provider history; retrying this stage may create a new charge.')
        history_layout.addWidget(self.production_retry_ack)
        history_layout.addWidget(action('Retry current failed stage', lambda: self._guard(self._retry_production)))
        tabs.addTab(history, 'Runs / resume')

        prompts = QWidget()
        prompt_layout = QVBoxLayout(prompts)
        prompt_layout.addWidget(note(f'Built-in prompt library v{VERSION}, adapted from the supplied 35-prompt conversation. '
                                     'The workflow combines these directions with structured output contracts. Every actual request is saved as prompt.txt in its run folder.'))
        self.production_prompt_picker = QComboBox()
        for key, (title, _) in PROMPTS.items():
            self.production_prompt_picker.addItem(f'{key} · {title}', key)
        prompt_layout.addWidget(self.production_prompt_picker)
        self.production_prompt_text = QPlainTextEdit()
        self.production_prompt_text.setReadOnly(True)
        prompt_layout.addWidget(self.production_prompt_text, 1)
        self.production_prompt_picker.currentIndexChanged.connect(
            lambda: self.production_prompt_text.setPlainText(PROMPTS[self.production_prompt_picker.currentData()][1]))
        self.production_prompt_text.setPlainText(PROMPTS['01'][1])
        tabs.addTab(prompts, 'Built-in prompts')
        self.production_pages = tabs
        try:
            self._refresh_production_routes()
            self._refresh_production_runs()
        except (ValueError, OSError, KeyError, TypeError) as error:
            self.production_details.setPlainText(f'Could not load production settings: {error}')
        return page

    def _choose_manuscript(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Attach manuscript', str(self.library.root), 'Manuscripts (*.txt *.md *.docx)')
        if path:
            self.production_source.setText(path)
            if not self.production_title.text().strip():
                self.production_title.setText(Path(path).stem.replace('_', ' ').title())

    def _refresh_production_routes(self):
        _, profiles = self.connection_store.load()
        for role, picker in self.production_routes.items():
            previous = picker.currentData()
            picker.clear()
            picker.addItem('Not selected' if role not in ('writing', 'review') else 'Use Analysis / planning connection', '')
            if role == 'voice':
                picker.addItem('Installed Windows speech (offline)', 'local_speech')
            for connection in profiles:
                if connection.enabled and capability(connection, ROLE_KINDS[role]):
                    picker.addItem(connection.name + (f' · {connection.model}' if connection.model else ''), connection.id)
            index = picker.findData(previous)
            if index >= 0:
                picker.setCurrentIndex(index)
            elif role == 'voice':
                picker.setCurrentIndex(1)
        self.production_profile_ids.setPlainText('\n'.join(f'{p.name}: {p.id}' for p in profiles if p.enabled))

    def _production_config(self):
        routes = {role: picker.currentData() for role, picker in self.production_routes.items()}
        for role in ('writing', 'review'):
            routes[role] = routes[role] or routes['analysis']
        return {'title': self.production_title.text().strip(), 'format': self.production_format.currentData(),
                'adaptation': self.production_approach.currentData(), 'episodes': self.production_count.value(),
                'seconds': self.production_seconds.value(), 'direction': self.production_direction.toPlainText().strip(),
                'routes': routes, 'max_calls': self.production_limit.value(), 'resolution': self.production_resolution.currentData(),
                'references': self.production_references.isChecked(), 'pause_after_plan': self.production_plan_pause.isChecked(),
                'local_voice': self.production_local_voice.text().strip(),
                'speaker_routes': json.loads(self.production_speakers.toPlainText())}

    def _start_production(self):
        if self.episode and not self.save_all(quiet=True):
            return
        state = self.production_runner.create(self.production_source.text().strip(), self._production_config())
        self._refresh_production_runs(state['id'])
        self.production_pages.setCurrentIndex(2)
        self._run_task(lambda progress, cancel: self.production_runner.run(state['id'], cancel=cancel, progress=progress),
                       self._production_completed)

    def _selected_production(self):
        item = self.production_history.currentItem()
        if not item:
            raise ValueError('Select a saved production run.')
        return self.production_runner.load(item.data(Qt.ItemDataRole.UserRole))

    def _refresh_production_runs(self, selected=None):
        old = self.production_history.currentItem()
        selected = selected or (old.data(Qt.ItemDataRole.UserRole) if old else None)
        self.production_history.clear()
        for state in self.production_runner.list_runs():
            item = QListWidgetItem(f'{state["config"]["title"]} · {FORMATS[state["config"]["format"]]} · {state["status"].replace("_", " ")}')
            item.setData(Qt.ItemDataRole.UserRole, state['id'])
            self.production_history.addItem(item)
            if state['id'] == selected:
                self.production_history.setCurrentItem(item)
        if self.production_history.currentRow() < 0 and self.production_history.count():
            self.production_history.setCurrentRow(0)

    def _production_selected(self, current=None, previous=None):
        if not current:
            self.production_details.clear()
            return
        def show():
            state = self._selected_production()
            completed = sum(s['status'] == 'ready' for s in state['stages'].values())
            self.production_details.setPlainText(
                f'Run: {state["id"]}\nStatus: {state["status"]}\nCurrent stage: {state["current_stage"]}\n'
                f'Completed generation stages: {completed}\nSubmission stages used: {state["calls"]} / {state["config"]["max_calls"]}\n'
                f'Story: {state["story"]}\n\n{state.get("error", "")}\n\n' +
                '\n'.join(f'{e["episode"]}: {e["path"]}' for e in state['exports']))
        self._guard(show)

    def _resume_production(self):
        if self.episode and not self.save_all(quiet=True):
            return
        state = self._selected_production()
        self._run_task(lambda progress, cancel: self.production_runner.run(state['id'], cancel=cancel, progress=progress,
                                                                          accept_plan=state['status'] == 'awaiting_plan'),
                       self._production_completed)

    def _production_completed(self, state):
        self._refresh_production_runs(state['id'])
        if state['status'] == 'complete':
            self.refresh_library(select_story=self.library.root / state['story'])
            self._set_status(f'{len(state["exports"])} video(s) generated and verified. Review them in Exports before publishing.')
        else:
            self._set_status('Series plan saved. Open the run folder to review season_plan.json, then Resume / accept plan.')

    def _open_production_folder(self):
        state = self._selected_production()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.production_runner.runs / state['id'])))

    def _open_production_story(self):
        state = self._selected_production()
        story = self.library.root / state['story']
        if not (story / 'story.json').is_file():
            raise ValueError('This run has not created its series plan yet.')
        self.refresh_library(select_story=story)

    def _retry_production(self):
        if not self.production_retry_ack.isChecked():
            raise ValueError('Check the provider history and acknowledge possible duplicate charges before retrying an unknown submission.')
        state = self._selected_production()
        self.production_runner.retry_stage(state['id'])
        self.production_retry_ack.setChecked(False)
        self._resume_production()

    def _update_production_speakers(self):
        state = self._selected_production()
        self.production_runner.update_speakers(state['id'], json.loads(self.production_speakers.toPlainText()))
        self._refresh_production_runs(state['id'])
        self._set_status('Voice overrides saved for the selected plan. Resume to begin episode production.')
