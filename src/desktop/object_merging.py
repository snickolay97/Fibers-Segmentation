"""Exact measured-mask loading and reversible measurement version selection."""
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from src.partition_geometry import dataset_path
from . import segmentation_text  # Register the worker's translated errors.
from .i18n import tr


def exact_objects(dataset, tile_name, rows):
    """Read binary masks in native tile coordinates and validate their areas."""
    base = Path(dataset['results_dir']) / 'verification_masks'
    try:
        manifest = json.loads((base / 'object_locations.json').read_text(encoding='utf8'))
        if manifest['schema_version'] != 1:
            raise ValueError('schema')
        expected = {int(r['Object_ID']):r for r in rows if r['Tile_Name'] == tile_name}
        entries = [e for e in manifest['objects'] if e['tile_name'] == tile_name]
        if len(entries) != len(expected) or len({e['object_id'] for e in entries}) != len(entries):
            raise ValueError('identities')
        result, shape = [], None
        for entry in entries:
            if type(entry['object_id']) is not int or entry['object_id'] <= 0:
                raise ValueError('identity')
            row = expected[int(entry['object_id'])]
            mask_path = dataset_path(base, entry['mask'])
            data = mask_path.read_bytes()
            mask = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
            origin = entry['origin_xy']
            current_shape = entry['tile_shape']
            if (mask is None or not mask.any() or not np.isin(mask, [0, 255]).all()
                    or not np.isfinite(float(row['Area'])) or abs(np.count_nonzero(mask) - float(row['Area'])) > .01
                    or len(origin) != 2 or len(current_shape) != 2
                    or not all(type(v) is int for v in [*origin, *current_shape])
                    or min(current_shape) <= 0 or entry['measurement_space'] != row['Measurement_Space']):
                raise ValueError('mask')
            ys, xs = np.nonzero(mask)
            x, y = origin
            if (x+xs.min() < 0 or y+ys.min() < 0 or x+xs.max() >= current_shape[1]
                    or y+ys.max() >= current_shape[0] or shape is not None and shape != current_shape):
                raise ValueError('coordinates')
            shape = current_shape
            manual = np.zeros(mask.shape, bool)
            if entry.get('manual_added_mask'):
                added = cv2.imdecode(np.frombuffer(dataset_path(base,entry['manual_added_mask']).read_bytes(),np.uint8),cv2.IMREAD_GRAYSCALE)
                if added is None or added.shape != mask.shape or not np.isin(added,[0,255]).all() or np.any((added > 0) & (mask == 0)):
                    raise ValueError('manual mask')
                manual = added > 0
            result.append(dict(entry=entry, row=row, mask=mask > 0, manual_added=manual, origin=(x,y),
                               mask_sha256=hashlib.sha256(data).hexdigest()))
        return result
    except (OSError, KeyError, TypeError, ValueError, cv2.error) as error:
        raise ValueError(tr('Exact object masks are unavailable or inconsistent. Recalculate measurements.')) from error


def merge_objects(project, dataset_id, tile_name, object_ids, expected_signature,
                  progress=None, cancelled=None):
    """Publish an exact union without adding any connecting pixels."""
    from .object_corrections import change_objects
    return change_objects(project, dataset_id, tile_name, object_ids, expected_signature,
                          progress=progress, cancelled=cancelled)


def undo_merge(project, dataset_id, expected_signature, progress=None, cancelled=None):
    """Reactivate the intact parent bundle; retain the merged version on disk."""
    from . import service
    dataset = project.get_dataset(dataset_id)
    if not service.results_are_current(dataset) or dataset.get('measurement_signature') != expected_signature:
        raise ValueError(tr('Measurements changed. Reload the tile before merging.'))
    run = json.loads((Path(dataset['results_dir'])/'measurement_run.json').read_text(encoding='utf8'))
    if run.get('operation') not in ('merge_objects', 'correct_objects', 'delete_objects'):
        raise ValueError(tr('No previous merge to undo.'))
    parent = run['parent_measurement']
    parent_path = Path(parent['results_dir']).resolve()
    managed = (Path(project.workspace)/'measurements').resolve()
    candidate = dict(dataset, **parent, results_current=True)
    parent_run = json.loads((parent_path/'measurement_run.json').read_text(encoding='utf8'))
    if (managed not in parent_path.parents or parent_run.get('dataset_id') != dataset_id
            or service.fingerprint(parent_run) != parent['measurement_signature']
            or not service.results_are_current(candidate)):
        raise ValueError(tr('Current measurements are required for merging.'))
    service._check_cancel(cancelled)
    dataset.update(parent, results_current=True, status='completed')
    project.add_history('undo_object_merge', dataset_id=dataset_id, measurement_signature=expected_signature)
    return dict(status='completed', tile_name=run['merge']['tile_name'])
