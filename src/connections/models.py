"""Cached platform catalogs and task model selection; never stores credentials."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import hashlib
from pathlib import Path

from ..media import atomic_json


TASK_OUTPUTS = {'story': 'text', 'script': 'text', 'image': 'image', 'voice': 'speech', 'video': 'video', 'lipsync': 'video'}


def is_free(record):
    if record['id'].endswith(':free'):
        return True
    prices = record.get('pricing', {})
    outputs = record.get('output_modalities', [])
    # Media prices are separate from prompt/completion prices. Unknown is not free.
    if 'video' in outputs and not record.get('pricing_skus'):
        return False
    if 'image' in outputs and not any(k in prices for k in ('image_output', 'image_token')):
        return False
    if any(m in outputs for m in ('audio', 'speech')) and not any(
            k in prices for k in ('audio_output', 'speech', 'characters')):
        return False
    prices = {**prices, **record.get('pricing_skus', {})}
    if not prices:
        return False
    try:
        return all(Decimal(str(v)) == 0 for v in prices.values() if v is not None) and any(v is not None for v in prices.values())
    except (InvalidOperation, ValueError, TypeError):
        return False


def normalize_model(record, provider):
    if not isinstance(record, dict):
        return None
    model_id = record.get('id') or record.get('model_id') or record.get('name')
    if not isinstance(model_id, str) or not model_id.strip():
        return None
    architecture = record.get('architecture')
    architecture = architecture if isinstance(architecture, dict) else {}
    outputs = architecture.get('output_modalities', record.get('output_modalities'))
    # Most compatible/local catalogs don't advertise modalities. Permit manual choices.
    known = isinstance(outputs, list) and all(isinstance(v, str) for v in outputs)
    result = {'id': model_id.strip(), 'name': record.get('name') if isinstance(record.get('name'), str) else model_id,
              'output_modalities': outputs if known else [],
              'input_modalities': architecture.get('input_modalities', ['text']),
              'modalities_known': known, 'pricing': record.get('pricing') if isinstance(record.get('pricing'), dict) else {},
              'pricing_skus': record.get('pricing_skus') if isinstance(record.get('pricing_skus'), dict) else {},
              'open_weights': bool(record.get('hugging_face_id')),
              'local': provider == 'ollama', 'voices': record.get('supported_voices') or [],
              'context_length': record.get('context_length')}
    if isinstance(record.get('tasks'), list):
        result['tasks'] = [k for k in record['tasks'] if isinstance(k, str)]
    result['free'] = provider == 'ollama' or is_free(result)
    return result


def supports_model(record, kind):
    if 'tasks' in record:
        return kind in record['tasks']
    output = TASK_OUTPUTS.get(kind)
    return not record.get('modalities_known', True) or output in record.get('output_modalities', [])


def filter_models(records, kind=None, *, free=False, open_weights=False):
    return [r for r in records if (not kind or supports_model(r, kind))
            and (not free or r.get('free'))
            and (not open_weights or r.get('open_weights') or r.get('local'))]


class ModelCatalog:
    def __init__(self, root):
        self.path = Path(root) / '.studio_models.json'

    @staticmethod
    def key(connection):
        key = connection.provider + ':' + connection.base_url.rstrip('/')
        # OpenRouter's public list is shared; private catalogs can differ by key.
        if connection.provider != 'openrouter':
            key += ':' + connection.id
        if connection.provider == 'comfyui':
            key += ':' + hashlib.sha256(json.dumps(connection.options.get('workflow', {}), sort_keys=True).encode()).hexdigest()
        return key

    def _load(self):
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def records(self, connection):
        entry = self._load().get(self.key(connection), {})
        records = entry.get('models', []) if isinstance(entry, dict) else []
        if not isinstance(records, list):
            return []
        valid = [r for r in records if isinstance(r, dict) and isinstance(r.get('id'), str)
                 and r['id'].strip() and isinstance(r.get('output_modalities'), list)
                 and all(isinstance(m, str) for m in r['output_modalities'])
                 and isinstance(r.get('name', ''), str)
                 and ('tasks' not in r or isinstance(r['tasks'], list))]
        # Tools with no standard discovery protocol can advertise their exact IDs.
        configured = connection.options.get('models', [])
        if isinstance(configured, list):
            valid += [r for item in configured
                      if (r := normalize_model({'id': item} if isinstance(item, str) else item, connection.provider))]
        return list({r['id']: r for r in valid}.values())

    def save(self, connection, records):
        data = self._load()
        data[self.key(connection)] = {'updated_utc': datetime.now(timezone.utc).isoformat(), 'models': records}
        atomic_json(self.path, data)

    def validate_selection(self, connection, kind):
        record = next((r for r in self.records(connection) if r['id'] == connection.model), None)
        if record and not supports_model(record, kind):
            raise ValueError(f'{connection.model} cannot generate {TASK_OUTPUTS.get(kind, kind)}. Choose a model with the matching output capability.')


def effective_model(config, role, connection):
    """Old route IDs remain valid; task overrides never mutate the saved connection."""
    value = config.get('models', {}).get(role, '')
    if role.startswith('voice_'):
        speaker = role.removeprefix('voice_')
        value = config.get('speaker_models', {}).get(speaker, '')
        if not value and config.get('speaker_routes', {}).get(speaker) == config['routes'].get('voice'):
            value = config.get('models', {}).get('voice', '')
    return value or connection.model
