"""Versioned factory settings, independent of projects and mutable config.

Change the corresponding catalog version when changing factory behavior.
Values are immutable; callers receive a separate dict for editable state.
"""
from types import MappingProxyType


DEFAULTS_VERSION = 3
EDITOR_DEFAULTS_VERSION = 3
EDITOR_DEFAULTS = MappingProxyType({
    'erase_radius': 60,
    'paint_radius': 3,
    'background_radius': 12,
    'gamma': 1.0,
})
MASK_EDITOR_DEFAULTS_VERSION = 1
MASK_EDITOR_DEFAULTS = MappingProxyType({
    'connection_width': 3,
    'brush_width': 7,
    'search_margin': 48,
    'path_intensity_weight': 4.0,
    'max_route_pixels': 1_000_000,
    'max_editor_pixels': 32_000_000,
})
MODEL_DEFAULTS_VERSION = 1
MODEL_DEFAULTS = MappingProxyType({
    'forest_tree_count': 200,
    'split_mode': 'group',
    # Candidate order also resolves ties. The first combination is used with
    # cross-validation off.
    'split_criteria': ('gini', 'entropy'),
    'tree_candidate_limits': ((3, 2), (5, 2), (8, 5), (3, 5)),  # depth, leaf size
    'forest_candidate_limits': (('sqrt', None, 2), ('sqrt', 5, 2),
                                (None, None, 2), ('sqrt', None, 5)),  # features, depth, leaf size
})
PIXEL_SEGMENTATION_DEFAULTS_VERSION = 1
PIXEL_SEGMENTATION_DEFAULTS = MappingProxyType({
    'local_radii': (2, 6),
    'background_margin': 8,
    'samples_per_label': 4096,
    'max_tile_pixels': 32_000_000,
})
STRAIGHT_SHIFT_FIELDS = ('straight_shift_left', 'straight_shift_right')
FACTORY_DEFAULTS = MappingProxyType({
    'target_size': 1500,
    'search_window_end': None,  # Derive the exclusive edge from the tile size.
    'straight_shift_left': None,
    'straight_shift_right': 0,
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
