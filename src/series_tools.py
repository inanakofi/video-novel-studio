"""Reusable series presentation and explicit, user-authored continuity records."""
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from .media import atomic_json
from .settings import settings_for


STYLE_KEYS = ('font', 'font_size', 'margin_bottom', 'margin_left', 'margin_right',
              'outline', 'shadow', 'wrap_chars', 'caption_words', 'caption_color',
              'card_background', 'card_accent', 'card_text', 'music_asset', 'music_volume',
              'narration_volume', 'duck_music', 'title_duration', 'end_duration',
              'width', 'height', 'fps', 'target_duration')


def load_style(story):
    path = story / 'style.json'
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('settings'), dict):
        raise ValueError('Series style must contain a settings object.')
    if data['settings'].keys() - set(STYLE_KEYS):
        raise ValueError('Series style contains unsupported settings.')
    if not isinstance(data.get('voice', ''), str) or type(data.get('voice_rate', -1)) is not int or not -10 <= data.get('voice_rate', -1) <= 10:
        raise ValueError('Series voice name/rate is invalid.')
    if data.get('subtitle_style', 'cinematic') not in ('cinematic', 'standard'):
        raise ValueError('Invalid series caption preset.')
    return data


def save_style(episode, *, voice='', rate=-1, subtitle_style='cinematic',
               title_template='{series} · Episode {episode}', end_template='To be continued'):
    if subtitle_style not in ('cinematic', 'standard') or type(rate) is not int or not -10 <= rate <= 10:
        raise ValueError('Invalid series voice speed or subtitle preset.')
    for template in (title_template, end_template):
        expand_card(template, series='Series', episode='001', title='Title')
    story = episode.directory.parent.parent
    settings = {key: settings_for(episode)[key] for key in STYLE_KEYS}
    if settings['music_asset']:
        asset = episode.resolve_asset(settings['music_asset'])
        if not asset.is_file():
            raise ValueError('Import the series music before saving it as a default.')
        from .render_cache import digest
        directory = story / 'assets' / 'music'
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f'{asset.stem}-{digest(asset)[:12]}{asset.suffix}'
        if not target.is_file():
            fd, name = tempfile.mkstemp(prefix='.style-music-', dir=directory)
            os.close(fd)
            try:
                shutil.copyfile(asset, name)
                os.replace(name, target)
            finally:
                Path(name).unlink(missing_ok=True)
        settings['music_asset'] = target.relative_to(story).as_posix()
    data = {'version': 1, 'settings': settings, 'voice': voice, 'voice_rate': rate,
            'subtitle_style': subtitle_style, 'title_template': title_template, 'end_template': end_template}
    atomic_json(story / 'style.json', data)
    return data


def expand_card(template, **values):
    if not isinstance(template, str):
        raise ValueError('Card template must be text.')
    fields = re.findall(r'\{([^{}]+)\}', template)
    if set(fields) - {'series', 'episode', 'title'}:
        raise ValueError('Card templates support only {series}, {episode} and {title}.')
    for key, value in values.items():
        template = template.replace('{' + key + '}', str(value))
    if '{' in template or '}' in template:
        raise ValueError('Unmatched braces in card template.')
    return template


def apply_style(episode, series_title):
    story = episode.directory.parent.parent
    profile = load_style(story)
    if not profile:
        return episode
    settings = dict(profile['settings'])
    if settings.get('music_asset'):
        settings['music_asset'] = Path(os.path.relpath(story / settings['music_asset'], episode.directory)).as_posix()
    values = {'series': series_title, 'episode': episode.episode_id.removeprefix('episode_'), 'title': episode.title}
    settings.update({'title_card': expand_card(profile.get('title_template', ''), **values),
                     'end_card': expand_card(profile.get('end_template', ''), **values)})
    scenes = tuple(replace(s, subtitle_style=profile.get('subtitle_style', 'cinematic')) for s in episode.scenes)
    updated = replace(episode, settings={**episode.settings, **settings}, scenes=scenes,
                      metadata={**episode.metadata, 'voice': profile.get('voice', ''), 'voice_rate': profile.get('voice_rate', -1)})
    settings_for(updated)
    return updated


def load_continuity(story):
    path = story / 'continuity.json'
    data = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {'characters': [], 'locations': [], 'threads': []}
    validate_continuity(data)
    return data


def validate_continuity(data):
    if not isinstance(data, dict):
        raise ValueError('Continuity must be an object.')
    for category in ('characters', 'locations', 'threads'):
        rows = data.get(category)
        if not isinstance(rows, list):
            raise ValueError(f'Continuity {category} must be a list.')
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not re.fullmatch(r'[\w-]+', row['id']):
                raise ValueError(f'{category}: use a nonempty ID with letters, digits, underscores or hyphens.')
            if row['id'] in seen:
                raise ValueError(f'{category}: duplicate ID {row["id"]}.')
            seen.add(row['id'])
            if not isinstance(row.get('name'), str) or not row['name'].strip():
                raise ValueError(f'{category}: enter a name/title.')
            if any(not isinstance(value, str) for value in row.values()):
                raise ValueError(f'{category}: all fields must be text.')
            if category == 'threads' and row.get('status') not in ('open', 'resolved'):
                raise ValueError('Plot thread status must be open or resolved.')
            if category == 'threads':
                for key in ('opened_episode', 'resolved_episode'):
                    if row.get(key) and not re.fullmatch(r'episode_\d+', row[key]):
                        raise ValueError('Thread episode references use episode_001, episode_002, etc.')
                if row.get('status') == 'resolved' and not row.get('resolved_episode'):
                    raise ValueError('A resolved thread needs its resolution episode.')
                if row.get('opened_episode') and row.get('resolved_episode'):
                    if int(row['resolved_episode'].split('_')[-1]) < int(row['opened_episode'].split('_')[-1]):
                        raise ValueError('A plot thread cannot resolve before it opens.')


def save_continuity(story, data):
    validate_continuity(data)
    atomic_json(story / 'continuity.json', data)


def continuity_notes(episode):
    data = load_continuity(episode.directory.parent.parent)
    text = '\n\n## Open plot threads\n\n'
    number = int(episode.episode_id.split('_')[-1]) if episode.episode_id.split('_')[-1].isdigit() else 0
    active = []
    for thread in data['threads']:
        opened = int(thread['opened_episode'].split('_')[-1]) if thread.get('opened_episode') else 0
        resolved = int(thread['resolved_episode'].split('_')[-1]) if thread.get('resolved_episode') else float('inf')
        if opened <= number and number < resolved:
            active.append(f'- {thread["name"]}: {thread.get("notes", "")}')
    text += '\n'.join(active) or 'No open threads recorded for this episode.'
    for category, ids in (('characters', {c for s in episode.scenes for c in s.characters}),
                          ('locations', {s.location for s in episode.scenes if s.location})):
        text += f'\n\n## Linked {category}\n\n'
        text += '\n'.join(f'- {row["name"]}: {row.get("notes", "")}' for row in data[category] if row['id'] in ids) or 'None linked.'
    return text


def reference_errors(episode):
    data = load_continuity(episode.directory.parent.parent)
    characters = {row['id'] for row in data['characters']}
    locations = {row['id'] for row in data['locations']}
    errors = []
    for scene in episode.scenes:
        for name in set(scene.characters) - characters:
            errors.append(f'Scene {scene.scene_id}: unknown character reference {name}.')
        if scene.location and scene.location not in locations:
            errors.append(f'Scene {scene.scene_id}: unknown location reference {scene.location}.')
    return errors
