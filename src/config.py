"""
Configuration File
Stores all constants, magic numbers, and default paths for the pipeline.
"""
# Directory Paths
INPUT_DIR = 'data/1_raw_large_images'
OUTPUT_DIR = 'data/2_sliced_tiles'
RAW_OUTPUT_DIR = 'data/3_raw_sliced_tiles'

# Block 3 & ML Paths
LABELS_DIR = 'data/3_sam_labels'     # Place .txt annotation files from CVAT/SAM here
FEATURES_DIR = 'data/4_final_results' # The final CSV will be saved here

# --- PERFORMANCE & VISUALIZATION TOGGLES ---
ENABLE_ANIMATIONS = True
ANIMATION_DIR = 'data/animations'

# Adaptive Grid Parameters (Smart Slicer)
TARGET_SIZE = 1500
MARGIN_START = 1300
MARGIN_END = 1500

# Dynamic Expansion Step (If object is cut, expand window backwards by this amount)
DYNAMIC_EXPANSION_STEP = 30
MIN_MARGIN_LIMIT = 500

# Filter Parameters (Global Preprocessor)
BILATERAL_D = 9
BILATERAL_SIGMA_COLOR = 35
BILATERAL_SIGMA_SPACE = 9

TOPHAT_RADIUS = 91
GAMMA_VALUE = 1.2  # Lowered from 1.8 to prevent crushing faint cylindrical connections

# Safety Thresholding Factor for Obstacle Detection
# Multiplier for Otsu's threshold (0.35 = 35% of Otsu). Guarantees faint bridges and loops are preserved.
OTSU_SAFETY_FACTOR = 0.25

# Dijkstra Algorithm Parameters
SEAM_REPULSION_POWER = 1.5  # How strongly the seam is repelled from objects (1.0 = standard, >1.0 = stronger repulsion)
SEAM_OBSTACLE_PENALTY = 10000.0 # Extreme cost penalty for crossing a white pixel (obstacle)