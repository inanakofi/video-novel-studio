"""Resumable, bounded manuscript production. External calls are sequential."""
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import uuid

from .adapters import Router, capability
from .manuscript import extract, chunks
from .prompts import VERSION, SOURCE, PROMPTS, FORMATS, instructions
from ..connections.config import identifier
from ..connections.generation import GenerationService
from ..connections.models import effective_model
from ..connections.transport import check_cancel, validate_url
from ..audio_manager import inspect_narration, installed_voices
from ..media import atomic_json, audio_duration, ffmpeg, tool
from ..scene_builder import Episode, Scene, save_episode
from ..story_manager import StoryLibrary, atomic_text, slug
from ..subtitle_generator import make_cues, cues_to_srt
from ..video_assets import video_info
from ..video_renderer import render_episode

ROLE_KINDS = {'analysis': 'story', 'writing': 'story', 'review': 'story', 'image': 'image',
              'video': 'video', 'voice': 'voice', 'lipsync': 'lipsync'}


def object_from(text):
    text = text.strip()
    if text.startswith('```') and text.endswith('```'):
        text = '\n'.join(text.splitlines()[1:-1])
    try:
        value = json.loads(text)
    except ValueError:
        raise ValueError('Model output is not complete JSON. Open this stage\'s draft.txt, correct it, then Resume; or explicitly retry the stage.') from None
    if not isinstance(value, dict):
        raise ValueError('The model must return a JSON object.')
    return value


def text_field(data, key, limit=30000, empty=False):
    value = data.get(key)
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError(f'Model field {key} must be text, at most {limit} characters.')
    return value


def validate_plan(plan, count, source_ids):
    for key in ('title', 'premise', 'series_bible', 'style_bible', 'audio_bible'):
        text_field(plan, key)
    for kind, prefix in (('characters', 'CHAR'), ('locations', 'LOC')):
        records = plan.get(kind)
        if not isinstance(records, list) or not 1 <= len(records) <= 30:
            raise ValueError(f'Plan needs 1–30 {kind}.')
        ids = set()
        for row in records:
            if not isinstance(row, dict):
                raise ValueError(f'Invalid {kind} record.')
            value = text_field(row, 'id', 30)
            if not re.fullmatch(prefix + r'-[0-9]{3}', value) or value in ids:
                raise ValueError(f'Use unique {prefix}-001-style IDs.')
            ids.add(value)
            text_field(row, 'name', 200)
            text_field(row, 'description', 6000)
    episodes = plan.get('episodes')
    if not isinstance(episodes, list) or len(episodes) != count:
        raise ValueError(f'Plan must contain exactly {count} episodes.')
    for episode in episodes:
        if not isinstance(episode, dict):
            raise ValueError('Episode plan must be an object.')
        text_field(episode, 'title', 300)
        text_field(episode, 'outline', 5000)
        refs = episode.get('source_chunks')
        if not isinstance(refs, list) or not refs or len(refs) > 6 or any(not isinstance(r, str) or r not in source_ids for r in refs):
            raise ValueError('Each episode needs 1–6 valid source chunk IDs. Use shorter source selections for small models.')


def validate_script(script, plan):
    for key in ('title', 'hook', 'cliffhanger', 'handoff'):
        text_field(script, key, empty=key == 'cliffhanger')
    text_field(script, 'handoff', 4000)
    shots = script.get('shots')
    if not isinstance(shots, list) or not 1 <= len(shots) <= 100:
        raise ValueError('An episode script needs 1–100 shots. Reduce episode length if necessary.')
    characters = {r['id'] for r in plan['characters']}
    locations = {r['id'] for r in plan['locations']}
    for shot in shots:
        if not isinstance(shot, dict):
            raise ValueError('Each shot must be an object.')
        text_field(shot, 'text', 1800, empty=True)
        text_field(shot, 'visual', 6000)
        if shot.get('speaker') not in characters | {'NARRATOR'}:
            raise ValueError('Shot speaker must be NARRATOR or a canonical character ID.')
        cast = shot.get('characters')
        if not isinstance(cast, list) or any(not isinstance(c, str) or c not in characters for c in cast):
            raise ValueError('Shot characters must contain canonical character IDs.')
        if shot.get('location') not in locations:
            raise ValueError('Shot location must be a canonical location ID.')
        duration = shot.get('seconds')
        if type(duration) not in (int, float) or not math.isfinite(duration) or not 1 <= duration <= 60:
            raise ValueError('Shot seconds must be a number from 1 to 60.')


class ProductionRunner:
    def __init__(self, root, service=None):
        self.root = Path(root).resolve()
        self.runs = self.root / '.production_runs'
        self.service = service or GenerationService(self.root)

    def preflight(self, config):
        if config.get('format') not in FORMATS or config.get('adaptation') not in ('faithful', 'original'):
            raise ValueError('Choose a video format and adaptation approach.')
        if not isinstance(config.get('title'), str) or not config['title'].strip():
            raise ValueError('Enter a series title.')
        for key, low, high in (('episodes', 1, 24), ('seconds', 15, 1200), ('max_calls', 5, 5000)):
            if type(config.get(key)) is not int or not low <= config[key] <= high:
                raise ValueError(f'{key} must be an integer from {low} to {high}.')
        if config.get('resolution', 'preview') not in ('preview', 'full'):
            raise ValueError('Choose preview or full resolution.')
        if type(config.get('references', False)) is not bool or type(config.get('pause_after_plan', False)) is not bool:
            raise ValueError('Invalid production options.')
        if not isinstance(config.get('routes'), dict):
            raise ValueError('Production routes must be an object of task names to connection IDs.')
        for key in ('models', 'speaker_models', 'voices'):
            values = config.get(key, {})
            if not isinstance(values, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in values.items()):
                raise ValueError(f'{key} must be an object of task/speaker names to text values.')
        if set(config.get('models', {})) - ROLE_KINDS.keys():
            raise ValueError('Unknown task in model selections.')
        tool('ffmpeg')
        tool('ffprobe')
        required = {'analysis', 'writing', 'review', 'voice', 'image' if config['format'] == 'narrated' else 'video'}
        if config.get('references'):
            required.add('image')
        if config.get('routes', {}).get('lipsync'):
            if config['format'] == 'narrated':
                raise ValueError('Lip-sync applies to animated/cinematic video, not still illustrations.')
            required.add('lipsync')
        snapshots = {}
        local_speech_needed = False
        def validate_route(role, route, model_role=None):
            nonlocal local_speech_needed
            if not route:
                raise ValueError(f'Choose a connection for {role}.')
            if route == 'local_speech' and role == 'voice':
                if os.name != 'nt':
                    raise ValueError('Installed speech is Windows-only. Choose a voice connection.')
                local_speech_needed = True
                return
            mode, connection = self.service.connection(route)
            snapshots[route] = asdict(connection)
            connection = replace(connection, model=effective_model(config, model_role or role, connection))
            voice = config.get('voices', {}).get(model_role or role, '')
            if voice:
                connection = replace(connection, options={**connection.options, 'voice_id': voice})
            self.service.catalog.validate_selection(connection, ROLE_KINDS[role])
            if connection.provider != 'mcp_stdio':
                validate_url(connection.base_url, mode)
            if not capability(connection, ROLE_KINDS[role]):
                raise ValueError(f'{connection.name} does not support {role}. Choose a matching provider or configure options.production.')
            if connection.provider in ('http', 'mcp_stdio', 'mcp_http'):
                spec = connection.options['production'][ROLE_KINDS[role]]
                key = 'path' if connection.provider == 'http' else 'tool'
                if not isinstance(spec.get(key), str) or not spec[key].strip() or not isinstance(spec.get('arguments', {}), dict):
                    raise ValueError(f'{connection.name}: production.{ROLE_KINDS[role]} needs {key} and an arguments object.')
                if connection.provider == 'http' and (not spec['path'].startswith('/') or spec['path'].startswith('//') or '\\' in spec['path']):
                    raise ValueError(f'{connection.name}: production path must start with a single /.')
                if connection.provider.startswith('mcp_') and importlib.util.find_spec('mcp') is None:
                    raise ValueError('Install requirements-integrations.txt before starting an MCP production.')
                if connection.provider == 'mcp_stdio' and not connection.options.get('command'):
                    raise ValueError(f'{connection.name}: configure the MCP program command.')
            elif connection.provider in ('ollama', 'openrouter', 'openai_compatible', 'runway') and not connection.model:
                raise ValueError(f'{connection.name}: choose a model for {role}, or set a default model in Connections / AI.')
            elif connection.provider == 'elevenlabs' and not connection.options.get('voice_id'):
                raise ValueError(f'{connection.name}: set options.voice_id.')
            elif connection.provider == 'comfyui':
                graph = connection.options.get('workflow')
                if not isinstance(graph, dict) or not graph or not all(isinstance(v, dict) and 'class_type' in v and isinstance(v.get('inputs'), dict) for v in graph.values()) or '{{prompt}}' not in json.dumps(graph):
                    raise ValueError(f'{connection.name}: load a valid API workflow containing {{{{prompt}}}}.')
                if '{{model}}' in json.dumps(graph) and not connection.model:
                    raise ValueError(f'{connection.name}: choose a model for the workflow’s {{{{model}}}} input.')
        for role in required:
            validate_route(role, config['routes'].get(role))
        voices = config.get('speaker_routes', {})
        if not isinstance(voices, dict):
            raise ValueError('Speaker routes must be a JSON object of speaker ID to connection ID.')
        for speaker, route in voices.items():
            if not isinstance(speaker, str) or not re.fullmatch(r'NARRATOR|CHAR-[0-9]{3}', speaker):
                raise ValueError('Voice overrides use NARRATOR or CHAR-001-style IDs.')
            validate_route('voice', route, 'voice_' + speaker)
        if set(config.get('speaker_models', {})) - voices.keys():
            raise ValueError('Each speaker model override needs a matching speaker connection override.')
        if local_speech_needed:
            voices = installed_voices()
            if not voices or (config.get('local_voice') and config['local_voice'] not in voices):
                raise ValueError('The selected installed speech voice is unavailable. Choose an installed voice or a speech connection before starting.')
        return snapshots

    def create(self, manuscript, config):
        config = json.loads(json.dumps(config))
        snapshots = self.preflight(config)
        source = extract(manuscript)
        run_id = uuid.uuid4().hex
        directory = self.runs / run_id
        directory.mkdir(parents=True)
        atomic_text(directory / 'source.txt', source)
        shutil.copyfile(manuscript, directory / ('manuscript' + Path(manuscript).suffix.lower()))
        atomic_json(directory / 'source_chunks.json', {'chunks': chunks(source)})
        atomic_json(directory / 'prompt_library.json', {'version': VERSION, 'source': SOURCE, 'prompts': PROMPTS})
        state = {'version': 1, 'id': run_id, 'created_utc': datetime.now(timezone.utc).isoformat(),
                 'config': config, 'connections': snapshots, 'prompt_version': VERSION,
                 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                 'source_name': Path(manuscript).name, 'status': 'created', 'current_stage': '',
                 'stages': {}, 'exports': [], 'calls': 0, 'plan_accepted': not config.get('pause_after_plan', False),
                 'story': 'stories/' + slug(config['title']) + '_' + run_id[:8]}
        atomic_json(directory / 'run.json', state)
        return state

    def load(self, run_id):
        state = json.loads((self.runs / identifier(run_id) / 'run.json').read_text(encoding='utf-8'))
        if not isinstance(state, dict) or state.get('version') != 1 or state.get('id') != run_id:
            raise ValueError('Unsupported or mismatched production run.')
        if (any(not isinstance(state.get(key), str) for key in ('created_utc', 'story', 'status', 'current_stage'))
                or not isinstance(state.get('config'), dict)
                or not isinstance(state['config'].get('title'), str)
                or state['config'].get('format') not in FORMATS
                or not isinstance(state.get('stages'), dict)
                or not isinstance(state.get('exports'), list)):
            raise ValueError('Invalid saved production run.')
        story = (self.root / state['story']).resolve()
        if not story.is_relative_to(self.root / 'stories'):
            raise ValueError('Production story must remain inside this workspace.')
        return state

    def list_runs(self):
        result = []
        for path in self.runs.glob('*/run.json'):
            try:
                result.append(self.load(path.parent.name))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sorted(result, key=lambda item: item['created_utc'], reverse=True)

    def update_speakers(self, run_id, overrides):
        state = self.load(run_id)
        directory = self.runs / run_id
        if state['status'] != 'awaiting_plan' or (directory / 'running.lock').exists():
            raise ValueError('Voice overrides can be changed only while paused at the series plan, before media generation.')
        config = {**state['config'], 'speaker_routes': overrides}
        snapshots = self.preflight(config)
        for key in state['connections'].keys() & snapshots.keys():
            if state['connections'][key] != snapshots[key]:
                raise ValueError('An existing connection changed. Restore its original settings before assigning voices.')
        state['config'] = config
        state['connections'].update(snapshots)
        atomic_json(directory / 'run.json', state)
        return state

    def retry_stage(self, run_id):
        state = self.load(run_id)
        directory = self.runs / run_id
        if (directory / 'running.lock').exists() or state['status'] != 'needs_attention':
            raise ValueError('Only a stopped run needing attention can retry its current stage.')
        key = state.get('current_stage')
        if key not in state['stages']:
            raise ValueError('This failure was local. Correct it and use Resume instead.')
        # Keep every original submission and response; a retry gets a new stage directory and job ID.
        stage = state['stages'].pop(key)
        attempt = len(state.setdefault('retries', [])) + 1
        state['retries'].append({'stage': key, 'record': stage, 'attempt': attempt})
        work = directory / 'stages' / key
        archive = directory / 'attempts' / f'{attempt:03}_{key}'
        if work.exists():
            archive.parent.mkdir(exist_ok=True)
            # Both resolved paths are confined to this run; os.rename is a non-recursive directory rename.
            if not work.resolve().is_relative_to(directory.resolve()) or not archive.resolve().is_relative_to(directory.resolve()):
                raise ValueError('Retry paths escaped the production run.')
            work.rename(archive)
        state['status'] = 'paused'
        atomic_json(directory / 'run.json', state)

    def run(self, run_id, *, cancel=None, progress=None, accept_plan=False):
        state = self.load(run_id)
        directory = self.runs / run_id
        lock = directory / 'running.lock'
        try:
            handle = lock.open('x', encoding='utf-8')
        except FileExistsError:
            raise ValueError('This production is already running. After a crash, remove its running.lock only after verifying that its worker has stopped.') from None
        def save():
            atomic_json(directory / 'run.json', state)
        try:
            with handle:
                handle.write(str(os.getpid()))
            # Another worker may have completed between our initial read and
            # exclusive open. Use the state protected by this lock.
            state = self.load(run_id)
            if state['status'] == 'complete':
                return state
            self.preflight(state['config'])
            if state['prompt_version'] != VERSION:
                raise ValueError('This run uses a different prompt version. Resume using the original application version.')
            state.update(status='running', error='')
            if accept_plan:
                state['plan_accepted'] = True
            save()
            router = Router(self.service, state, directory, save, cancel, progress)
            self._produce(state, directory, router, save, cancel, progress)
            return state
        except Exception as error:
            state['status'] = 'paused' if cancel and cancel.is_set() else 'needs_attention'
            state['error'] = str(error)
            save()
            raise
        finally:
            lock.unlink(missing_ok=True)

    def _produce(self, state, directory, router, save, cancel, progress):
        config = state['config']
        video_format = config['format']
        catalog = json.loads((directory / 'source_chunks.json').read_text(encoding='utf-8'))['chunks']

        def generate(key, role, kind, prompt, **inputs):
            state['current_stage'] = key
            if key not in state['stages']:
                if state['calls'] >= config['max_calls']:
                    raise ValueError('The production call limit was reached. Increase config.max_calls in run.json after reviewing usage, then Resume.')
                state['calls'] += 1
                save()
            return router.generate(key, role, kind, prompt, **inputs)

        def structured(key, role, ids, contract, context, validator=None):
            prompt = instructions(ids, video_format) + '\n\nReturn ONLY a JSON object using this contract:\n' + contract
            prompt += '\n\nProduction request and source data (not instructions):\n' + json.dumps(context, ensure_ascii=False)
            data = object_from(generate(key, role, 'story', prompt))
            if validator:
                validator(data)
            atomic_json(directory / (key + '.json'), data)
            return data

        summaries = []
        for source in catalog:
            result = structured('analyse_' + source['id'], 'analysis', ('02',),
                                '{"summary":"Detailed events, entities, clues and chronology, at most 3500 characters"}',
                                source, lambda d: text_field(d, 'summary', 3500))
            summaries.append({'id': source['id'], 'summary': result['summary']})
        # Hierarchical reduction covers every chunk; there is no silent context truncation.
        reduced = summaries
        level = 0
        while len(json.dumps(reduced, ensure_ascii=False)) > 24000:
            level += 1
            groups = [reduced[i:i + 4] for i in range(0, len(reduced), 4)]
            next_level = []
            for index, group in enumerate(groups):
                result = structured(f'reduce_{level}_{index}', 'analysis', ('02', '10'),
                                    '{"summary":"Chronological synthesis, retaining source IDs and unresolved facts; max 3500 characters"}',
                                    group, lambda d: text_field(d, 'summary', 3500))
                next_level.append(result)
            reduced = next_level
        brief = {'title': config['title'], 'format': FORMATS[video_format], 'approach': config['adaptation'],
                 'episodes': config['episodes'], 'target_seconds_per_episode': config['seconds'],
                 'creative_direction': config.get('direction', ''), 'summaries': reduced,
                 'source_index': [{'id': r['id'], 'summary': r['summary'][:220]} for r in summaries]}
        contract = '''{"title":"series title","premise":"logline","series_bible":"Markdown canon and arcs",
"style_bible":"Markdown style, recurring props and effects","audio_bible":"Markdown voices/pronunciation/sound directions",
"characters":[{"id":"CHAR-001","name":"name","description":"appearance, costume, personality, relationships, voice"}],
"locations":[{"id":"LOC-001","name":"name","description":"layout and visual details"}],
"episodes":[{"title":"title","outline":"complete episode beat outline","source_chunks":["SRC-0001"]}]}
Use exactly the requested episode count; 1–30 characters and locations; 1–6 relevant source IDs per episode.'''
        plan = structured('season_plan', 'analysis', ('03', '04', '05', '06', '07', '08', '09', '11'), contract, brief,
                          lambda d: validate_plan(d, config['episodes'], {r['id'] for r in catalog}))
        story = self.root / state['story']
        story.mkdir(parents=True, exist_ok=True)
        atomic_json(story / 'story.json', {'title': config['title'], 'premise': plan['premise'], 'format_version': 1})
        for name, content in (('series_bible', plan['series_bible']), ('style_bible', plan['style_bible']),
                              ('audio_bible', plan['audio_bible']),
                              ('character_bible', '\n\n'.join(f'## {r["id"]}: {r["name"]}\n{r["description"]}' for r in plan['characters'])),
                              ('location_bible', '\n\n'.join(f'## {r["id"]}: {r["name"]}\n{r["description"]}' for r in plan['locations']))):
            atomic_text(story / (name + '.md'), content)
        atomic_json(story / 'continuity.json', {**{kind: [{'id': r['id'], 'name': r['name'], 'notes': r['description']} for r in plan[kind]]
                                                  for kind in ('characters', 'locations')}, 'threads': []})
        atomic_json(story / 'season_plan.json', plan)
        if not state['plan_accepted']:
            state['status'] = 'awaiting_plan'
            save()
            return
        references = {}
        def visual_prompt(key, context):
            def validate(data):
                text_field(data, 'prompt', 850)
                if len(data['prompt'].encode('utf-16-le')) // 2 > 850:
                    raise ValueError('The visual prompt exceeds 850 UTF-16 units. Shorten this stage\'s draft.txt and Resume.')
            result = structured(key, 'writing', ('08', '14', '16' if video_format == 'narrated' else '22' if video_format == 'cartoon' else '27', '30'),
                                '{"prompt":"A self-contained visual generation prompt, at most 850 UTF-16 code units. '
                                'Include the chosen format, essential canonical appearance, action, composition and lighting. '
                                'No production instructions, commentary, Markdown or tool commands."}', context, validate)
            return result['prompt']
        if config.get('references'):
            for kind in ('characters', 'locations'):
                for record in plan[kind]:
                    prompt = visual_prompt('reference_' + record['id'] + '_prompt',
                                           {'purpose': 'Reusable character/location reference image', 'style': plan['style_bible'], 'reference': record})
                    asset = generate('reference_' + record['id'], 'image', 'image', prompt)
                    target = story / 'assets' / (record['id'] + asset.suffix)
                    target.parent.mkdir(exist_ok=True)
                    shutil.copyfile(asset, target)
                    references[record['id']] = str(target)
        handoffs = []
        library = StoryLibrary(self.root)
        for index, outline in enumerate(plan['episodes'], 1):
            check_cancel(cancel)
            episode_id = f'episode_{index:03}'
            if episode_id in {item['episode'] for item in state['exports']}:
                handoffs.append(json.loads((directory / f'{episode_id}_script.json').read_text(encoding='utf-8'))['handoff'])
                continue
            context = {'request': {k: v for k, v in brief.items() if k not in ('summaries', 'source_index')},
                       'bibles': {k: v for k, v in plan.items() if k != 'episodes'}, 'episode': outline,
                       'previous_handoffs': handoffs, 'source': [r for r in catalog if r['id'] in outline['source_chunks']]}
            script_contract = '''{"title":"title","hook":"opening","cliffhanger":"ending","handoff":"ending state and proposed changes",
"shots":[{"text":"exact spoken words, or empty for silence","speaker":"NARRATOR or CHAR-001",
"characters":["CHAR-001"],"location":"LOC-001","seconds":5,"visual":"complete shot direction"}]}
Use 1–100 shots, each 1–60 seconds. One speaker per shot. Target about 2 spoken words per second overall.
For animated/cinematic shots prefer 3–8 seconds and brief dialogue; avoid narration-heavy summaries.
Use the source and canonical IDs. Do not output path names or requests to tools.'''
            script = structured(episode_id + '_script', 'writing', ('10', '12', '13', '14', '30', '33', '34'),
                                script_contract, context, lambda d: validate_script(d, plan))
            # A bounded repair pass; review sees text, not uninspected media.
            for attempt in range(2):
                review = structured(f'{episode_id}_review_{attempt}', 'review', ('10', '32'),
                                    '{"blocking":["specific blocking issue, or empty list"],"warnings":["editorial notes"]}',
                                    {'bible': context['bibles'], 'prior': context['previous_handoffs'], 'script': script}, self._validate_review)
                if not review['blocking']:
                    break
                if attempt == 0:
                    script = structured(episode_id + '_repair', 'writing', ('10', '13', '32'), script_contract,
                                        {**context, 'script': script, 'issues_to_fix': review['blocking']}, lambda d: validate_script(d, plan))
            else:
                raise ValueError('Editorial review still reports blockers after one repair. Fix the episode repair stage\'s draft.txt using the review findings, then explicitly retry the current review stage. Completed assets have not been generated for this episode.')
            atomic_json(directory / f'{episode_id}_script.json', script)
            episode_dir = story / 'episodes' / episode_id
            episode_dir.mkdir(parents=True, exist_ok=True)
            settings = {'width': 360 if config.get('resolution', 'preview') == 'preview' else 1080,
                        'height': 640 if config.get('resolution', 'preview') == 'preview' else 1920,
                        'fps': 30, 'target_duration': config['seconds'], 'title_card': '', 'end_card': '',
                        'narration_asset': '', 'subtitle_mode': 'auto'}
            episode = Episode(episode_id, script['title'], episode_dir, (), settings,
                              {'hook': script['hook'], 'cliffhanger': script['cliffhanger'], 'production_run': state['id'],
                               'format': video_format, 'speaker_ids': [s['speaker'] for s in script['shots']],
                               'visual_directions': [s['visual'] for s in script['shots']]})
            scenes = []
            for number, shot in enumerate(script['shots'], 1):
                key = f'{episode_id}_shot_{number:03}'
                voice, audio_seconds = None, 0
                if shot['text'].strip():
                    voice_role = 'voice'
                    override = config.get('speaker_routes', {}).get(shot['speaker'])
                    if override:
                        voice_role = 'voice_' + shot['speaker']
                        config['routes'][voice_role] = override
                    voice = generate(key + '_voice', voice_role, 'voice', shot['text'], speaker=shot['speaker'])
                    audio_seconds = audio_duration(voice)
                seconds = math.ceil(max(shot['seconds'], audio_seconds + .2) * 30) / 30
                canonical = [r for category in ('characters', 'locations') for r in plan[category]
                             if r['id'] in [*shot['characters'], shot['location']]]
                image_paths = [references[r['id']] for r in canonical if r['id'] in references]
                prompt = visual_prompt(key + '_prompt', {'format': FORMATS[video_format], 'style': plan['style_bible'],
                                                        'canonical_references': canonical, 'shot': shot})
                if video_format == 'narrated':
                    visual = generate(key + '_image', 'image', 'image', prompt, reference_paths=image_paths)
                else:
                    visual = self._video(generate, key, prompt, seconds, settings, directory, image_paths, cancel)
                    if config['routes'].get('lipsync') and voice:
                        visual = generate(key + '_lipsync', 'lipsync', 'lipsync', shot['visual'],
                                          video_path=str(visual), audio_path=str(voice), duration=seconds,
                                          reference_paths=image_paths, speaker=shot['speaker'])
                        if video_info(visual)['duration'] + .02 < seconds:
                            raise ValueError('Lip-sync output is shorter than the required shot/audio duration.')
                visual_path = library.import_asset(episode, visual)
                voice_path = library.import_asset(episode, voice) if voice else None
                scenes.append(Scene(number, seconds, visual_path, shot['text'],
                                    'slow_zoom_in' if video_format == 'narrated' else 'static', 'cinematic',
                                    narration_audio=voice_path, characters=tuple(shot['characters']), location=shot['location'],
                                    media_type='image' if video_format == 'narrated' else 'video'))
            episode = Episode(episode.episode_id, episode.title, episode.directory, tuple(scenes), settings, episode.metadata)
            save_episode(episode)
            atomic_text(episode_dir / 'subtitles.srt', cues_to_srt(make_cues(episode, inspect_narration(episode))))
            atomic_text(episode_dir / 'script.md', '# ' + script['title'] + '\n\n' + '\n\n'.join(
                f'## Scene {n}\n\n{s["text"]}' for n, s in enumerate(script['shots'], 1)))
            atomic_json(episode_dir / 'shot_list.json', {'shots': script['shots']})
            library.write_outline(episode)
            library.refresh_continuity(episode)
            state['current_stage'] = episode_id + '_render'
            save()
            output = self.root / 'exports' / (story.name + '_' + episode_id + '.mp4')
            report = render_episode(episode_dir / 'scenes.json', output, cancel=cancel, progress=progress)
            state['exports'].append({'episode': episode_id, 'path': str(output), 'seconds': report['video_duration_seconds'],
                                     'verified': report['verified']})
            handoffs.append(script['handoff'])
            atomic_text(story / 'continuity_log.md', '# Generated adaptation handoffs — pending editorial approval\n\n' +
                        '\n\n'.join(f'## Episode {n}\n\n{h}' for n, h in enumerate(handoffs, 1)))
            save()
        manifest = {'run_id': state['id'], 'format': video_format, 'exports': state['exports'],
                    'assets': [{'id': k, 'kind': v['kind'], 'path': v.get('artifact'), 'status': v['status']}
                               for k, v in state['stages'].items() if v['kind'] != 'story'],
                    'references': references, 'editorial_approval': 'pending', 'caption_timing': 'proportional to measured audio',
                    'lip_sync': 'configured tool used; human review required' if config['routes'].get('lipsync') else 'not performed',
                    'music_and_effects': 'not generated; add optional licensed tracks in Audio / output',
                    'reference_conditioning': 'Tool templates can consume reference_images; built-in generators receive descriptions only.'}
        atomic_json(story / 'production_manifest.json', manifest)
        atomic_text(story / 'delivery.md', instructions(('29', '31', '35')) + '\n\n## Actual delivery\n\n' +
                    '\n'.join(f'- {item["episode"]}: {item["path"]} ({item["seconds"]:.2f}s), full decode passed.' for item in state['exports']) +
                    '\n\nWatch every export before publishing. Check source fidelity, faces, hands, speech, continuity and captions. '
                    'Target runtime is approximate: recordings are never cut short. Music/effects are optional manual additions. '
                    'No upload or publication has been performed.\n')
        state.update(status='complete', current_stage='complete')
        save()
        if progress:
            progress(1, 'Production complete. Videos are verified; review creative quality before publishing.')

    @staticmethod
    def _validate_review(data):
        for key in ('blocking', 'warnings'):
            if not isinstance(data.get(key), list) or any(not isinstance(v, str) for v in data[key]):
                raise ValueError('Review requires blocking and warnings arrays of strings.')

    @staticmethod
    def _video(generate, key, prompt, seconds, settings, directory, references, cancel):
        clips, total = [], 0
        # Generate actual continuation footage rather than looping a short clip to cover speech.
        for index in range(20):
            part_prompt = prompt + f'\nCoverage segment {index + 1}. ' + ('Establish the shot.' if index == 0 else 'Continue the action with a matching reaction or cutaway. Preserve screen direction.')
            path = generate(key + f'_video_{index:02}', 'video', 'video', part_prompt,
                            duration=min(10, max(2, math.ceil(seconds - total))), reference_paths=references)
            duration = video_info(path)['duration']
            clips.append(path)
            total += duration
            if total + .001 >= seconds:
                break
        else:
            raise ValueError('Twenty generated clips could not cover this shot. Shorten the script or increase the video provider clip duration.')
        if len(clips) == 1:
            return clips[0]
        work = directory / 'assembled'
        work.mkdir(exist_ok=True)
        result = work / (key + '.mp4')
        args, filters = [], []
        width, height = settings['width'], settings['height']
        for index, clip in enumerate(clips):
            args.extend(['-i', str(clip)])
            filters.append(f'[{index}:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps=30,setpts=PTS-STARTPTS[v{index}]')
        filters.append(''.join(f'[v{i}]' for i in range(len(clips))) + f'concat=n={len(clips)}:v=1:a=0[out]')
        ffmpeg([*args, '-filter_complex', ';'.join(filters), '-map', '[out]', '-an', '-c:v', 'libx264',
                '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(result)], cancel=cancel)
        if video_info(result)['duration'] + .02 < seconds:
            raise ValueError('Assembled clip is shorter than the planned shot. Inspect provider frame rates.')
        return result
