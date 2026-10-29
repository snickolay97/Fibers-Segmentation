"""Serializable per-run settings shared by the desktop UI and pipeline."""
from dataclasses import asdict, dataclass
from collections.abc import Mapping
import math
from src.default_settings import FACTORY_DEFAULTS, factory_defaults


class PipelineCancelled(RuntimeError):
    """A cooperative cancellation; incomplete results must not be published."""


class SettingsValidationError(ValueError):
    """Strict backend validation with issues also consumable by the UI."""
    def __init__(self, issues):
        self.issues = issues
        super().__init__('; '.join(issue['message'] for issue in issues))


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
                      'animation_max_trial_frames'}
    positive_integers = {'overview_size', 'bilateral_d', 'tophat_radius',
                         'min_sub_object_area', 'min_corridor_width', 'animation_max_trial_frames'}
    positive_numbers = {'bilateral_sigma_color', 'bilateral_sigma_space', 'gamma',
                        'otsu_safety_factor', 'tier2_threshold_factor', 'seam_repulsion_power'}
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
            if isinstance(value, bool) or not isinstance(value, int):
                add(name, 'integer', 'must be an integer')
            elif name == 'target_size' and value < 8:
                add(name, 'minimum', 'must be at least 8 pixels')
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
        return dict(margin_start=int(self.target_size * .75),
                    margin_end=int(self.target_size * .975),
                    dynamic_step=max(1, int(self.target_size * .015)),
                    min_margin_limit=max(1, int(self.target_size * .25)))

    def validate(self):
        issues = self.validation_issues()
        if issues:
            raise SettingsValidationError(issues)
        return self

    def validation_issues(self):
        return inspect_settings(self.to_dict())
