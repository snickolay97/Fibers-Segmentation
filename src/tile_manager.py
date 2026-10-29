import os
import shutil
import re
from pathlib import Path
from typing import List, Union, Set, Optional

from src import config
from src.partition_geometry import dataset_path, read_manifest

class TileManager:
    """
    Operational Tile Exclusion Engine.
    Relocates unverified, out-of-channel, or scale-bar tiles into 'excluded_tiles/'
    subfolders. Automatically skips raw tiles if raw saving was toggled off.
    """

    def __init__(self, project_root: Optional[str] = None, output_dir=None, raw_output_dir=None):
        # Keep the original positional project_root argument working.
        self.project_root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[1]
        self.output_dir = self._rooted(output_dir if output_dir is not None else config.OUTPUT_DIR)
        self.raw_output_dir = self._rooted(raw_output_dir) if raw_output_dir is not None else (self._rooted(config.RAW_OUTPUT_DIR) if output_dir is None else None)

    def _rooted(self, value):
        path = Path(value)
        return path.resolve() if path.is_absolute() else (self.project_root/path).resolve()

    def _dataset(self, root, dataset_name):
        if not isinstance(dataset_name, str) or not re.fullmatch(r'[^/\\:]+', dataset_name) or dataset_name in ('.', '..'):
            raise ValueError('Dataset name must be a safe directory name')
        return dataset_path(root, dataset_name)

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
        if any(v <= 0 for v in ids):
            raise ValueError('Tile IDs must be positive')
        return ids

    def exclude(self, dataset_name: str, tile_specs: List[Union[int, str]]) -> int:
        return self._move(dataset_name, tile_specs, restore=False)

    def restore(self, dataset_name: str, tile_specs: List[Union[int, str]]) -> int:
        return self._move(dataset_name, tile_specs, restore=True)

    def list_excluded(self, dataset_name):
        base = self._dataset(self.output_dir, dataset_name)
        excluded = dataset_path(base, 'excluded_tiles')
        return sorted(ident for ident, filename in self._filenames(base, dataset_name).items()
                      if dataset_path(excluded, filename).is_file())

    @staticmethod
    def _filenames(base, dataset_name):
        manifests = sorted((base/'overview').glob('*_tiles_coords.json'))
        if len(manifests) > 1:
            raise ValueError('Multiple dataset manifests found')
        result = {}
        if manifests:
            records = read_manifest(manifests[0]).get('tiles', [])
            for record in records:
                ident, filename = record.get('id'), record.get('filename')
                path = dataset_path(base, filename)
                match = re.fullmatch(r'[^/\\]+_tile_(\d+)\.png', filename)
                if path.parent != base or not isinstance(ident, int) or ident <= 0 or not match or int(match.group(1)) != ident or ident in result:
                    raise ValueError('Invalid tile filename or ID in manifest')
                result[ident] = filename
        else:
            for folder in (base, base/'excluded_tiles'):
                for path in folder.glob('*.png'):
                    match = re.fullmatch(re.escape(dataset_name)+r'_tile_(\d+)\.png', path.name)
                    if match:
                        result[int(match.group(1))] = path.name
        return result

    def _move(self, dataset_name, tile_specs, restore):
        ids = self.parse_specs(tile_specs)
        base = self._dataset(self.output_dir, dataset_name)
        if not base.is_dir() or not ids:
            return 0
        filenames = self._filenames(base, dataset_name)
        roots = [base]
        if self.raw_output_dir is not None:
            raw = self._dataset(self.raw_output_dir, dataset_name)
            if raw.is_dir() and raw != base:
                roots.append(raw)
        planned = []
        moved_count = 0
        for ident in sorted(ids):
            filename = filenames.get(ident)
            if filename is None:
                continue
            for root in roots:
                active = dataset_path(root, filename)
                excluded = dataset_path(root, 'excluded_tiles/'+filename)
                source, destination = (excluded, active) if restore else (active, excluded)
                if not source.is_file():
                    continue
                if destination.exists():
                    raise FileExistsError('Tile destination already exists: '+str(destination))
                if source.is_symlink():
                    raise ValueError('Tile files must not be symlinks')
                planned.append((source, destination))
                if root == base:
                    moved_count += 1
        completed = []
        try:
            for source, destination in planned:
                destination.parent.mkdir(exist_ok=True)
                # Both locations are inside the same checked dataset directory.
                source.rename(destination)
                completed.append((source, destination))
        except BaseException:
            for source, destination in reversed(completed):
                destination.rename(source)
            raise
        return moved_count
