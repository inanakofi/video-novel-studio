"""A guided manuscript production page; advanced controls stay optional."""
import json
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
                              QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QCheckBox, QFileDialog,
                              QScrollArea, QListWidget, QListWidgetItem, QTabWidget, QGridLayout)

from .production.adapters import capability
from .production.prompts import FORMATS, PROMPTS, VERSION
from .production.runner import ProductionRunner, ROLE_KINDS
from .connections.models import filter_models
from .model_widgets import model_picker, fill_models
from .media import atomic_json
from .ui_widgets import FormSection


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
        setup_layout = QVBoxLayout(setup)
        setup_layout.setSpacing(16)
        self.production_sections = {}
        for title in ('Manuscript', 'Video format', 'Task models'):
            section = self.production_sections[title] = FormSection(title)
            setup_layout.addWidget(section)
        setup_layout.addStretch()
        form = self.production_sections['Manuscript'].form
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
        form = self.production_sections['Video format'].form
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
        form = self.production_sections['Task models'].form
        connections = QHBoxLayout()
        connections.addWidget(action('Refresh available connections', lambda: self._guard(self._refresh_production_routes)))
        connections.addWidget(action('Refresh model catalogs', lambda: self._guard(self._refresh_model_catalogs)))
        form.addRow('3. AI connections', connections)
        filters = QHBoxLayout()
        self.production_free = QCheckBox('Free only')
        self.production_open = QCheckBox('Open weights / local')
        filters.addWidget(self.production_free)
        filters.addWidget(self.production_open)
        filters.addWidget(action('Show all models', self._show_all_production_models))
        filters.addStretch()
        self.production_free.toggled.connect(self._filter_production_models)
        self.production_open.toggled.connect(self._filter_production_models)
        form.addRow('Browse models', filters)
        self.production_routes = {}
        self.production_models = {}
        self.production_model_counts = {}
        model_choices = QWidget()
        model_grid = QGridLayout(model_choices)
        model_grid.setContentsMargins(0, 8, 0, 0)
        model_grid.setHorizontalSpacing(12)
        model_grid.setVerticalSpacing(8)
        model_grid.setColumnStretch(1, 2)
        model_grid.setColumnStretch(2, 3)
        for column, title in enumerate(('Task', 'Connection', 'Model', 'Available')):
            heading = QLabel(title)
            heading.setObjectName('tableHeading')
            model_grid.addWidget(heading, 0, column)
        labels = {'analysis': 'Analysis / planning', 'writing': 'Scripts', 'review': 'Quality review',
                  'image': 'Illustrations / references', 'video': 'Animated / cinematic clips', 'voice': 'Speech',
                  'lipsync': 'Lip-sync tool (optional)'}
        for row_index, (role, label) in enumerate(labels.items(), 1):
            picker = self.production_routes[role] = QComboBox()
            model = self.production_models[role] = model_picker()
            picker.setAccessibleName(label + ' connection')
            model.setAccessibleName(label + ' model')
            task_label = QLabel(label)
            task_label.setBuddy(picker)
            model_grid.addWidget(task_label, row_index, 0)
            model_grid.addWidget(picker, row_index, 1)
            model_grid.addWidget(model, row_index, 2)
            self.production_model_counts[role] = note('')
            self.production_model_counts[role].setObjectName('muted')
            model_grid.addWidget(self.production_model_counts[role], row_index, 3)
            picker.currentIndexChanged.connect(lambda _, r=role: self._production_model_changed(r, reset=True))
        form.addRow(model_choices)
        self.production_voice_id = QLineEdit()
        self.production_voice_id.setPlaceholderText('Optional; blank uses the Speech connection voice')
        form.addRow('Speech voice ID', self.production_voice_id)
        shortcuts = QHBoxLayout()
        shortcuts.addWidget(action('Use Analysis model for all text tasks', lambda: self._guard(self._use_analysis_model)))
        shortcuts.addWidget(action('Use Analysis platform for supported tasks', lambda: self._guard(self._use_analysis_platform)))
        form.addRow(shortcuts)
        form.addRow(action('Save task choices', lambda: self._guard(self._save_production_choices)))
        self.production_model_notice = note('')
        form.addRow(self.production_model_notice)
        form.addRow(note('Choose a connection and a model for each task. Reuse a connection to share its API key; '
                         'choose separate connections for different keys on the same platform. Blank model uses its default. '
                         'Scripts and Quality review inherit Analysis when their connection is blank. '
                         'Animated/cinematic clips need a video model; lip-sync uses a configured tool.'))
        self.production_start = action('Create videos', lambda: self._guard(self._start_production))
        self.production_start.setObjectName('primary')
        consent = note('Starting sends manuscript sections and production context to the selected text models, and prompts to media models. '
                         'Connected tools may incur charges. Stop pauses the run; submitted provider jobs may continue. '
                         'The call limit in Advanced bounds submissions, not their price.')
        consent.setObjectName('muted')
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(setup)
        create_page = QWidget()
        create_layout = QVBoxLayout(create_page)
        create_layout.setContentsMargins(0, 0, 0, 0)
        create_layout.addWidget(scroll, 1)
        create_footer = QHBoxLayout()
        create_footer.addWidget(consent, 1)
        create_footer.addWidget(self.production_start)
        create_layout.addLayout(create_footer)
        tabs.addTab(create_page, 'Create videos')

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
            self._restore_production_choices()
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
        self.production_profiles = profiles
        for role, picker in self.production_routes.items():
            previous = picker.currentData()
            model = self.production_models[role].currentText()
            picker.blockSignals(True)
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
            picker.blockSignals(False)
            self._production_model_changed(role, selected=model)
        self.production_profile_ids.setPlainText('\n'.join(f'{p.name}: {p.id}' for p in profiles if p.enabled))
        self._filter_production_models()

    def _production_model_changed(self, role, *, reset=False, selected=None):
        key = self.production_routes[role].currentData()
        if not key and role in ('writing', 'review'):
            key = self.production_routes['analysis'].currentData()
        conn = next((c for c in getattr(self, 'production_profiles', []) if c.id == key), None)
        picker = self.production_models[role]
        value = selected if selected is not None else ('' if reset else picker.currentText())
        count = fill_models(picker, conn, self.generation_service.catalog, ROLE_KINDS[role],
                            free=self.production_free.isChecked(), open_weights=self.production_open.isChecked(), selected=value)
        total = len(filter_models(self.generation_service.catalog.records(conn), ROLE_KINDS[role])) if conn else 0
        self.production_model_counts[role].setText(f'{count} / {total} models' if conn else
                                                  ('Installed voice' if key == 'local_speech' else 'Choose connection'))
        if role == 'analysis':
            for other in ('writing', 'review'):
                if not self.production_routes[other].currentData():
                    self._production_model_changed(other)

    def _filter_production_models(self, *_):
        for role in self.production_routes:
            self._production_model_changed(role)
        self.production_model_notice.setText('Search or enter a model ID. Lists match each task’s output. '
            'Counts show displayed / total models. Show all models clears price and license filters. '
            'Refresh model catalogs retrieves the latest lists; failed refreshes keep cached models.')

    def _show_all_production_models(self):
        self.production_free.setChecked(False)
        self.production_open.setChecked(False)
        self._filter_production_models()

    def _use_analysis_model(self):
        key = self.production_routes['analysis'].currentData()
        if not key:
            raise ValueError('Choose an Analysis connection first.')
        model = self.production_models['analysis'].currentText()
        for role in ('writing', 'review'):
            self.production_routes[role].setCurrentIndex(self.production_routes[role].findData(key))
            self.production_models[role].setEditText(model)

    def _use_analysis_platform(self):
        key = self.production_routes['analysis'].currentData()
        conn = next((c for c in self.production_profiles if c.id == key), None)
        if not conn:
            raise ValueError('Choose an Analysis connection first.')
        self._use_analysis_model()
        for role in ('image', 'voice', 'video'):
            picker = self.production_routes[role]
            index = picker.findData(key)
            if index < 0:
                continue
            picker.setCurrentIndex(index)
            records = filter_models(self.generation_service.catalog.records(conn), ROLE_KINDS[role],
                                    free=self.production_free.isChecked(), open_weights=self.production_open.isChecked())
            if records:
                model = next((r['id'] for r in records if r['id'] == conn.model), None)
                self.production_models[role].setEditText(model or sorted(records, key=lambda r: (not r['free'], r['id']))[0]['id'])

    def _save_production_choices(self):
        atomic_json(self.library.root / '.studio_task_models.json', {
            'routes': {r: p.currentData() for r, p in self.production_routes.items()},
            'models': {r: p.currentText().strip() for r, p in self.production_models.items()},
            'voice': self.production_voice_id.text().strip(), 'free': self.production_free.isChecked(),
            'open_weights': self.production_open.isChecked()})
        self._set_status('Task connections and model choices saved.')

    def _restore_production_choices(self):
        path = self.library.root / '.studio_task_models.json'
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or any(not isinstance(data.get(k, {}), dict) for k in ('routes', 'models')):
            raise ValueError('Saved task choices need routes and models objects.')
        if any(not isinstance(v, str) for v in data.get('models', {}).values()) or not isinstance(data.get('voice', ''), str):
            raise ValueError('Saved model and voice IDs must be text.')
        for role, picker in self.production_routes.items():
            index = picker.findData(data.get('routes', {}).get(role))
            if index >= 0:
                picker.setCurrentIndex(index)
            self.production_models[role].setEditText(data.get('models', {}).get(role, ''))
        self.production_voice_id.setText(data.get('voice', ''))
        self.production_free.setChecked(bool(data.get('free')))
        self.production_open.setChecked(bool(data.get('open_weights')))

    def _production_config(self):
        routes = {role: picker.currentData() for role, picker in self.production_routes.items()}
        models = {role: picker.currentText().strip() for role, picker in self.production_models.items()}
        for role in ('writing', 'review'):
            if not routes[role] and not models[role]:
                models[role] = models['analysis']
            routes[role] = routes[role] or routes['analysis']
        return {'title': self.production_title.text().strip(), 'format': self.production_format.currentData(),
                'adaptation': self.production_approach.currentData(), 'episodes': self.production_count.value(),
                'seconds': self.production_seconds.value(), 'direction': self.production_direction.toPlainText().strip(),
                'routes': routes, 'models': models, 'voices': {'voice': self.production_voice_id.text().strip()},
                'max_calls': self.production_limit.value(), 'resolution': self.production_resolution.currentData(),
                'references': self.production_references.isChecked(), 'pause_after_plan': self.production_plan_pause.isChecked(),
                'local_voice': self.production_local_voice.text().strip(),
                'speaker_routes': json.loads(self.production_speakers.toPlainText())}

    def _start_production(self):
        if self.episode and not self.save_all(quiet=True):
            return
        state = self.production_runner.create(self.production_source.text().strip(), self._production_config())
        self._save_production_choices()
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
