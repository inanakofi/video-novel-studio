"""Opt-in live checks. Reads a local key without printing or exporting it."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.connections.config import Connection, ConnectionStore, SecretStore
from src.connections.generation import GenerationService, prompt_for
from src.connections.models import filter_models
from src.media import atomic_json
from src.production.manuscript import extract
from src.production.runner import ProductionRunner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--key-file', default='temp_api.txt')
    parser.add_argument('--manuscript', required=True)
    parser.add_argument('--pilot', action='store_true')
    parser.add_argument('--text-model')
    parser.add_argument('--image-model')
    args = parser.parse_args()
    match = re.search(r'sk-or-v1-[A-Za-z0-9_-]+', Path(args.key_file).read_text(encoding='utf-8-sig'))
    if not match:
        raise ValueError('No OpenRouter key found in the supplied key file.')
    store, secrets = ConnectionStore(ROOT), SecretStore()
    mode, connections = store.load()
    connection = next((c for c in connections if c.name == 'OpenRouter (test key)' and c.provider == 'openrouter'), None)
    connection = connection or replace(Connection.preset('openrouter'), name='OpenRouter (test key)')
    connection = replace(connection, enabled=True)
    secrets.put(connection.id, match.group(0))
    connections = [c for c in connections if c.id != connection.id] + [connection]
    store.save('online', connections)
    service = GenerationService(ROOT, secrets)
    records = service.discover(connection.id)['catalog']
    source = extract(args.manuscript)
    candidates = filter_models(records, 'story', free=True)
    if not candidates:
        raise ValueError('No free text-output models are available in the live catalog.')
    preferred = ['google/gemma-4-31b-it:free', 'poolside/laguna-s-2.1:free', 'openrouter/free']
    text_model = args.text_model or next((m for m in preferred if any(r['id'] == m for r in candidates)), candidates[0]['id'])
    if text_model not in {r['id'] for r in candidates}:
        raise ValueError('The selected text model is not listed as free.')
    choices = {'story': text_model}
    for kind in ('image', 'voice'):
        available = filter_models(records, kind, free=True)
        # The built-in smoke check has no image/audio reference input.
        available = [r for r in available if 'text' in r.get('input_modalities', [])]
        preferred_image = 'inclusionai/ming-image-0.1-design'
        choices[kind] = (next((r['id'] for r in available if r['id'] == preferred_image), available[0]['id'])
                         if kind == 'image' and available else available[0]['id'] if available else None)
    if args.image_model:
        if args.image_model not in {r['id'] for r in filter_models(records, 'image', free=True)}:
            raise ValueError('The selected image model is not listed as free.')
        choices['image'] = args.image_model
    report = {'connection_id': connection.id, 'manuscript': Path(args.manuscript).name,
              'catalog_models': len(records), 'selected_free_models': choices, 'checks': {}}
    report_path = ROOT / ('exports/verification/openrouter-pilot-live.json' if args.pilot else 'exports/verification/openrouter-models-live.json')
    atomic_json(report_path, report)
    if args.pilot:
        cfg = {'title': "The CEO's Hidden Love — OpenRouter pilot", 'format': 'narrated', 'adaptation': 'faithful',
               'episodes': 1, 'seconds': 15, 'max_calls': 24, 'resolution': 'preview', 'references': False,
               'direction': 'A short Ghanaian romance pilot in English. Use exactly two shots and a single narrator. '
                            'Each shot has one short spoken sentence, about 10 words. Show the rainy first meeting in Osu. '
                            'Return concise JSON matching each requested contract.',
               'routes': {r: connection.id for r in ('analysis', 'writing', 'review', 'image', 'voice')},
               'models': {'analysis': text_model, 'writing': text_model, 'review': text_model,
                          'image': choices['image'], 'voice': choices['voice']}}
        if not choices['image'] or not choices['voice']:
            raise ValueError('A free image and speech model are required for this live pilot.')
        runner = ProductionRunner(ROOT, service)
        state = runner.create(args.manuscript, cfg)
        report['production_run'] = state['id']
        atomic_json(report_path, report)
        print('pilot_run:', state['id'], flush=True)
        try:
            state = runner.run(state['id'], progress=lambda _, message: print(message, flush=True))
            report['pilot_status'] = state['status']
            report['exports'] = state['exports']
        except Exception as error:
            report['pilot_error'] = str(error)
            raise
        finally:
            atomic_json(report_path, report)
        return
    prompts = {
        'story': prompt_for('script', 'Adapt this manuscript into two short scenes, about 15 seconds total. '
                            'Set the opening in rainy Osu, Ghana. Preserve the named adults and the central plot.', source),
        'image': 'Vertical illustration for a Ghanaian romance novel. Rainy evening near a waakye stall in Osu, Accra. '
                 'A 25-year-old Ghanaian woman offers transport money to a 32-year-old Ghanaian man. '
                 'Warm stall light, rain reflections, modest contemporary clothing, no text.',
        'voice': 'One rainy evening in Osu, Akosua gave a stranger her last money for transport.'}
    for kind, model in choices.items():
        if not model:
            report['checks'][kind] = {'status': 'unavailable', 'reason': 'No free output model in the live catalog.'}
            continue
        try:
            print('testing:', kind, model, flush=True)
            job = service.run(connection.id, 'script' if kind == 'story' else kind, prompts[kind], model=model)
            report['checks'][kind] = {'status': job['status'], 'model': model, 'job_id': job['id'],
                                     'artifacts': job['artifacts'], 'usage': job.get('usage', {}),
                                     **({'script_valid': job.get('script_valid')} if kind == 'story' else {})}
            print('result:', kind, job['status'], flush=True)
        except Exception as error:
            report['checks'][kind] = {'status': 'failed', 'model': model, 'error': str(error)}
            print('result:', kind, str(error), flush=True)
        atomic_json(report_path, report)


if __name__ == '__main__':
    main()
