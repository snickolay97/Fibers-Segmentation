"""Pipeline paths, low-level fallbacks and historical experiment constants.

The application uses the immutable catalogue in default_settings.py to create
PipelineSettings. These constants also support direct calls to older helpers.
"""
import os

# Standalone pipeline directories, relative to the working directory.
INPUT_DIR = 'data/1_raw_large_images'
OUTPUT_DIR = 'data/2_sliced_tiles_1500'
RAW_OUTPUT_DIR = 'data/3_raw_sliced_tiles_1500'

LABELS_DIR = 'data/3_sam_labels'
FEATURES_DIR = 'data/4_final_results'

# Optional outputs for inspection. GIFs show attempted windows and the final route.
ENABLE_ANIMATIONS = False
ANIMATION_DIR = 'data/animations'

# Raw tiles share the same ownership masks as filtered tiles.
SAVE_RAW_TILES = False
OVERVIEW_MAP_SIZE = 6000

# Legacy slicer defaults. Offsets are in source pixels from the crop origin.
TARGET_SIZE = 1500
# Preserve oversized native crops and scale them to the fixed model canvas.
OVERSIZED_OBJECT_POLICY = 'preserve'
MARGIN_START = int(TARGET_SIZE * 0.75)
MARGIN_END = int(TARGET_SIZE * 0.975)
DYNAMIC_EXPANSION_STEP = max(1, int(TARGET_SIZE * 0.015))
MIN_MARGIN_LIMIT = max(1, int(TARGET_SIZE * 0.25))
MIN_CORRIDOR_WIDTH = 15  # Preferred free run before trying the narrower fallback.

SEAM_REPULSION_POWER = 1.5  # Exponent in the cost based on distance to the mask.
SEAM_OBSTACLE_PENALTY = float('inf')  # Historical constant. The solver assigns infinity directly.

# Grayscale preprocessing.
BILATERAL_D = 9
BILATERAL_SIGMA_COLOR = 45              # Intensity difference in the bilateral weight
BILATERAL_SIGMA_SPACE = 15              # Spatial distance in the bilateral weight
TOPHAT_RADIUS = 85                      # Background subtraction kernel radius (2R + 1 = 171 px)
GAMMA_VALUE = 1.2                       # Reciprocal exponent lifts dim signal and background

OTSU_SAFETY_FACTOR = 0.25  # Multiplier for the protective threshold.

# Local measurement masks.
TIER2_THRESHOLD_FACTOR = 0.70           # Multiplier for local Otsu inside Block 3 crops
MIN_CLEAN_THRESHOLD = 25                # Absolute minimum intensity cutoff
MIN_SUB_OBJECT_AREA = 30                # Minimum pixel area for sub-entities

# Historical experimental settings. Block 3 currently uses local thresholding
# and connected components, without selecting any of these algorithms.
SEPARATION_STRATEGY = 'architectural'   # 'architectural' or 'algorithmic'
ALGORITHMIC_METHOD = 'hybrid'           # 'frangi', 'skeleton_collinearity', or 'hybrid'

FRANGI_SIGMAS = (1.0, 4.0, 1.0)
FRANGI_BETA = 0.5
FRANGI_SENSITIVITY = 0.12
GRAPH_COLLINEARITY_COS_THRESH = -0.65
GRAPH_BRANCH_PROBE_DIST = 8
BRIDGE_MAX_INTENSITY_RATIO = 0.65

# Model coverage PNGs store fractional coverage after resizing.
SAVE_COVERAGE_MASKS = False
ANIMATION_MAX_TRIAL_FRAMES = 24  # Display limit. The trial log retains all windows.
# Protective morphology, independent of the image display filters.
BRIDGE_KERNEL_SIZE = 17
BUFFER_KERNEL_SIZE = 5
