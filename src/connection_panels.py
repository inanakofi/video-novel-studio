"""Desktop controls for optional connections and explicit result review."""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import uuid

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QPushButton, QComboBox, QLineEdit, QPlainTextEdit, QCheckBox, QTabWidget, QSplitter,
    QListWidget, QListWidgetItem, QFileDialog, QScrollArea)

from .connections.config import Connection, ConnectionStore, SecretStore, PRESETS
from .connections.generation import GenerationService, prompt_for, episode_from_draft, parse_script, script_markdown, validate_artifact
from .connections.tools import call_http, mcp_action
from .media import atomic_json
from .scene_builder import save_episode
from .story_manager import atomic_text


def action(text, callback):
    widget = QPushButton(text)
    widget.clicked.connect(callback)
    return widget


def note(text):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName('muted')
    return label


class ConnectionPanels:
    def _connections_tab(self):
        self.connection_store = ConnectionStore(self.library.root)
        self.secret_store = SecretStore()
        self.generation_service = GenerationService(self.library.root, self.secret_store)
        self.connection_profiles = []
        self.selected_connection_id = None
        self.review_job = None
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(note('Optional connections. Offline editing, installed speech and rendering work with these disabled. '
                              'Test, Generate, Resume, Call and manuscript production contact the selected services.'))
        modes = QHBoxLayout()
        self.connection_mode = QComboBox()
        for title, value in [('Disabled — offline studio', 'disabled'), ('Local services only — loopback HTTP', 'local'), ('Online and local services', 'online')]:
            self.connection_mode.addItem(title, value)
        modes.addWidget(self.connection_mode, 1)
        self.save_mode_button = action('Save connection mode', lambda: self._guard(self._save_connection_mode))
        modes.addWidget(self.save_mode_button)
        layout.addLayout(modes)
        self.connection_pages = QTabWidget()
        self.connection_pages.addTab(self._profile_panel(), 'Connections')
        self.connection_pages.addTab(self._generate_panel(), 'Generate')
        self.connection_pages.addTab(self._review_panel(), 'Jobs / review')
        self.connection_pages.addTab(self._tools_panel(), 'Software tools')
        layout.addWidget(self.connection_pages, 1)
        try:
            mode, self.connection_profiles = self.connection_store.load()
            self.connection_mode.setCurrentIndex(self.connection_mode.findData(mode))
            self._refresh_connections()
            self._refresh_generation_jobs()
        except (ValueError, OSError, TypeError) as error:
            self.connection_notice.setText(f'Could not load connections: {error}. Offline production is still available.')
        return page

    def _profile_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        row = QHBoxLayout()
        self.connection_picker = QComboBox()
        self.connection_picker.currentIndexChanged.connect(self._connection_selected)
        row.addWidget(self.connection_picker, 1)
        self.provider_picker = QComboBox()
        for key, (title, _, _, _) in PRESETS.items():
            self.provider_picker.addItem(title, key)
        row.addWidget(self.provider_picker, 1)
        self.add_connection_button = action('Add connection', lambda: self._guard(self._add_connection))
        row.addWidget(self.add_connection_button)
        layout.addLayout(row)
        inner = QWidget()
        form = QFormLayout(inner)
        self.connection_enabled = QCheckBox('Enable this connection')
        self.connection_name = QLineEdit()
        self.connection_url = QLineEdit()
        self.connection_model = QComboBox()
        self.connection_model.setEditable(True)
        self.connection_model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.connection_model.lineEdit().setPlaceholderText('Enter model ID or use Test / discover')
        self.connection_env = QLineEdit()
        self.connection_env.setPlaceholderText('Optional environment variable name; leave empty for stored key')
        self.connection_key = QLineEdit()
        self.connection_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.connection_key.setPlaceholderText('Enter a new key to save securely; blank keeps the existing key')
        self.connection_voice = QLineEdit()
        self.connection_voice.setPlaceholderText('ElevenLabs voice ID; Test / discover lists voices')
        self.connection_options = QPlainTextEdit('{}')
        self.connection_options.setMinimumHeight(145)
        self.connection_options.setPlaceholderText('Advanced provider options as JSON; never put credentials here')
        self.connection_notice = note('Add a provider preset to get started. No model is installed or downloaded automatically.')
        form.addRow(self.connection_enabled)
        form.addRow('Name', self.connection_name)
        form.addRow('Base URL / MCP endpoint', self.connection_url)
        form.addRow('Model ID', self.connection_model)
        form.addRow('Voice ID (ElevenLabs)', self.connection_voice)
        form.addRow('Credential environment', self.connection_env)
        form.addRow('Secure API key', self.connection_key)
        form.addRow('Provider options', self.connection_options)
        form.addRow(note('ComfyUI: load an exported API-format workflow, then replace its prompt input with {{prompt}}. '
                         'MCP stdio: command, args and optional cwd. Only launch programs you trust; they have your OS permissions.'))
        options_row = QHBoxLayout()
        options_row.addWidget(action('Load ComfyUI workflow…', lambda: self._guard(self._load_comfy_workflow)))
        options_row.addWidget(action('Remove stored key', lambda: self._guard(self._remove_connection_key)))
        form.addRow(options_row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)
        buttons = QHBoxLayout()
        self.save_connection_button = action('Save connection', lambda: self._guard(self._save_connection))
        self.test_connection_button = action('Save & test / discover', lambda: self._guard(self._test_connection))
        buttons.addWidget(self.save_connection_button)
        buttons.addWidget(self.test_connection_button)
        buttons.addWidget(action('Remove connection', lambda: self._guard(self._remove_connection)))
        layout.addLayout(buttons)
        layout.addWidget(self.connection_notice)
        return panel

    def _generate_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        row = QHBoxLayout()
        self.generation_connection = QComboBox()
        self.generation_connection.currentIndexChanged.connect(self._generation_connection_changed)
        self.generation_kind = QComboBox()
        row.addWidget(self.generation_connection, 2)
        row.addWidget(self.generation_kind, 1)
        layout.addLayout(row)
        layout.addWidget(note('1. Describe the result. Select context to include, then build and review the exact prompt.'))
        self.generation_instruction = QPlainTextEdit()
        self.generation_instruction.setPlaceholderText('For example: draft a three-scene episode ending with the arrival of a mysterious letter.')
        self.generation_instruction.setMaximumHeight(80)
        layout.addWidget(self.generation_instruction)
        contexts = QHBoxLayout()
        self.context_script = QCheckBox('Current script')
        self.context_bibles = QCheckBox('Story bibles')
        self.context_continuity = QCheckBox('Continuity')
        for widget in (self.context_script, self.context_bibles, self.context_continuity):
            contexts.addWidget(widget)
        self.prepare_prompt_button = action('Build prompt for review', lambda: self._guard(self._prepare_generation_prompt))
        contexts.addWidget(self.prepare_prompt_button)
        layout.addLayout(contexts)
        self.generation_prompt = QPlainTextEdit()
        self.generation_prompt.setMinimumHeight(160)
        self.generation_prompt.setPlaceholderText('The exact prompt sent to the selected service appears here. You can edit it before generating.')
        layout.addWidget(self.generation_prompt, 1)
        self.generation_destination = note('Results stay in Jobs / review until you explicitly apply them.')
        layout.addWidget(self.generation_destination)
        layout.addWidget(note('Online generation sends this prompt and provider options to the configured service and may incur charges. '
                              'Voice prompts should contain only the text to speak. No automatic retries or tool calls.'))
        self.generate_ai_button = action('Generate and save for review', lambda: self._guard(self._start_generation))
        self.generate_ai_button.setObjectName('primary')
        layout.addWidget(self.generate_ai_button)
        return panel

    def _review_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        split = QSplitter()
        self.generation_jobs = QListWidget()
        self.generation_jobs.setMaximumWidth(330)
        self.generation_jobs.currentItemChanged.connect(lambda *_: self._guard(self._select_generation_job))
        split.addWidget(self.generation_jobs)
        content = QWidget()
        column = QVBoxLayout(content)
        self.generation_result_info = note('Saved jobs are retained between sessions. Provider failures never count as completed results.')
        column.addWidget(self.generation_result_info)
        self.generation_result = QPlainTextEdit()
        self.generation_result.setPlaceholderText('Review and edit a generated draft, or inspect saved media information.')
        column.addWidget(self.generation_result, 1)
        self.generation_artifact = QComboBox()
        column.addWidget(self.generation_artifact)
        buttons = QHBoxLayout()
        buttons.addWidget(action('Open selected result', lambda: self._guard(self._open_generation_result)))
        buttons.addWidget(action('Save draft edits', lambda: self._guard(self._save_generation_edits)))
        column.addLayout(buttons)
        self.apply_generation_button = action('Apply reviewed result to current episode', lambda: self._guard(self._apply_generation_result))
        column.addWidget(self.apply_generation_button)
        column.addWidget(note('Applying a script replaces structured scenes and requires fresh narration; existing files are backed up. '
                              'A story draft replaces the series bible. Media replaces the selected scene asset after format validation.'))
        split.addWidget(content)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)
        controls = QHBoxLayout()
        controls.addWidget(action('Refresh jobs', lambda: self._guard(self._refresh_generation_jobs)))
        self.resume_generation_button = action('Resume saved provider task', lambda: self._guard(self._resume_generation))
        controls.addWidget(self.resume_generation_button)
        controls.addWidget(action('Import text draft for review…', lambda: self._guard(self._import_text_draft)))
        layout.addLayout(controls)
        return panel

    def _tools_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.software_connection = QComboBox()
        self.software_connection.currentIndexChanged.connect(lambda *_: self.mcp_tool_picker.clear())
        layout.addWidget(self.software_connection)
        layout.addWidget(note('Calls are explicit. External tools may change files or create paid jobs. Review the tool description and exact arguments before calling. '
                              'Local-only mode restricts HTTP destinations; it does not sandbox a launched MCP program.'))
        row = QHBoxLayout()
        row.addWidget(action('List MCP tools', lambda: self._guard(self._list_mcp_tools)))
        self.mcp_tool_picker = QComboBox()
        self.mcp_tool_picker.currentIndexChanged.connect(self._mcp_tool_selected)
        row.addWidget(self.mcp_tool_picker, 1)
        layout.addLayout(row)
        self.mcp_tool_description = QPlainTextEdit()
        self.mcp_tool_description.setReadOnly(True)
        self.mcp_tool_description.setMaximumHeight(120)
        layout.addWidget(self.mcp_tool_description)
        row = QHBoxLayout()
        self.http_method = QComboBox()
        self.http_method.addItems(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
        self.http_path = QLineEdit('/')
        row.addWidget(self.http_method)
        row.addWidget(self.http_path, 1)
        layout.addLayout(row)
        layout.addWidget(note('JSON arguments for MCP, or request body for HTTP. GET uses no body.'))
        self.software_arguments = QPlainTextEdit('{}')
        self.software_arguments.setMaximumHeight(130)
        layout.addWidget(self.software_arguments)
        self.call_software_button = action('Call selected tool / HTTP endpoint', lambda: self._guard(self._call_software))
        layout.addWidget(self.call_software_button)
        self.software_result = QPlainTextEdit()
        self.software_result.setReadOnly(True)
        layout.addWidget(self.software_result, 1)
        layout.addWidget(note('Expose this workspace to another MCP app with: python -m src.studio_mcp --workspace "PATH". '
                              'The server is read-only by default; --allow-drafts and --allow-render enable those tools. See CONNECTIONS.md.'))
        return panel

    def _refresh_connections(self, select=None):
        previous = select or self.connection_picker.currentData()
        self.connection_picker.blockSignals(True)
        self.connection_picker.clear()
        for conn in self.connection_profiles:
            self.connection_picker.addItem(f'{conn.name} ({conn.provider})', conn.id)
        self.connection_picker.setCurrentIndex(max(0, self.connection_picker.findData(previous)))
        self.connection_picker.blockSignals(False)
        self._connection_selected()
        for picker, software in ((self.generation_connection, False), (self.software_connection, True)):
            selected = picker.currentData()
            picker.blockSignals(True)
            picker.clear()
            for conn in self.connection_profiles:
                if bool(PRESETS[conn.provider][2]) != software:
                    picker.addItem(conn.name + ('' if conn.enabled else ' (disabled)'), conn.id)
            picker.setCurrentIndex(max(0, picker.findData(selected)))
            picker.blockSignals(False)
        self._generation_connection_changed()
        self.mcp_tool_picker.clear()

    def _connection_selected(self, *_):
        key = self.connection_picker.currentData()
        conn = next((c for c in self.connection_profiles if c.id == key), None)
        self.selected_connection_id = key
        self.connection_key.clear()
        if conn:
            self.connection_name.setText(conn.name)
            self.connection_url.setText(conn.base_url)
            self.connection_model.clear()
            self.connection_model.setEditText(conn.model)
            self.connection_env.setText(conn.key_env)
            self.connection_enabled.setChecked(conn.enabled)
            self.connection_voice.setText(conn.options.get('voice_id', ''))
            self.connection_options.setPlainText(json.dumps(conn.options, indent=2, ensure_ascii=False))
            self.connection_notice.setText(f'{PRESETS[conn.provider][0]} · '
                + ('Credential configured' if self.secret_store.exists(conn) else 'No credential configured')
                + ' · Endpoint discovery does not prove generation is available.')

    def _add_connection(self):
        conn = Connection.preset(self.provider_picker.currentData())
        self.connection_profiles.append(conn)
        self.connection_store.save(self.connection_mode.currentData(), self.connection_profiles)
        self._refresh_connections(conn.id)

    def _save_connection_mode(self):
        self.connection_store.save(self.connection_mode.currentData(), self.connection_profiles)
        self.connection_notice.setText('Connection mode saved. Production features remain available in every mode.')

    def _save_connection(self):
        conn = next((c for c in self.connection_profiles if c.id == self.selected_connection_id), None)
        if not conn:
            raise ValueError('Add a connection first')
        options = json.loads(self.connection_options.toPlainText())
        if not isinstance(options, dict):
            raise ValueError('Provider options must be a JSON object')
        if conn.provider == 'elevenlabs':
            options['voice_id'] = self.connection_voice.text().strip()
        updated = replace(conn, name=self.connection_name.text().strip(), base_url=self.connection_url.text().strip(),
                          model=self.connection_model.currentText().strip(), enabled=self.connection_enabled.isChecked(),
                          key_env=self.connection_env.text().strip(), options=options).validate()
        # Validate URL without connecting; a disabled profile may be prepared for later use.
        if updated.provider != 'mcp_stdio':
            from .connections.transport import validate_url
            validate_url(updated.base_url, 'online')
        if self.connection_key.text().strip():
            if updated.key_env:
                raise ValueError('Choose either a stored key or an environment variable, not both')
            self.secret_store.put(conn.id, self.connection_key.text().strip())
        self.connection_profiles = [updated if c.id == conn.id else c for c in self.connection_profiles]
        self.connection_store.save(self.connection_mode.currentData(), self.connection_profiles)
        self._refresh_connections(conn.id)
        return updated

    def _remove_connection_key(self):
        if self.selected_connection_id:
            self.secret_store.delete(self.selected_connection_id)
            self.connection_key.clear()
            self._connection_selected()

    def _remove_connection(self):
        key = self.selected_connection_id
        if key:
            self.secret_store.delete(key)
            self.connection_profiles = [c for c in self.connection_profiles if c.id != key]
            self.connection_store.save(self.connection_mode.currentData(), self.connection_profiles)
            self._refresh_connections()

    def _load_comfy_workflow(self):
        conn = next((c for c in self.connection_profiles if c.id == self.selected_connection_id), None)
        if not conn or conn.provider != 'comfyui':
            raise ValueError('Select a ComfyUI connection to load its workflow')
        path, _ = QFileDialog.getOpenFileName(self, 'Load ComfyUI API workflow', str(self.library.root), 'JSON (*.json)')
        if path:
            options = json.loads(self.connection_options.toPlainText())
            data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
            options['workflow'] = data.get('prompt', data)
            self.connection_options.setPlainText(json.dumps(options, indent=2, ensure_ascii=False))

    def _test_connection(self):
        conn = self._save_connection()
        if conn.provider in ('http', 'mcp_stdio', 'mcp_http'):
            self.connection_pages.setCurrentIndex(3)
            self.software_connection.setCurrentIndex(self.software_connection.findData(conn.id))
            self._set_status('Use List MCP tools or an explicit HTTP request to test this connection.')
            return
        def complete(result):
            self.connection_model.clear()
            self.connection_model.addItems(result['models'])
            self.connection_model.setEditText(conn.model)
            self.connection_notice.setText(result['status'] + '. Select a model and save the connection.')
            self.software_result.setPlainText(json.dumps(result['response'], indent=2, ensure_ascii=False))
            self._set_status(result['status'] + '; details are in Software tools.')
        self._run_task(lambda progress, cancel: self.generation_service.discover(conn.id, cancel), complete)

    def _generation_connection_changed(self, *_):
        conn = next((c for c in self.connection_profiles if c.id == self.generation_connection.currentData()), None)
        old = self.generation_kind.currentText()
        self.generation_kind.clear()
        if conn:
            self.generation_kind.addItems(PRESETS[conn.provider][2])
            if old in PRESETS[conn.provider][2]:
                self.generation_kind.setCurrentText(old)

    def _prepare_generation_prompt(self):
        if not self.generation_kind.currentText():
            raise ValueError('Add a generation connection first')
        if self.episode:
            self._save()
        context = []
        if self.context_script.isChecked() and self.episode:
            context.append(self.script_editor.toPlainText())
        if self.context_bibles.isChecked() and self.story:
            from .story_manager import BIBLES
            context.extend((self.story / name).read_text(encoding='utf-8') for name in BIBLES[:3] if (self.story / name).is_file())
        if self.context_continuity.isChecked() and self.episode:
            path = self.episode.directory / 'continuity_context.md'
            if path.is_file():
                context.append(path.read_text(encoding='utf-8'))
        self.generation_prompt.setPlainText(prompt_for(self.generation_kind.currentText(), self.generation_instruction.toPlainText(), '\n\n'.join(context)))
        self.generation_destination.setText('Review the prompt above. Results are saved separately; no script or asset is replaced during generation.')

    def _start_generation(self):
        key, kind = self.generation_connection.currentData(), self.generation_kind.currentText()
        prompt = self.generation_prompt.toPlainText()
        if not key or not prompt.strip():
            raise ValueError('Choose a connection and build or enter the exact prompt first')
        target = {'episode': str(self.episode.directory.relative_to(self.library.root)) if self.episode else '',
                  'scene_id': self.episode.scenes[self.scene_index].scene_id if self.episode and self.scene_index >= 0 else None}
        self._run_task(lambda progress, cancel: self.generation_service.run(key, kind, prompt, progress=progress, cancel=cancel, target=target),
                       self._generation_complete)

    def _generation_complete(self, job):
        self._refresh_generation_jobs(job['id'])
        self.connection_pages.setCurrentIndex(2)
        self._set_status('Result saved locally. Review it before applying.')

    def _refresh_generation_jobs(self, select=None):
        if select is None and self.generation_jobs.currentItem():
            select = self.generation_jobs.currentItem().data(Qt.ItemDataRole.UserRole)
        self.generation_jobs.blockSignals(True)
        self.generation_jobs.clear()
        selected = None
        for job in self.generation_service.list_jobs():
            item = QListWidgetItem(f'{job["kind"].title()} · {job["status"]}\n{job["created_utc"][:19]} · {job["connection"]["name"]}')
            item.setData(Qt.ItemDataRole.UserRole, job['id'])
            self.generation_jobs.addItem(item)
            if job['id'] == select:
                selected = item
        if selected:
            self.generation_jobs.setCurrentItem(selected)
        self.generation_jobs.blockSignals(False)
        if selected:
            self._select_generation_job()

    def _select_generation_job(self):
        item = self.generation_jobs.currentItem()
        if not item:
            return
        job = self.generation_service.load_job(item.data(Qt.ItemDataRole.UserRole))
        self.review_job = job
        self.generation_artifact.clear()
        self.generation_artifact.addItems(job.get('artifacts', []))
        self.generation_result_info.setText(f'{job["kind"]} · {job["status"]} · Target: {job.get("target", {})}\n'
            + job.get('review_note', job.get('error', ''))
            + ('\nUsage reported by provider: ' + json.dumps(job['usage']) if job.get('usage') else ''))
        text_draft = job['kind'] in ('script', 'story') and bool(job.get('artifacts'))
        self.generation_result.setReadOnly(not text_draft)
        self.generation_result.setPlainText((self._job_artifact(job, job['artifacts'][0])).read_text(encoding='utf-8') if text_draft else json.dumps(job, indent=2, ensure_ascii=False))
        self.apply_generation_button.setEnabled(job['status'] == 'ready')
        self.resume_generation_button.setEnabled(bool(job.get('remote_id')) and job['status'] != 'ready')

    def _job_artifact(self, job, name):
        if Path(name).name != name or name not in job.get('artifacts', []):
            raise ValueError('Invalid job artifact path')
        path = self.generation_service.jobs / job['id'] / name
        if not path.resolve().is_relative_to(self.generation_service.jobs.resolve()):
            raise ValueError('Result must stay inside the job directory')
        return path

    def _open_generation_result(self):
        if self.review_job and self.generation_artifact.currentText():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._job_artifact(self.review_job, self.generation_artifact.currentText()))))

    def _save_generation_edits(self):
        job = self.review_job
        if not job or job['status'] != 'ready' or job['kind'] not in ('story', 'script'):
            raise ValueError('Select a completed text draft')
        text = self.generation_result.toPlainText()
        if job['kind'] == 'script':
            parse_script(text)
        if not text.strip():
            raise ValueError('Draft cannot be empty')
        atomic_text(self._job_artifact(job, job['artifacts'][0]), text)
        self._set_status('Reviewed draft saved locally.')

    def _backup_for_generation(self):
        folder = self.episode.directory / 'drafts' / ('before_apply_' + uuid.uuid4().hex)
        folder.mkdir(parents=True)
        for name in ('scenes.json', 'script.md', 'subtitles.srt'):
            source = self.episode.directory / name
            if source.is_file():
                shutil.copyfile(source, folder / name)
        if self.story and (self.story / 'series_bible.md').is_file():
            shutil.copyfile(self.story / 'series_bible.md', folder / 'series_bible.md')
        return folder

    def _apply_generation_result(self):
        job = self.review_job
        if not job or job['status'] != 'ready' or not self.episode:
            raise ValueError('Open an episode and select a completed result')
        kind = job['kind']
        self._save()
        if kind in ('story', 'script'):
            text = self.generation_result.toPlainText()
            if not text.strip():
                raise ValueError('Draft is empty')
            if kind == 'script':
                revised = episode_from_draft(self.episode, text)
            backup = self._backup_for_generation()
            if kind == 'script':
                save_episode(revised)
                atomic_text(revised.directory / 'script.md', script_markdown(parse_script(text)))
                self.library.write_outline(revised)
                self.load_project(revised.directory / 'scenes.json')
            else:
                atomic_text(self.story / 'series_bible.md', text)
                self.load_project(self.episode.directory / 'scenes.json')
        else:
            if self.scene_index < 0:
                raise ValueError('Select a scene to receive this asset')
            path = self._job_artifact(job, self.generation_artifact.currentText())
            validate_artifact(path, kind)
            backup = self._backup_for_generation()
            relative = self.library.import_asset(self.episode, path)
            scene = self.episode.scenes[self.scene_index]
            if kind == 'voice':
                scene = replace(scene, narration_audio=relative, narration=job['prompt'], subtitle=None)
            else:
                changes = {'visual_asset': relative, 'media_type': kind, 'video_start_seconds': 0, 'video_audio_volume': 0}
                if kind == 'video':
                    from .video_assets import video_info
                    video_info(path)
                    changes.update(camera_motion='static', foreground_asset=None)
                scene = replace(scene, **changes)
            scenes = list(self.episode.scenes)
            scenes[self.scene_index] = scene
            self.episode = replace(self.episode, scenes=tuple(scenes))
            self._populate_scene(self.scene_index)
            self._save()
        self._set_status(f'Reviewed result applied. Previous files: {backup}. Run Check assets and adjust scene timing before rendering.')

    def _resume_generation(self):
        job = self.review_job
        if not job or not job.get('remote_id'):
            raise ValueError('Select a job with a saved provider task ID')
        self._run_task(lambda progress, cancel: self.generation_service.run(job['connection']['id'], job['kind'], job['prompt'],
                       resume=job['id'], cancel=cancel, progress=progress), self._generation_complete)

    def _import_text_draft(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import structured script JSON or story Markdown', str(self.library.root), 'Text drafts (*.json *.md *.txt)')
        if not path:
            return
        from datetime import datetime, timezone
        text = Path(path).read_text(encoding='utf-8-sig')
        kind = 'script' if Path(path).suffix.lower() == '.json' else 'story'
        if kind == 'script':
            parse_script(text)
        key = uuid.uuid4().hex
        folder = self.generation_service.jobs / key
        folder.mkdir(parents=True)
        atomic_text(folder / 'draft.txt', text)
        job = {'id': key, 'created_utc': datetime.now(timezone.utc).isoformat(), 'connection': {'name': 'Imported local draft'},
               'kind': kind, 'prompt': '', 'status': 'ready', 'remote_id': None, 'artifacts': ['draft.txt'], 'target': {}}
        atomic_json(folder / 'job.json', job)
        self._generation_complete(job)

    def _list_mcp_tools(self):
        key = self.software_connection.currentData()
        def complete(result):
            self.mcp_tool_picker.clear()
            for tool in result['tools']:
                self.mcp_tool_picker.addItem(tool['name'], tool)
            self.software_result.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
        self._run_task(lambda progress, cancel: mcp_action(self.generation_service, key, cancel=cancel), complete)

    def _mcp_tool_selected(self, *_):
        tool = self.mcp_tool_picker.currentData()
        self.mcp_tool_description.setPlainText(json.dumps(tool, indent=2, ensure_ascii=False) if tool else '')

    def _call_software(self):
        key = self.software_connection.currentData()
        _, conn = self.generation_service.connection(key)
        body = json.loads(self.software_arguments.toPlainText())
        if conn.provider == 'http':
            method, path = self.http_method.currentText(), self.http_path.text().strip()
            function = lambda progress, cancel: call_http(self.generation_service, key, method, path, None if method == 'GET' else body, cancel)
        else:
            tool = self.mcp_tool_picker.currentData()
            if not tool:
                raise ValueError('List and select an MCP tool first')
            function = lambda progress, cancel: mcp_action(self.generation_service, key, tool_name=tool['name'], arguments=body, cancel=cancel)
        self._run_task(function, lambda result: self.software_result.setPlainText(json.dumps(result, indent=2, ensure_ascii=False)))
