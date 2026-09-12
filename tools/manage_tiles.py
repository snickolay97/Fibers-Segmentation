"""
CLI Utility to quickly exclude tiles without running the whole pipeline.
Usage: python tools/manage_tiles.py
"""

from src.tile_manager import TileManager

TARGET_DATASET = 'FL01_G3_RGB_Red'
TILES_TO_EXCLUDE = [
    "1-9",
    "14-20, 82, 83, 95-97, 110, 111",
    "153-159, 167-175, 180-205"
]

if __name__ == "__main__":
    manager = TileManager()
    manager.exclude(dataset_name=TARGET_DATASET, tile_specs=TILES_TO_EXCLUDE)