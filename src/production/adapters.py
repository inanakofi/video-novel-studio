"""Task routing to existing providers or an explicitly configured HTTP/MCP tool."""
import base64
from dataclasses import asdict, replace
import json
import mimetypes
from pathlib import Path
import shutil
import uuid

from ..audio_manager import synthesize_local
from ..connections.config import Connection, PRESETS
from ..connections.generation import validate_artifact
from ..connections.tools import call_http, mcp_action
from ..connections.transport import Transport, check_cancel
from ..connections.models import effective_model
from ..media import atomic_json
from ..story_manager import atomic_text


def capability(connection, kind):
    custom = connection.options.get('production', {})
    return kind in PRESETS[connection.provider][2] or (
        connection.provider in ('http', 'mcp_stdio', 'mcp_http')
        and isinstance(custom, dict) and isinstance(custom.get(kind), dict))


def substitute(value, inputs):
    if isinstance(value, str):
        if value.startswith('{{') and value.endswith('}}') and value[2:-2] in inputs:
            return inputs[value[2:-2]]
        for key, item in inputs.items():
            if isinstance(item, (str, int, float)):
                value = value.replace('{{' + key + '}}', str(item))
        return value
    if isinstance(value, dict):
        return {k: substitute(v, inputs) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v, inputs) for v in value]
    return value


def data_uri(path):
    path = Path(path)
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('A tool reference input exceeds 8 MiB. Resize/compress it before sending.')
    return 'data:' + (mimetypes.guess_type(path.name)[0] or 'application/octet-stream') + ';base64,' + base64.b64encode(path.read_bytes()).decode('ascii')


def unwrap(result):
    if not isinstance(result, dict):
        raise ValueError('Production tools must return a JSON object.')
    if result.get('isError'):
        raise ValueError('The production tool reported an error.')
    if isinstance(result.get('structuredContent'), dict):
        return result['structuredContent']
    if 'content' in result:
        blocks = result['content']
        text = '\n'.join(b.get('text', '') for b in blocks if b.get('type') == 'text')
        if text:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except ValueError:
                pass
            return {'text': text}
        for block in blocks:
            if block.get('type') in ('image', 'audio'):
                return {'base64': block['data'], 'mime_type': block['mimeType']}
    return result


class Router:
    def __init__(self, service, state, directory, save, cancel=None, progress=None):
        self.service, self.state, self.directory, self.save = service, state, directory, save
        self.cancel, self.progress = cancel, progress

    def generate(self, key, role, kind, prompt, **inputs):
        """Record intent before submission. Unknown outcomes never auto-resubmit."""
        check_cancel(self.cancel)
        stages = self.state['stages']
        route = self.state['config']['routes'][role]
        stage = stages.get(key)
        if stage and stage.get('status') == 'ready':
            path = self.directory / stage['artifact']
            if not path.is_file():
                raise ValueError(f'Missing saved artifact for {key}: {path}. Restore it or explicitly retry this stage.')
            if kind == 'story':
                return path.read_text(encoding='utf-8')
            validate_artifact(path, 'video' if kind == 'lipsync' else kind)
            return path
        if not stage:
            stage = stages[key] = {'status': 'pending', 'role': role, 'kind': kind, 'job_id': uuid.uuid4().hex}
            self.save()
        work = self.directory / 'stages' / key
        work.mkdir(parents=True, exist_ok=True)
        atomic_text(work / 'prompt.txt', prompt)
        self.state['current_stage'] = key
        self.save()
        if self.progress:
            self.progress(0, key.replace('_', ' '))
        if route == 'local_speech':
            path = work / 'speech.wav'
            synthesize_local(prompt, path, voice=self.state['config'].get('local_voice', ''), cancel=self.cancel)
        else:
            mode, connection = self.service.connection(route)
            if asdict(connection) != self.state['connections'][route]:
                raise ValueError(f'Connection {connection.name} changed. Restore its saved settings before resuming; see run.json.')
            connection = replace(connection, model=effective_model(self.state['config'], role, connection))
            if not capability(connection, kind):
                raise ValueError(f'{connection.name} cannot perform {kind}. Configure the matching production tool.')
            if connection.provider not in ('http', 'mcp_stdio', 'mcp_http'):
                job_path = self.service.jobs / stage['job_id'] / 'job.json'
                resume = stage['job_id'] if job_path.exists() else None
                # A crash before the service creates job.json has not submitted anything.
                job = self.service.run(route, kind, prompt, cancel=self.cancel, resume=resume, job_id=stage['job_id'],
                                       model=connection.model, voice=self.state['config'].get('voices', {}).get(role),
                                       target={'production_run': self.state['id'], 'stage': key},
                                       progress=(lambda fraction, message: self.progress(fraction, key + ': ' + message)) if self.progress else None)
                source = self.service.jobs / job['id'] / job['artifacts'][0]
                path = work / source.name
                shutil.copyfile(source, path)
            else:
                response_file = work / 'response.json'
                if response_file.exists():
                    result = json.loads(response_file.read_text(encoding='utf-8'))
                else:
                    if stage['status'] == 'submitted':
                        raise ValueError(f'{key}: tool outcome is unknown. Check the tool history and use Retry selected stage only when safe. No automatic resubmission was made.')
                    spec = connection.options['production'][kind]
                    suffix = {'story': '.txt', 'image': '.png', 'voice': '.wav', 'video': '.mp4', 'lipsync': '.mp4'}[kind]
                    values = {'prompt': prompt, 'text': prompt, 'model': connection.model, 'kind': kind,
                              'request_id': stage['job_id'], 'output_path': str((work / ('result' + suffix)).resolve()),
                              'duration': 0, 'speaker': 'NARRATOR', 'reference_paths': [], 'audio_path': '', 'video_path': '', **inputs}
                    # Only materialize image/audio payloads explicitly requested by the user template.
                    template = json.dumps(spec)
                    if '{{reference_images}}' in template:
                        values['reference_images'] = [data_uri(p) for p in inputs.get('reference_paths', [])]
                    if '{{audio_data_uri}}' in template:
                        values['audio_data_uri'] = data_uri(inputs['audio_path']) if inputs.get('audio_path') else ''
                    if '{{video_data_uri}}' in template:
                        values['video_data_uri'] = data_uri(inputs['video_path']) if inputs.get('video_path') else ''
                    arguments = substitute(spec.get('arguments', {'prompt': '{{prompt}}', 'output_path': '{{output_path}}'}), values)
                    stage['status'] = 'submitted'
                    self.save()
                    if connection.provider == 'http':
                        result = call_http(self.service, route, 'POST', spec['path'], arguments, self.cancel,
                                           capture_submission=True)
                    else:
                        result = mcp_action(self.service, route, tool_name=spec['tool'], arguments=arguments, cancel=self.cancel)
                    # Preserve the response even if cancellation arrives immediately after submission.
                    atomic_json(response_file, result)
                data = unwrap(result)
                if kind == 'story':
                    path = work / 'draft.txt'
                    text = data.get('text')
                    atomic_text(path, text if isinstance(text, str) else json.dumps(data, ensure_ascii=False))
                else:
                    path = self._artifact(work, data, kind, mode)
        if kind != 'story':
            validate_artifact(path, 'video' if kind == 'lipsync' else kind)
        stage.update(status='ready', artifact=path.relative_to(self.directory).as_posix())
        self.save()
        return path.read_text(encoding='utf-8') if kind == 'story' else path

    def _artifact(self, work, data, kind, mode):
        allowed = {'image': {'.png', '.jpg', '.jpeg', '.webp'}, 'voice': {'.wav', '.mp3', '.ogg', '.m4a'},
                   'video': {'.mp4', '.webm', '.mov'}, 'lipsync': {'.mp4', '.webm', '.mov'}}[kind]
        if isinstance(data.get('path'), str):
            source = Path(data['path']).resolve()
            if not source.is_relative_to(work.resolve()) or source.suffix.lower() not in allowed:
                raise ValueError('Tool files must be written inside the supplied output_path directory with a supported media extension.')
            if not source.is_file() or source.stat().st_size > 512 * 1024**2:
                raise ValueError('Tool output is missing or larger than 512 MiB.')
            return source
        suffix = data.get('extension') or mimetypes.guess_extension(data.get('mime_type', ''))
        suffix = suffix or {'image': '.png', 'voice': '.wav', 'video': '.mp4', 'lipsync': '.mp4'}[kind]
        if suffix == '.jpe':
            suffix = '.jpg'
        if suffix not in allowed:
            raise ValueError('Tool returned an unsupported media extension.')
        path = work / ('result' + suffix)
        if isinstance(data.get('url'), str):
            downloader = Transport(Connection('download', 'Artifact download', 'http', data['url'], enabled=True), mode, cancel=self.cancel)
            downloader.download(data['url'], path)  # Never forward provider credentials to artifact hosts.
        elif isinstance(data.get('base64'), str):
            if len(data['base64']) > 64 * 1024**2:
                raise ValueError('Base64 output exceeds 64 MiB; return an artifact URL instead.')
            path.write_bytes(base64.b64decode(data['base64'], validate=True))
        else:
            raise ValueError('Media tools must return {path}, {url} or {base64, mime_type}, not a job ID. Use a tool that waits for its completed artifact.')
        return path
