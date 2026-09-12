"""
Configuration File
Stores all constants, magic numbers, and default paths for the pipeline.
"""
import os

# Directory Paths
INPUT_DIR = 'data/1_raw_large_images'
OUTPUT_DIR = 'data/2_sliced_tiles'
RAW_OUTPUT_DIR = 'data/3_raw_sliced_tiles'

# Block 3 & ML Paths
LABELS_DIR = 'data/3_sam_labels'        # Place .txt annotation files from CVAT/SAM here
FEATURES_DIR = 'data/4_final_results'   # The final CSV/Excel files will be saved here

# ==============================================================================
# PERFORMANCE & VISUALIZATION TOGGLES
# ==============================================================================
# 1. Animations Toggle (generates step-by-step GIF for each seam pathfinding)
ENABLE_ANIMATIONS = True                # Set to True to generate pathfinding GIFs
ANIMATION_DIR = 'data/animations'

# 2. Raw Tiles Toggle (saves un-filtered raw tiles mapped to the exact same seams)
SAVE_RAW_TILES = True                  # Set to True only when raw tiles are required

# 3. Overview Map Resolution (canonical puzzle map size in px)
OVERVIEW_MAP_SIZE = 8000

# ==============================================================================
# ADAPTIVE GRID PARAMETERS (SMART SLICER)
# ==============================================================================
TARGET_SIZE = 2000                      # Strict output canvas size with zero-padding (px)
MARGIN_START = 1500                     # Where seam search window begins relative to anchor
MARGIN_END = 1950                       # Maximum boundary coordinate where seam search window ends

# Dynamic Back-off Parameters (If obstacles block corridor/seam, step window backwards)
DYNAMIC_EXPANSION_STEP = 30             # Step size in pixels when backing off
MIN_MARGIN_LIMIT = 500                  # Minimum allowed tile width before fallback forced cut
MIN_CORRIDOR_WIDTH = 15                 # Minimum zero-intensity run for an obstacle-free straight cut

# Dijkstra Algorithm Parameters
SEAM_REPULSION_POWER = 1.5              # Repulsion gradient steepness from fiber boundaries
SEAM_OBSTACLE_PENALTY = 1000000.0       # Prohibitive cost: forces trajectory around fibers

# ==============================================================================
# GLOBAL PREPROCESSOR (BLOCK 1)
# ==============================================================================
BILATERAL_D = 9
BILATERAL_SIGMA_COLOR = 45              # Stitches fluctuating faint boundaries
BILATERAL_SIGMA_SPACE = 15              # Preserves continuity along fiber axes
TOPHAT_RADIUS = 85                      # Background subtraction kernel radius (2R + 1 = 171 px)
GAMMA_VALUE = 1.2                       # Contrast enhancement: lifts dim cylindrical walls

# Safety Thresholding Factor for Obstacle Detection
OTSU_SAFETY_FACTOR = 0.25               # 25% of Otsu baseline captures faint loops and bridges

# ==============================================================================
# OBJECT EXTRACTION & TOPOLOGY (BLOCK 3)
# ==============================================================================
TIER2_THRESHOLD_FACTOR = 0.70           # Multiplier for local Otsu inside Block 3 crops
MIN_CLEAN_THRESHOLD = 25                # Absolute minimum intensity cutoff
MIN_SUB_OBJECT_AREA = 30                # Minimum pixel area for sub-entities

SEPARATION_STRATEGY = 'architectural'   # 'architectural' or 'algorithmic'
ALGORITHMIC_METHOD = 'hybrid'           # 'frangi', 'skeleton_collinearity', or 'hybrid'

# Algorithmic Filters Parameters
FRANGI_SIGMAS = (1.0, 4.0, 1.0)
FRANGI_BETA = 0.5
FRANGI_SENSITIVITY = 0.12
GRAPH_COLLINEARITY_COS_THRESH = -0.65
GRAPH_BRANCH_PROBE_DIST = 8
BRIDGE_MAX_INTENSITY_RATIO = 0.65
