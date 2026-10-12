"""Read-only provider catalogs. A failed refresh never replaces the last good list."""
from urllib.parse import urlencode

from .models import normalize_model
from .transport import ConnectionError


# Runway exposes no model-list endpoint. IDs from its official Python SDK's
# text_to_video_create_params.py, checked 2026-10-12. Manual IDs remain supported.
RUNWAY_VIDEO_MODELS = (
    'gen4.5', 'veo3.1', 'veo3.1_fast', 'hailuo3', 'happyhorse_1_0',
    'seedance2', 'seedance2_fast', 'seedance2_mini', 'gemini_omni_flash',
    'seedance2_5', 'grok_imagine_1_5', 'wan3', 'gemini_omni_flash_1.1',
    'wan3_prime', 'h3_max', 'grok_imagine_1_5_lite',
)


def model_list(payload, field=None):
    values = payload.get(field) if field and isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise ConnectionError('Provider did not return a model list; the previous catalog was kept.')
    return values


def comfy_models(info, workflow):
    """Match the workflow's model inputs, never offer VAE/LoRA IDs as checkpoints."""
    if not isinstance(info, dict) or not isinstance(workflow, dict):
        raise ConnectionError('ComfyUI returned invalid node metadata or the workflow is invalid.')
    choices = []
    for node in workflow.values():
        if not isinstance(node, dict) or not isinstance(node.get('inputs'), dict):
            continue
        schema = info.get(node.get('class_type'), {})
        schema = schema.get('input', {}) if isinstance(schema, dict) else {}
        if not isinstance(schema, dict):
            raise ConnectionError('ComfyUI returned invalid input metadata; the previous catalog was kept.')
        for name, value in node['inputs'].items():
            if not isinstance(value, str) or '{{model}}' not in value:
                continue
            definition = next((group[name] for group in schema.values()
                               if isinstance(group, dict) and name in group), None)
            if not isinstance(definition, list) or not definition or not isinstance(definition[0], list):
                raise ConnectionError(f'ComfyUI cannot list choices for {name}; enter its model ID manually.')
            prefix, suffix = value.split('{{model}}', 1)
            available = set()
            for item in definition[0]:
                if isinstance(item, str) and item.startswith(prefix) and item.endswith(suffix):
                    end = len(item) - len(suffix) if suffix else len(item)
                    available.add(item[len(prefix):end])
            choices.append(available)
    # One override must satisfy every substituted model input in this graph.
    return [{'id': item} for item in sorted(set.intersection(*choices))] if choices else []


def discover_models(transport):
    connection = transport.connection
    provider = connection.provider
    status = 'Endpoint responded; generation not tested'
    if provider in ('openrouter', 'openai_compatible', 'ollama'):
        path = {'openrouter': '/models?output_modalities=all',
                'openai_compatible': '/models', 'ollama': '/api/tags'}[provider]
        result = transport.request('GET', path)
        field = 'models' if provider == 'ollama' else 'data'
        raw = list(model_list(result, field))
        page, seen = result, set()
        # Some compatible servers paginate with OpenAI-style after cursors.
        while isinstance(page, dict) and page.get('has_more'):
            cursor = page.get('last_id')
            items = model_list(page, field)
            if not cursor and items and isinstance(items[-1], dict):
                cursor = items[-1].get('id')
            if not isinstance(cursor, str) or not cursor or cursor in seen or len(seen) >= 1000:
                raise ConnectionError('Model pagination did not advance; the previous catalog was kept.')
            seen.add(cursor)
            page = transport.request('GET', path + ('&' if '?' in path else '?') + urlencode({'after': cursor}))
            raw.extend(model_list(page, field))
        result = {**result, field: raw}
    elif provider == 'elevenlabs':
        models = transport.request('GET', '/models')
        raw = [{**item, 'id': item.get('model_id'), 'output_modalities': ['speech']}
               for item in model_list(models) if isinstance(item, dict) and item.get('can_do_text_to_speech') is True]
        result = {'models': models}
        # Voice-list permissions can differ from model-list permissions.
        try:
            result['voices'] = transport.request('GET', '/voices')
        except ConnectionError as error:
            result['voice_warning'] = str(error)
            status += '; voice discovery failed (see details)'
    elif provider == 'comfyui':
        result = transport.request('GET', '/object_info')
        raw = comfy_models(result, connection.options.get('workflow', {}))
        status += '; models match the workflow’s {{model}} inputs'
        if not raw:
            status += '; no selectable model input found, check the workflow'
    elif provider == 'runway':
        result = transport.request('GET', '/organization')
        raw = [{'id': name, 'output_modalities': ['video']} for name in RUNWAY_VIDEO_MODELS]
        status += '; Runway model suggestions from the official SDK (2026-10-12), account access not verified'
    else:
        raise ValueError('This tool has no standard model catalog. Configure options.models or enter an ID.')
    records = [r for item in raw if (r := normalize_model(item, provider))]
    if raw and not records:
        raise ConnectionError('No valid model records were returned; the previous catalog was kept.')
    records = list({r['id']: r for r in records}.values())
    return {'status': status, 'models': [r['id'] for r in records], 'catalog': records, 'response': result}
