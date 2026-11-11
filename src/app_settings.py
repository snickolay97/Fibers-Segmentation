"""Serializable per-run settings shared by the desktop UI and pipeline."""
from dataclasses import asdict, dataclass
from collections.abc import Mapping
import math
from src.default_settings import FACTORY_DEFAULTS, STRAIGHT_SHIFT_FIELDS, factory_defaults


class PipelineCancelled(RuntimeError):
    """A cooperative cancellation; incomplete results must not be published."""


class SettingsValidationError(ValueError):
    """Strict backend validation with issues also consumable by the UI."""
    def __init__(self, issues):
        self.issues = issues
        super().__init__('; '.join(issue['message'] for issue in issues))


def search_window_end_range(target_size):
    """A manual exclusive end leaves at least one column in the initial window."""
    return target_size * 75 // 100 + 1, target_size


def _tiling_margins(target_size, search_window_end=None):
    """Resolve the initial half-open window in source pixels from the crop origin."""
    return dict(margin_start=search_window_end_range(target_size)[0] - 1,
                margin_end=target_size * 975 // 1000 if search_window_end is None else search_window_end,
                dynamic_step=max(1, target_size * 15 // 1000),
                min_margin_limit=max(1, target_size // 4))


def straight_shift_limits(target_size, search_window_end=None):
    """Return the allowed shifts in source pixels.

    Use the automatic end for an invalid draft so the UI can still show limits.
    """
    low, high = search_window_end_range(target_size)
    if type(search_window_end) is not int or not low <= search_window_end <= high:
        search_window_end = None
    margins = _tiling_margins(target_size, search_window_end)
    return dict(straight_shift_left=margins['margin_start'] - margins['min_margin_limit'],
                straight_shift_right=target_size - margins['margin_end'])


def inspect_settings(values):
    """Return every invalid field without changing input or coercing values.

    Missing fields use factory defaults for backward compatibility. A stored
    null/list settings container is invalid; from_dict(None) separately means
    the caller requested a default runtime instance.
    """
    if not isinstance(values, Mapping):
        return [dict(field='settings', code='container_type',
                     message='settings must be an object', value=values,
                     default=factory_defaults())]
    issues = []
    integer_fields = {'target_size', 'overview_size', 'channel', 'plane', 'bilateral_d',
                      'tophat_radius', 'bridge_kernel_size', 'buffer_kernel_size',
                      'min_clean_threshold', 'min_sub_object_area', 'min_corridor_width',
                      'animation_max_trial_frames', 'search_window_end', *STRAIGHT_SHIFT_FIELDS}
    positive_integers = {'overview_size', 'bilateral_d', 'tophat_radius',
                         'min_sub_object_area', 'min_corridor_width', 'animation_max_trial_frames'}
    positive_numbers = {'bilateral_sigma_color', 'bilateral_sigma_space', 'gamma',
                        'otsu_safety_factor', 'tier2_threshold_factor', 'seam_repulsion_power'}
    target_size = values.get('target_size', FACTORY_DEFAULTS['target_size'])
    if not isinstance(target_size, int) or target_size < 8:
        target_size = FACTORY_DEFAULTS['target_size']
    end_range = search_window_end_range(target_size)
    shift_limits = straight_shift_limits(target_size, values.get('search_window_end'))
    def add(name, code, rule):
        issues.append(dict(field=name, code=code, message=str(name)+' '+rule,
                           value=values[name], default=FACTORY_DEFAULTS.get(name)))
    for name in values:
        if name not in FACTORY_DEFAULTS:
            add(name, 'unknown', 'is not a supported setting')
    for name, default in FACTORY_DEFAULTS.items():
        if name not in values:
            continue
        value = values[name]
        if isinstance(default, bool):
            if not isinstance(value, bool):
                add(name, 'boolean', 'must be boolean')
        elif name in integer_fields:
            if name in ('straight_shift_left', 'search_window_end') and value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                add(name, 'integer', 'must be an integer')
            elif name == 'target_size' and value < 8:
                add(name, 'minimum', 'must be at least 8 pixels')
            elif name == 'search_window_end' and not end_range[0] <= value <= end_range[1]:
                add(name, 'range', f'must be between {end_range[0]} and {end_range[1]} source pixels')
            elif name in shift_limits and not 0 <= value <= shift_limits[name]:
                add(name, 'range', f'must be between 0 and {shift_limits[name]} source pixels')
            elif name in positive_integers and value <= 0:
                add(name, 'positive', 'must be positive')
            elif name in ('bridge_kernel_size', 'buffer_kernel_size') and (value <= 0 or value % 2 == 0):
                add(name, 'positive_odd', 'must be a positive odd integer')
            elif name in ('channel', 'plane') and value < 0:
                add(name, 'nonnegative', 'must be nonnegative')
            elif name == 'min_clean_threshold' and not 0 <= value <= 255:
                add(name, 'range', 'must be between 0 and 255')
        elif name in positive_numbers or name == 'pixel_size_um':
            if name == 'pixel_size_um' and value is None:
                continue
            numeric = not isinstance(value, bool) and isinstance(value, (int,float))
            try:
                valid = numeric and math.isfinite(value) and value > 0
            except OverflowError:
                valid = False
            if not valid:
                add(name, 'finite_positive', 'must be a finite positive number'+(' or null' if name=='pixel_size_um' else ''))
        elif name == 'oversized_policy' and (not isinstance(value,str) or value not in ('preserve', 'error')):
            add(name, 'choice', 'must be preserve or error')
    return issues


@dataclass
class PipelineSettings:
    target_size: int = FACTORY_DEFAULTS['target_size']
    overview_size: int = FACTORY_DEFAULTS['overview_size']
    save_raw_tiles: bool = FACTORY_DEFAULTS['save_raw_tiles']
    enable_animations: bool = FACTORY_DEFAULTS['enable_animations']
    channel: int = FACTORY_DEFAULTS['channel']
    plane: int = FACTORY_DEFAULTS['plane']
    pixel_size_um: float | None = FACTORY_DEFAULTS['pixel_size_um']
    bilateral_d: int = FACTORY_DEFAULTS['bilateral_d']
    bilateral_sigma_color: float = FACTORY_DEFAULTS['bilateral_sigma_color']
    bilateral_sigma_space: float = FACTORY_DEFAULTS['bilateral_sigma_space']
    tophat_radius: int = FACTORY_DEFAULTS['tophat_radius']
    gamma: float = FACTORY_DEFAULTS['gamma']
    otsu_safety_factor: float = FACTORY_DEFAULTS['otsu_safety_factor']
    bridge_kernel_size: int = FACTORY_DEFAULTS['bridge_kernel_size']
    buffer_kernel_size: int = FACTORY_DEFAULTS['buffer_kernel_size']
    tier2_threshold_factor: float = FACTORY_DEFAULTS['tier2_threshold_factor']
    min_clean_threshold: int = FACTORY_DEFAULTS['min_clean_threshold']
    min_sub_object_area: int = FACTORY_DEFAULTS['min_sub_object_area']
    min_corridor_width: int = FACTORY_DEFAULTS['min_corridor_width']
    oversized_policy: str = FACTORY_DEFAULTS['oversized_policy']
    seam_repulsion_power: float = FACTORY_DEFAULTS['seam_repulsion_power']
    save_coverage_masks: bool = FACTORY_DEFAULTS['save_coverage_masks']
    animation_max_trial_frames: int = FACTORY_DEFAULTS['animation_max_trial_frames']
    enable_bilateral: bool = FACTORY_DEFAULTS['enable_bilateral']
    enable_tophat: bool = FACTORY_DEFAULTS['enable_tophat']
    enable_gamma: bool = FACTORY_DEFAULTS['enable_gamma']
    enable_closing: bool = FACTORY_DEFAULTS['enable_closing']
    enable_dilation: bool = FACTORY_DEFAULTS['enable_dilation']
    straight_shift_left: int | None = FACTORY_DEFAULTS['straight_shift_left']
    straight_shift_right: int = FACTORY_DEFAULTS['straight_shift_right']
    search_window_end: int | None = FACTORY_DEFAULTS['search_window_end']

    @classmethod
    def from_dict(cls, values):
        if values is None:
            return cls().validate()
        issues = inspect_settings(values)
        if issues:
            raise SettingsValidationError(issues)
        return cls(**dict(values)).validate()

    def to_dict(self):
        return asdict(self)

    def margins(self):
        return _tiling_margins(self.target_size, self.search_window_end)

    def validate(self):
        issues = self.validation_issues()
        if issues:
            raise SettingsValidationError(issues)
        return self

    def validation_issues(self):
        return inspect_settings(self.to_dict())
