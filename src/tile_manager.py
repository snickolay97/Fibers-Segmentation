import os
import shutil
from typing import List, Union, Set, Optional

from src import config

class TileManager:
    """
    Operational Tile Exclusion Engine.
    Relocates unverified, out-of-channel, or scale-bar tiles into 'excluded_tiles/'
    subfolders. Automatically skips raw tiles if raw saving was toggled off.
    """

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = project_root or os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    @staticmethod
    def parse_specs(specs: Union[List[Union[int, str]], str, int]) -> Set[int]:
        if isinstance(specs, (str, int)):
            specs = [specs]

        ids = set()
        for item in specs:
            if isinstance(item, int):
                ids.add(item)
            elif isinstance(item, str):
                tokens = [t.strip() for t in item.split(',') if t.strip()]
                for token in tokens:
                    if '-' in token:
                        parts = token.split('-')
                        if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                            start, end = int(parts[0].strip()), int(parts[1].strip())
                            for val in range(min(start, end), max(start, end) + 1):
                                ids.add(val)
                    elif token.isdigit():
                        ids.add(int(token))
        return ids

    def exclude(self, dataset_name: str, tile_specs: List[Union[int, str]]) -> int:
        target_ids = self.parse_specs(tile_specs)
        if not target_ids:
            print("[!] No valid tile IDs provided for exclusion.")
            return 0

        sliced_dir = os.path.join(self.project_root, config.OUTPUT_DIR, dataset_name)
        raw_sliced_dir = os.path.join(self.project_root, config.RAW_OUTPUT_DIR, dataset_name)

        if not os.path.exists(sliced_dir):
            print(f"[!] Target directory does not exist: {sliced_dir}")
            return 0

        exclude_sliced_dir = os.path.join(sliced_dir, 'excluded_tiles')
        os.makedirs(exclude_sliced_dir, exist_ok=True)

        has_raw = os.path.exists(raw_sliced_dir)
        exclude_raw_dir = None
        if has_raw:
            exclude_raw_dir = os.path.join(raw_sliced_dir, 'excluded_tiles')
            os.makedirs(exclude_raw_dir, exist_ok=True)

        moved_count = 0
        print(f"\n---> [Tile Manager] Isolating {len(target_ids)} tiles for dataset '{dataset_name}'...")

        for tile_id in sorted(target_ids):
            tile_name = f"{dataset_name}_tile_{tile_id:04d}.png"

            # 1. Filtered tile
            src_filtered = os.path.join(sliced_dir, tile_name)
            if os.path.exists(src_filtered):
                shutil.move(src_filtered, os.path.join(exclude_sliced_dir, tile_name))
                moved_count += 1

            # 2. Raw tile (only if raw directory was actually generated)
            if has_raw and exclude_raw_dir:
                src_raw = os.path.join(raw_sliced_dir, tile_name)
                if os.path.exists(src_raw):
                    shutil.move(src_raw, os.path.join(exclude_raw_dir, tile_name))

        print(f"[SUCCESS] Moved {moved_count} tile files into 'excluded_tiles/'.")
        return moved_count