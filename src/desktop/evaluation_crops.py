"""Resolve visual evidence in the exact measurement recorded by an evaluation."""

import csv
import json
from math import isclose
from pathlib import Path
import re

from .object_labels import object_key


class EvaluationCrops:
    """Index recorded masks and legacy review crops without consulting live results."""

    def __init__(self, workspace):
        self.root = Path(workspace).resolve()
        self._manifests = {}
        self._legacy = {}
        self._scales = {}

    def table_measurements(self, references, project_datasets):
        """Resolve export references to project-owned versions, never by TIFF name."""
        from .service import fingerprint

        references = set(references) - {None, ''}
        found = {}

        def record(reference, directory, filename):
            if reference not in references or not directory or not filename:
                return
            try:
                output = (self.root / directory).resolve()
                source = (output / Path(filename).name).resolve()
                if self.root in output.parents and source.parent == output and source.is_file():
                    found.setdefault(reference, set()).add((output, source))
            except (OSError, TypeError, ValueError, RuntimeError):
                pass

        for dataset in project_datasets:
            record(f"{dataset.get('id')}:{dataset.get('measurement_signature')}",
                   dataset.get('results_dir'), dataset.get('last_csv'))
        if references - found.keys():
            # Old versions remain on disk after a later extraction or edit.
            # The digest of their saved provenance is the exported signature.
            for path in (self.root / 'measurements').glob('*/*/measurement_run.json'):
                try:
                    path = path.resolve()
                    if self.root not in path.parents:
                        continue
                    run = json.loads(path.read_text(encoding='utf-8'))
                    reference = f"{run['dataset_id']}:{fingerprint(run)}"
                    record(reference, path.parent, run['summary']['csv_path'])
                except (OSError, TypeError, ValueError, KeyError, RuntimeError):
                    continue
        return {reference: next(iter(paths)) for reference, paths in found.items() if len(paths) == 1}

    @staticmethod
    def table_object_paths(snapshot, measurements):
        """Bind table rows only when their saved object keys and predictors agree."""
        features = snapshot['features']
        datasets = {item['dataset_id']: item.get('measurement_reference') for item in snapshot['datasets']}
        indexed = {}
        for reference, (output, path) in measurements.items():
            try:
                with path.open(encoding='utf-8-sig', newline='') as handle:
                    rows = {}
                    for row in csv.DictReader(handle):
                        key = object_key(row['Tile_Name'], row['Object_ID'])
                        rows[key] = None if key in rows else row
                indexed[reference] = output, rows
            except (OSError, ValueError, KeyError, TypeError):
                continue
        result = {}
        for index, row in enumerate(snapshot['rows']):
            reference = datasets[row['dataset_id']]
            if reference not in indexed or row.get('image_identity_missing'):
                continue
            output, rows = indexed[reference]
            try:
                saved = rows.get(object_key(row['tile_name'], row['object_id']))
                if saved and all(isclose(float(saved[key]), value, rel_tol=1e-12)
                                 for key, value in zip(features, row['values'], strict=True)):
                    result[index] = output
            except (ValueError, KeyError, TypeError):
                continue
        return result

    @staticmethod
    def _read_manifest(base):
        try:
            manifest = (base / 'object_locations.json').resolve()
            if base not in manifest.parents:
                return {}
            document = json.loads(manifest.read_text(encoding='utf-8'))
            if document.get('schema_version') != 1:
                return {}
            paths = {}
            for entry in document['objects']:
                key = object_key(entry['tile_name'], entry['object_id'])
                # A duplicate identity is ambiguous even if paths coincide.
                paths[key] = None if key in paths else (entry['mask'], entry.get('measurement_space'))
            return paths
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return {}

    @staticmethod
    def _png(base, path):
        if not isinstance(path, (str, Path)):
            return None
        try:
            file = (base / path).resolve()
            if base in file.parents and file.suffix.casefold() == '.png' and file.is_file():
                return file
        except (OSError, ValueError, RuntimeError):
            pass
        return None

    def paths(self, results_dir, tile_name, object_id):
        """Return an exact binary mask and an unambiguous review crop, if present."""
        if not results_dir:
            return None, None
        try:
            key = object_key(tile_name, object_id)
            result = (self.root / results_dir).resolve()
            base = (result / 'verification_masks').resolve()
            if self.root not in result.parents or result not in base.parents:
                return None, None
            folder = (base / tile_name).resolve()
            if base not in folder.parents:
                return None, None
            if base not in self._manifests:
                self._manifests[base] = self._read_manifest(base)
            location = self._manifests[base].get(key)
            exact = self._png(base, location[0]) if location else None
            if folder not in self._legacy:
                legacy = {}
                for file in folder.glob('obj_*.png'):
                    match = re.fullmatch(r'obj_(\d+)_.+\.png', file.name)
                    if match:
                        ident = int(match.group(1))
                        legacy[ident] = None if ident in legacy else self._png(folder, file)
                self._legacy[folder] = legacy
            return exact, self._legacy[folder].get(int(object_id))
        except (OSError, TypeError, ValueError, RuntimeError):
            return None, None

    def resolve(self, results_dir, tile_name, object_id):
        """Prefer the saved binary mask, with a labeled review-crop fallback."""
        mask, crop = self.paths(results_dir, tile_name, object_id)
        return (mask, 'exact') if mask is not None else (crop, 'legacy') if crop is not None else (None, None)

    def ruler_scale(self, results_dir, tile_name, object_id):
        """Resolve a crop's units against the same frozen measurement as its image."""
        from .image_ruler import measurement_ruler_scale

        if not results_dir:
            return None
        try:
            result = (self.root / results_dir).resolve()
            base = (result / 'verification_masks').resolve()
            if self.root not in result.parents or result not in base.parents:
                return None
            if base not in self._manifests:
                self._manifests[base] = self._read_manifest(base)
            location = self._manifests[base].get(object_key(tile_name, object_id))
            space = location[1] if location else None
            key = result, space
            if key not in self._scales:
                self._scales[key] = measurement_ruler_scale(result, space)
            return self._scales[key]
        except (OSError, TypeError, ValueError, RuntimeError):
            return None
