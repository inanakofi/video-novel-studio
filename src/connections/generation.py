"""Real provider adapters and durable, reviewable local generation jobs."""
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
from urllib.parse import quote, urlencode
import uuid

from .config import ConnectionStore, SecretStore, PRESETS, identifier
from .transport import ConnectionError, Transport, check_cancel
from ..media import atomic_json, audio_duration, probe
from ..story_manager import atomic_text


SCRIPT_INSTRUCTIONS = '''Draft an episode as a JSON object only, without code fences.
Use this structure: {"title":"...", "hook":"...", "cliffhanger":"...", "scenes":[
{"narration":"spoken text", "duration_seconds":6, "visual_description":"art direction",
"camera_motion":"slow_zoom_in", "transition":"crossfade"}]}.
Each scene must have narration, positive duration_seconds and visual_description.
Camera motion: static, slow_zoom_in, slow_zoom_out, pan_left or pan_right.
Transition: cut, crossfade or fade_black. Do not invent file paths or audio files.
Allow sufficient time for the spoken words. Preserve supplied continuity.
'''


def prompt_for(kind, instruction, context=''):
    prefix = SCRIPT_INSTRUCTIONS if kind == 'script' else (
        'Draft a series bible in Markdown with premise, characters, locations, series arc, hooks and continuity notes.\n'
        if kind == 'story' else '')
    return prefix + instruction.strip() + ('\n\nUser-selected story context:\n' + context if context.strip() else '')


def parse_script(text):
    stripped = text.strip()
    if stripped.startswith('```') and stripped.endswith('```'):
        stripped = '\n'.join(stripped.splitlines()[1:-1])
    try:
        data = json.loads(stripped)
    except ValueError as error:
        raise ValueError('Script draft must be a JSON object. Edit the result before applying it.') from error
    if not isinstance(data, dict) or any(not isinstance(data.get(k), str) or not data[k].strip() for k in ('title', 'hook', 'cliffhanger')):
        raise ValueError('Script needs nonempty title, hook and cliffhanger strings')
    scenes = data.get('scenes')
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 100:
        raise ValueError('Script must contain 1–100 structured scenes')
    for i, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise ValueError(f'Draft scene {i} must be an object')
        for key in ('narration', 'visual_description'):
            if not isinstance(scene.get(key), str) or not scene[key].strip():
                raise ValueError(f'Draft scene {i} needs {key}')
        duration = scene.get('duration_seconds')
        if type(duration) not in (int, float) or not math.isfinite(duration) or not .1 <= duration <= 600:
            raise ValueError(f'Draft scene {i}: duration must be 0.1–600 seconds')
        if scene.get('camera_motion', 'slow_zoom_in') not in ('static', 'slow_zoom_in', 'slow_zoom_out', 'pan_left', 'pan_right'):
            raise ValueError(f'Draft scene {i}: unsupported camera motion')
        if scene.get('transition', 'crossfade') not in ('cut', 'crossfade', 'fade_black'):
            raise ValueError(f'Draft scene {i}: unsupported transition')
    return data


def episode_from_draft(episode, text):
    """Model output cannot choose paths. Existing visuals are reused by position."""
    from ..scene_builder import Scene
    data = parse_script(text)
    fps = episode.settings.get('fps', 30)
    scenes = []
    for i, record in enumerate(data['scenes']):
        old = episode.scenes[i] if i < len(episode.scenes) else None
        media_type = old.media_type if old else 'image'
        scenes.append(Scene(i + 1, math.ceil(record['duration_seconds'] * fps) / fps,
                            old.visual_asset if old else f'assets/scene_{i + 1:03}.png',
                            record['narration'], 'static' if media_type == 'video' else record.get('camera_motion', 'slow_zoom_in'),
                            'cinematic', transition=record.get('transition', 'crossfade'),
                            characters=old.characters if old else (), location=old.location if old else None,
                            media_type=media_type, video_start_seconds=old.video_start_seconds if old else 0,
                            video_audio_volume=old.video_audio_volume if old else 0))
    # Stale recordings and manually timed captions must not silently narrate new prose.
    return replace(episode, title=data['title'], scenes=tuple(scenes),
                   settings={**episode.settings, 'subtitle_mode': 'auto', 'narration_asset': 'narration_required.wav'},
                   metadata={**episode.metadata, 'hook': data['hook'], 'cliffhanger': data['cliffhanger'],
                             'visual_directions': [s['visual_description'] for s in data['scenes']]})


def script_markdown(data):
    return '# ' + data['title'] + '\n\n' + '\n\n'.join(
        f'## Scene {i}\n\n{s["narration"]}' for i, s in enumerate(data['scenes'], 1)) + '\n'


def validate_artifact(path, kind):
    if kind == 'image':
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
    elif kind == 'voice':
        if audio_duration(path) <= 0:
            raise ValueError('Generated audio is empty')
    elif kind == 'video':
        info = probe(path)
        streams = [s for s in info['streams'] if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic')]
        if not streams or float(streams[0].get('duration', info.get('format', {}).get('duration', 0))) <= 0:
            raise ValueError('Generated file has no playable video stream')


class GenerationService:
    def __init__(self, root, secrets=None):
        self.root = Path(root)
        self.store = ConnectionStore(self.root)
        self.secrets = secrets or SecretStore()
        self.jobs = self.root / '.generation_jobs'

    def connection(self, connection_id):
        mode, profiles = self.store.load()
        if mode == 'disabled':
            raise ConnectionError('Connections are disabled. Enable local-only or online connections first.')
        connection = next((c for c in profiles if c.id == connection_id), None)
        if not connection or not connection.enabled:
            raise ConnectionError('Connection is missing or disabled')
        return mode, connection

    def transport(self, connection_id, cancel=None):
        mode, connection = self.connection(connection_id)
        return Transport(connection, mode, self.secrets.get(connection), cancel)

    def discover(self, connection_id, cancel=None):
        transport = self.transport(connection_id, cancel)
        provider = transport.connection.provider
        paths = {'ollama': '/api/tags', 'openrouter': '/models', 'openai_compatible': '/models',
                 'elevenlabs': '/voices', 'comfyui': '/system_stats', 'runway': '/organization'}
        if provider not in paths:
            raise ValueError('Use the Tools panel to test this connection')
        result = transport.request('GET', paths[provider])
        models = []
        if provider == 'ollama':
            models = [m['name'] for m in result.get('models', [])]
        elif provider in ('openrouter', 'openai_compatible'):
            models = [m['id'] for m in result.get('data', [])]
        return {'status': 'Endpoint responded; generation not tested', 'models': models, 'response': result}

    def list_jobs(self):
        if not self.jobs.exists():
            return []
        result = []
        for path in sorted(self.jobs.glob('*/job.json'), reverse=True):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                identifier(data['id'])
                result.append(data)
            except (OSError, ValueError, KeyError):
                continue
        return sorted(result, key=lambda j: j['created_utc'], reverse=True)

    def load_job(self, job_id):
        path = self.jobs / identifier(job_id) / 'job.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        if data['id'] != job_id:
            raise ValueError('Job ID mismatch')
        return data

    def run(self, connection_id, kind, prompt, *, cancel=None, progress=None, resume=None, target=None):
        transport = self.transport(connection_id, cancel)
        connection = transport.connection
        if kind not in PRESETS[connection.provider][2]:
            raise ValueError(f'{connection.name} does not support {kind} in this adapter')
        if not prompt.strip():
            raise ValueError('Enter a prompt before generating')
        if connection.provider in ('ollama', 'openrouter', 'openai_compatible', 'runway') and not connection.model:
            raise ValueError('Choose or enter a model ID')
        job = self.load_job(resume) if resume else {
            'id': uuid.uuid4().hex, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'connection': asdict(connection), 'kind': kind, 'prompt': prompt,
            'status': 'created', 'remote_id': None, 'artifacts': [], 'target': target or {},
        }
        if resume and (job['connection'] != asdict(connection) or job['kind'] != kind):
            raise ValueError('Restore the original connection settings before resuming this job')
        if resume and job['status'] == 'ready':
            return job
        if resume and not job['remote_id']:
            raise ValueError('This job has no provider task ID. Check provider history; do not blindly resubmit.')
        directory = self.jobs / identifier(job['id'])
        directory.mkdir(parents=True, exist_ok=True)
        lock = directory / 'running.lock'
        try:
            handle = lock.open('x')
        except FileExistsError:
            raise ValueError('This job is already being retrieved. After a process crash, remove its running.lock only when no worker remains.') from None
        def save():
            atomic_json(directory / 'job.json', job)
        def notify(message):
            check_cancel(cancel)
            if progress:
                progress(.3, message)
        try:
            with handle:
                import os
                handle.write(str(os.getpid()))
            job['status'] = 'running'
            save()
            notify(f'Contacting {connection.name}; results will be saved for review')
            provider = connection.provider
            options = connection.options
            if kind in ('story', 'script'):
                if provider == 'ollama':
                    result = transport.request('POST', '/api/generate', {
                        'model': connection.model, 'prompt': prompt, 'stream': False,
                        **({'format': 'json'} if kind == 'script' else {}),
                        'options': options.get('generation', {}),
                    })
                    text = result.get('response')
                    job['usage'] = {k: result[k] for k in ('prompt_eval_count', 'eval_count', 'total_duration') if k in result}
                else:
                    extra = options.get('generation', {})
                    if not isinstance(extra, dict) or set(extra) - {'temperature', 'top_p', 'max_tokens', 'max_completion_tokens', 'seed', 'response_format'}:
                        raise ValueError('Unsupported text generation options')
                    result = transport.request('POST', '/chat/completions', {
                        **extra, 'model': connection.model, 'messages': [{'role': 'user', 'content': prompt}], 'stream': False,
                    })
                    choices = result.get('choices', [])
                    if not choices or choices[0].get('error') or choices[0].get('finish_reason') in ('error', 'content_filter', 'length', 'tool_calls'):
                        raise ConnectionError('Provider returned an incomplete, filtered or failed text result. No draft was applied.')
                    text = choices[0].get('message', {}).get('content')
                    job['usage'] = result.get('usage', {})
                    job['provider_response_id'] = result.get('id')
                if not isinstance(text, str) or not text.strip():
                    raise ConnectionError('Provider returned no text')
                atomic_text(directory / 'draft.txt', text)
                job['artifacts'] = ['draft.txt']
                if kind == 'script':
                    try:
                        parse_script(text)
                        job['script_valid'] = True
                    except ValueError as error:
                        job['script_valid'] = False
                        job['review_note'] = str(error)
            elif provider == 'elevenlabs':
                voice = options.get('voice_id', '')
                if not voice:
                    raise ValueError('Set options.voice_id using a voice from Test / discover')
                body = {'text': prompt}
                if connection.model:
                    body['model_id'] = connection.model
                if 'voice_settings' in options:
                    body['voice_settings'] = options['voice_settings']
                content = transport.request('POST', '/text-to-speech/' + quote(voice, safe='') + '?output_format=mp3_44100_128', body, raw=True)
                path = directory / 'narration.mp3'
                path.write_bytes(content)
                validate_artifact(path, kind)
                job['artifacts'] = [path.name]
            elif provider in ('comfyui', 'runway'):
                if not job['remote_id']:
                    if provider == 'comfyui':
                        workflow = options.get('workflow')
                        if not isinstance(workflow, dict) or not workflow or not all(isinstance(v, dict) and 'class_type' in v and isinstance(v.get('inputs'), dict) for v in workflow.values()):
                            raise ValueError('ComfyUI needs an API-format workflow object in options.workflow')
                        replacements = [0]
                        def substitute(value):
                            if isinstance(value, str):
                                replacements[0] += value.count('{{prompt}}')
                                return value.replace('{{prompt}}', prompt)
                            if isinstance(value, list):
                                return [substitute(v) for v in value]
                            if isinstance(value, dict):
                                return {k: substitute(v) for k, v in value.items()}
                            return value
                        graph = substitute(workflow)
                        if not replacements[0]:
                            raise ValueError('Place {{prompt}} in a ComfyUI text input so the reviewed prompt is used')
                        result = transport.request('POST', '/prompt', {'prompt': graph, 'client_id': job['id']}, capture_submission=True)
                        if result.get('error') or result.get('node_errors'):
                            raise ConnectionError('ComfyUI rejected workflow nodes. Check installed models and the exported API workflow.')
                        job['remote_id'] = result.get('prompt_id')
                    else:
                        duration = options.get('duration', 5)
                        if type(duration) is not int or not 2 <= duration <= 10:
                            raise ValueError('Runway duration must be an integer from 2 to 10; the model may impose tighter limits')
                        body = {'model': connection.model, 'promptText': prompt, 'duration': duration,
                                'ratio': options.get('ratio', '720:1280')}
                        for key in ('seed', 'audio', 'negativePrompt'):
                            if key in options:
                                body[key] = options[key]
                        job['remote_id'] = transport.request('POST', '/text_to_video', body, capture_submission=True).get('id')
                    if not isinstance(job['remote_id'], str) or not job['remote_id']:
                        raise ConnectionError('Provider did not return a task ID. Check its history before submitting again.')
                    save()  # Commit provider ID before polling/downloading.
                notify('Job submitted. Stop waiting is safe; Resume retrieves the same task.')
                artifacts = self._poll(transport, job, directory, notify)
                job['artifacts'] = artifacts
            job['status'] = 'ready'
            job.pop('error', None)
            save()
            if progress:
                progress(1, 'Result saved locally. Review it before applying to your story.')
            return job
        except Exception as error:
            job['status'] = 'waiting' if job.get('remote_id') else 'failed_or_unknown'
            message = str(error)
            if transport.secret:
                message = message.replace(transport.secret, '[redacted]')
            job['error'] = message
            save()
            raise ConnectionError(message) from None
        finally:
            lock.unlink(missing_ok=True)

    def _poll(self, transport, job, directory, notify):
        provider = transport.connection.provider
        remote = quote(job['remote_id'], safe='')
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            check_cancel(transport.cancel)
            if provider == 'runway':
                result = transport.request('GET', '/tasks/' + remote)
                status = result.get('status')
                if status in ('FAILED', 'CANCELED', 'CANCELLED'):
                    raise ConnectionError(f'Runway task {status.lower()}. Check provider task history for its failure reason.')
                if status == 'SUCCEEDED':
                    outputs = result.get('output', [])
                    if not outputs:
                        raise ConnectionError('Completed Runway task returned no media')
                    path = directory / 'video.mp4'
                    transport.download(outputs[0], path)
                    validate_artifact(path, 'video')
                    return [path.name]
            else:
                history = transport.request('GET', '/history/' + remote)
                result = history.get(job['remote_id'], {})
                status = result.get('status', {})
                if status.get('status_str') == 'error':
                    raise ConnectionError('ComfyUI workflow failed. Inspect its history and node errors.')
                if status.get('completed') or result.get('outputs'):
                    found = []
                    for output in result.get('outputs', {}).values():
                        for group in ('images', 'gifs', 'videos'):
                            for item in output.get(group, []):
                                filename = item.get('filename', '')
                                suffix = Path(filename).suffix.lower()
                                allowed = ('.png', '.jpg', '.jpeg', '.webp') if job['kind'] == 'image' else ('.mp4', '.webm', '.mov', '.mkv')
                                if suffix not in allowed:
                                    continue
                                path = directory / f'output_{len(found) + 1:03}{suffix}'
                                query = urlencode({k: item.get(k, '') for k in ('filename', 'subfolder', 'type')})
                                transport.download(transport.url('/view?' + query), path, authenticated=True)
                                validate_artifact(path, job['kind'])
                                found.append(path.name)
                    if not found:
                        raise ConnectionError('Workflow completed without matching saved media. Use a SaveImage or video output node and select the correct generation type.')
                    return found
            notify('Waiting for provider; this retrieves the existing task')
            if transport.cancel:
                transport.cancel.wait(2)
            else:
                time.sleep(2)
        raise ConnectionError('Stopped polling after 30 minutes. Resume this job later; no second generation is needed.')
