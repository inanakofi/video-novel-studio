"""Validated offline render and caption settings."""
import copy
import math


DEFAULTS = {
    'width': 1080, 'height': 1920, 'fps': 30, 'crf': 20, 'preset': 'veryfast',
    'target_duration': 75.0, 'title_card': '', 'title_duration': 2.0,
    'end_card': '', 'end_duration': 2.0, 'narration_asset': 'narration.wav',
    'narration_volume': 1.0, 'music_asset': '', 'music_volume': 0.16,
    'duck_music': True, 'sound_effects': [], 'subtitle_mode': 'auto',
    'font': 'Arial', 'font_size': 58, 'margin_bottom': 360,
    'margin_left': 90, 'margin_right': 180, 'outline': 3, 'shadow': 1,
    'wrap_chars': 30, 'caption_words': 9,
    'caption_color': '#FFFFFF', 'card_background': '#111B2D',
    'card_accent': '#61D7BB', 'card_text': '#F5F3EE',
    'publish_min_duration': 60.0, 'publish_max_duration': 90.0,
    'pause_warning_seconds': 1.5,
}


def settings_for(episode) -> dict:
    result = copy.deepcopy(DEFAULTS)
    unknown = episode.settings.keys() - DEFAULTS.keys()
    if unknown:
        raise ValueError('Unknown render settings: ' + ', '.join(sorted(unknown)))
    result.update(episode.settings)
    for key in ('width', 'height', 'fps', 'crf', 'font_size', 'margin_bottom',
                'margin_left', 'margin_right', 'outline', 'shadow', 'wrap_chars', 'caption_words'):
        if type(result[key]) is not int:
            raise ValueError(f'{key} must be an integer')
    if not (160 <= result['width'] <= 2160 and 160 <= result['height'] <= 3840):
        raise ValueError('Resolution must be between 160 and 2160 × 3840')
    if result['width'] % 2 or result['height'] % 2 or not 1 <= result['fps'] <= 60:
        raise ValueError('Resolution must be even and frame rate must be 1–60')
    if not 0 <= result['crf'] <= 40 or result['preset'] not in ('ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow'):
        raise ValueError('Invalid H.264 quality or speed preset')
    for key in ('target_duration', 'title_duration', 'end_duration', 'narration_volume', 'music_volume',
                'publish_min_duration', 'publish_max_duration', 'pause_warning_seconds'):
        value = result[key]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f'{key} must be a finite nonnegative number')
    if result['target_duration'] <= 0 or result['narration_volume'] > 2 or result['music_volume'] > 1:
        raise ValueError('Target must be positive; voice volume is 0–2 and music volume 0–1')
    if result['subtitle_mode'] not in ('auto', 'manual'):
        raise ValueError('Subtitle mode must be auto or manual')
    if not (10 <= result['font_size'] <= 120 and 10 <= result['wrap_chars'] <= 60 and 1 <= result['caption_words'] <= 20):
        raise ValueError('Caption size, wrap width, or word count is outside the supported range')
    if not (0 <= result['margin_bottom'] <= 1000 and 0 <= result['margin_left'] <= 400 and 0 <= result['margin_right'] <= 400):
        raise ValueError('Caption margins are outside the supported range')
    if not (0 <= result['outline'] <= 10 and 0 <= result['shadow'] <= 10):
        raise ValueError('Caption outline and shadow must be 0–10')
    for key in ('font', 'title_card', 'end_card', 'narration_asset', 'music_asset'):
        if not isinstance(result[key], str):
            raise ValueError(f'{key} must be text')
    if not result['font'].strip() or any(c in result['font'] for c in ',\r\n'):
        raise ValueError('Font name must be nonempty and contain no commas or line breaks')
    if type(result['duck_music']) is not bool or not isinstance(result['sound_effects'], list):
        raise ValueError('Invalid music ducking or sound effect settings')
    for index, effect in enumerate(result['sound_effects']):
        label = f'sound_effects[{index}]'
        if not isinstance(effect, dict) or not {'asset', 'start_seconds', 'volume'}.issubset(effect):
            raise ValueError(f'{label} needs asset, start_seconds, and volume.')
        if not isinstance(effect['asset'], str) or not effect['asset'].strip():
            raise ValueError(f'{label}.asset must be a nonempty path.')
        for key in ('start_seconds', 'volume'):
            value = effect[key]
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f'{label}.{key} must be a finite nonnegative number.')
        if effect['volume'] > 1:
            raise ValueError(f'{label}.volume must be between 0 and 1.')
    if result['publish_min_duration'] > result['publish_max_duration'] or result['pause_warning_seconds'] <= 0:
        raise ValueError('Publishing duration range must be ordered and pause threshold positive.')
    import re
    for key in ('caption_color', 'card_background', 'card_accent', 'card_text'):
        if not isinstance(result[key], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', result[key]):
            raise ValueError(f'{key} must be a #RRGGBB colour.')
    return result


def card_durations(settings: dict) -> tuple[float, float]:
    return (settings['title_duration'] if settings['title_card'].strip() else 0,
            settings['end_duration'] if settings['end_card'].strip() else 0)
