"""
CLI Utility to quickly exclude tiles without running the whole pipeline.
Usage: python tools/manage_tiles.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tile_manager import TileManager

TARGET_DATASET = 'FL01_G3_RGB_Red'
# Resolve IDs from the overview for this exact dataset. A fresh preparation
# can assign different IDs even when it uses the same source TIFF.
TILES_TO_EXCLUDE = []

if __name__ == "__main__":
    manager = TileManager()
    manager.exclude(dataset_name=TARGET_DATASET, tile_specs=TILES_TO_EXCLUDE)
