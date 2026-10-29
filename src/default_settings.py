"""Versioned factory settings, independent of projects and mutable config.

Change DEFAULTS_VERSION deliberately when changing this baseline. All values
are immutable primitives; callers receive a separate dict for editable state.
"""
from types import MappingProxyType


DEFAULTS_VERSION = 1
FACTORY_DEFAULTS = MappingProxyType({
    'target_size': 1500,
    'overview_size': 6000,
    'save_raw_tiles': False,
    'enable_animations': False,
    'channel': 0,
    'plane': 0,
    'pixel_size_um': None,
    'bilateral_d': 9,
    'bilateral_sigma_color': 45,
    'bilateral_sigma_space': 15,
    'tophat_radius': 85,
    'gamma': 1.2,
    'otsu_safety_factor': 0.25,
    'bridge_kernel_size': 17,
    'buffer_kernel_size': 5,
    'tier2_threshold_factor': 0.70,
    'min_clean_threshold': 25,
    'min_sub_object_area': 30,
    'min_corridor_width': 15,
    'oversized_policy': 'preserve',
    'seam_repulsion_power': 1.5,
    'save_coverage_masks': False,
    'animation_max_trial_frames': 24,
    'enable_bilateral': True,
    'enable_tophat': True,
    'enable_gamma': True,
    'enable_closing': True,
    'enable_dilation': True,
})


def factory_defaults():
    """Return editable settings without exposing the factory baseline."""
    return dict(FACTORY_DEFAULTS)
