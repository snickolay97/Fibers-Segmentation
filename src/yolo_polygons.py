"""Read exact normalized annotation geometry shared by measurement and preview."""

import numpy as np

from src.object_classes import OBJECT_CLASS_CATALOG


_CLASS_IDS = {entry['id'] for entry in OBJECT_CLASS_CATALOG}


def read_yolo_polygons(path):
    """Return class IDs and continuous vertices in the normalized model canvas."""
    polygons = []
    with open(path, encoding='utf-8-sig') as source:
        for line_number, line in enumerate(source, 1):
            fields = line.split()
            if not fields:
                continue
            if len(fields) < 7 or (len(fields) - 1) % 2:
                raise ValueError(f'Expected YOLO segmentation polygon (at least 3 points): {path}')
            try:
                class_id = int(fields[0])
                coords = np.array(fields[1:], dtype=float).reshape(-1, 2)
            except ValueError as error:
                raise ValueError(f'Invalid YOLO numeric values at {path}:{line_number}') from error
            if class_id not in _CLASS_IDS:
                raise ValueError(f'Unknown annotation class at {path}:{line_number}')
            if not np.all(np.isfinite(coords)) or np.any(coords < 0) or np.any(coords > 1):
                raise ValueError(f'YOLO coordinates must be finite and normalized to 0..1 at {path}:{line_number}')
            polygons.append((class_id, coords))
    return polygons
