"""
Configuration File
Stores all constants, magic numbers, and default paths for the pipeline.
"""
# Directory Paths
INPUT_DIR = 'data/1_raw_large_images'
OUTPUT_DIR = 'data/2_sliced_tiles'
RAW_OUTPUT_DIR = 'data/3_raw_sliced_tiles'

# Block 3 & ML Paths
LABELS_DIR = 'data/3_sam_labels'     # Сюда кладем .txt файлы из CVAT/SAM
FEATURES_DIR = 'data/4_final_results' # Сюда сохранится финальный CSV

# Metadata Erasure (Scale bars, text, logos)
ERASE_METADATA = True
# Defines a rectangle in the bottom-right corner to paint black (Height, Width)
METADATA_ZONE = {'h_from_bottom': 350, 'w_from_right': 700}

# Adaptive Grid Parameters (Smart Slicer)
TARGET_SIZE = 1500
MARGIN_START = 1300
MARGIN_END = 1500

# Dynamic Expansion Step (If object is cut, expand window backwards by this amount)
DYNAMIC_EXPANSION_STEP = 30
MIN_MARGIN_LIMIT = 500 # Do not search further back than this to avoid infinite loops

# Filter Parameters (Global Preprocessor)
BILATERAL_D = 9
BILATERAL_SIGMA_COLOR = 35
BILATERAL_SIGMA_SPACE = 9

TOPHAT_RADIUS = 91
GAMMA_VALUE = 1.8