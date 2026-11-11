"""Validated personal defaults kept separate from the immutable factory catalogs."""

import json
import math

from src.app_settings import PipelineSettings
from src.default_settings import EDITOR_DEFAULTS, MASK_EDITOR_DEFAULTS


EDITOR_LIMITS = {
    'tile': {'erase_radius': (0, 150), 'paint_radius': (0, 150),
             'background_radius': (1, 85), 'gamma': (.25, 4.)},
    'mask': {'connection_width': (1, 101), 'brush_width': (1, 101),
             'search_margin': (4, 256)},
}
_CATALOGS = {'tile': EDITOR_DEFAULTS, 'mask': MASK_EDITOR_DEFAULTS}
_KEY = 'personal_scientific_settings'


def editor_factory(kind):
    """Expose editable initial values, excluding fixed safety limits."""
    return {key: _CATALOGS[kind][key] for key in EDITOR_LIMITS[kind]}


def editor_value(kind, key, value):
    default = _CATALOGS[kind][key]
    low, high = EDITOR_LIMITS[kind][key]
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise ValueError(key)
    if type(default) is int and type(value) is not int:
        raise ValueError(key)
    if kind == 'mask' and key in ('brush_width', 'connection_width') and value % 2 == 0:
        raise ValueError(key)
    return value


def read_profile(preferences):
    """An invalid personal value falls back locally without touching saved projects."""
    try:
        data = json.loads(preferences.value(_KEY, '{}'))
        if not isinstance(data, dict):
            data = {}
    except (TypeError, ValueError):
        data = {}
    result = {}
    for kind in EDITOR_LIMITS:
        result[kind] = editor_factory(kind)
        stored = data.get(kind)
        if isinstance(stored, dict):
            for key, value in stored.items():
                if key in result[kind]:
                    try:
                        result[kind][key] = editor_value(kind, key, value)
                    except ValueError:
                        pass
    try:
        result['processing'] = PipelineSettings.from_dict(data.get('processing')).to_dict()
        mode = data.get('calibration_mode', 'auto')
        result['calibration_mode'] = mode if mode in ('auto', 'manual') else 'auto'
        if result['calibration_mode'] == 'auto':
            result['processing']['pixel_size_um'] = None
    except ValueError:
        result.update(processing=PipelineSettings().to_dict(), calibration_mode='auto')
    return result


def write_profile(preferences, values):
    preferences.setValue(_KEY, json.dumps(values, allow_nan=False))
