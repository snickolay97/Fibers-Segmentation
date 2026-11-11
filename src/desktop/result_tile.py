"""Resolve a measured object's tile without guessing object coordinates."""
from pathlib import Path
import json

import cv2
import numpy as np

from src.partition_geometry import dataset_path
from src.tile_edits import tile_artifact_path
from .i18n import tr, register_translations
from .qt import QtCore, Signal

register_translations({
    'Highlight object': 'Подсветить объект',
    'Locating the selected object…': 'Поиск выбранного объекта…',
    'The exact measured mask is highlighted.': 'Подсвечена точная измеренная маска объекта.',
    'Located by a unique exact match of the saved crop.': 'Объект найден по единственному точному совпадению сохранённого фрагмента.',
    'This older result cannot be located unambiguously. Recalculate to save object positions.': 'Объект старой версии не удалось найти однозначно. Пересчитайте измерения, чтобы сохранить положения объектов.',
}, hebrew={
    'Highlight object': 'הדגשת האובייקט',
    'Locating the selected object…': 'איתור האובייקט שנבחר…',
    'The exact measured mask is highlighted.': 'מסכת המדידה המדויקת של האובייקט מודגשת.',
    'Located by a unique exact match of the saved crop.': 'המיקום נמצא לפי התאמה מדויקת ויחידה של החיתוך השמור.',
    'This older result cannot be located unambiguously. Recalculate to save object positions.': 'לא ניתן לאתר תוצאה ישנה זו באופן חד־משמעי. חשבו שוב כדי לשמור מיקומי אובייקטים.',
})


class ObjectHighlightTask(QtCore.QRunnable):
    class Signals(QtCore.QObject):
        ready = Signal(object)

    def __init__(self, dataset, row, record, space):
        super().__init__()
        self.arguments = dataset, row, record, space
        self.signals = self.Signals()

    def run(self):
        try:
            result = resolve_object_highlight(*self.arguments)
        except (ValueError, OSError, KeyError, TypeError, cv2.error):
            result = None
        self.signals.ready.emit(result)


def _gray(path):
    return cv2.imdecode(np.frombuffer(Path(path).read_bytes(), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)


def resolve_object_highlight(dataset, row, record, space):
    """Use recorded pixel coordinates or a unique, exact legacy intensity match.

    A partial or ambiguous template match must never be presented as a location.
    The numerical predictors and historical measurement files remain untouched.
    """
    if not dataset.get('results_dir'):
        return None
    base = Path(dataset['results_dir'])/'verification_masks'
    tile, object_id = str(row['Tile_Name']), int(row['Object_ID'])
    manifest = base/'object_locations.json'
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding='utf-8'))
        entries = [r for r in data.get('objects', []) if r.get('tile_name') == tile and r.get('object_id') == object_id]
        if data.get('schema_version') != 1 or len(entries) != 1:
            return None
        entry = entries[0]
        mask = _gray(dataset_path(base, entry['mask']))
        origin = entry['origin_xy']
        height, width = entry['tile_shape']
        if mask is None or len(origin) != 2 or not all(isinstance(v, int) for v in [*origin, height, width]):
            return None
        if not mask.any() or abs(np.count_nonzero(mask) - float(row.get('Area', np.count_nonzero(mask)))) > .01:
            return None
        ys, xs = np.nonzero(mask)
        if (height <= 0 or width <= 0 or origin[0]+xs.min() < 0 or origin[1]+ys.min() < 0
                or origin[0]+xs.max() >= width or origin[1]+ys.max() >= height):
            return None
        coordinate_size = (width, height)
        if space == 'model' and entry['measurement_space'] == 'source_pixels':
            coordinate_size = tuple(record['transform']['padded_native_shape'][::-1])
        return dict(mask=mask > 0, origin=origin, coordinate_size=coordinate_size, recovered=False)
    # Older grayscale review crops preserve foreground intensities but discard
    # their position. Match those known pixels exactly; ignore synthetic zeros.
    files = sorted(dataset_path(base, tile).glob(f'obj_{object_id:03d}_*.png'))
    if len(files) != 1:
        return None
    template = _gray(files[0])
    image_path, actual_space = resolve_tile_image(dataset, record)
    image = _gray(image_path)
    if template is None or image is None or image.size > 32_000_000:
        return None
    ys, xs = np.nonzero(template)
    if len(xs) < 3:
        return None
    x0, x1, y0, y1 = xs.min(), xs.max()+1, ys.min(), ys.max()+1
    template = template[y0:y1, x0:x1]
    known = template > 0
    h, w = template.shape
    if h > image.shape[0] or w > image.shape[1]:
        return None
    errors = cv2.matchTemplate(image.astype(np.float32), template.astype(np.float32),
                               cv2.TM_SQDIFF, mask=known.astype(np.uint8))
    # FFT rounding affects the candidate score. Equality below, in uint8,
    # establishes an exact match. A bounded candidate list prevents UI stalls.
    candidates = np.argwhere(np.isfinite(errors) & (errors <= max(1, len(xs)*.1)))
    if len(candidates) > 10000:
        return None
    matches = []
    for y, x in candidates:
        if np.array_equal(image[y:y+h, x:x+w][known], template[known]):
            matches.append((int(x), int(y)))
            if len(matches) > 1:
                return None
    if len(matches) != 1 or actual_space != space:
        return None
    return dict(mask=known, origin=matches[0], coordinate_size=image.shape[::-1], recovered=True)


def resolve_result_tile(dataset, row, records):
    """Return (path, space) for the exact manifest entry named by a CSV row.

    Native crops preserve the pixels used for v3 measurements. A model canvas
    is a visibly labelled fallback when only that image remains available.
    CSV object IDs do not encode a position and must never become an overlay.
    """
    return resolve_tile_image(dataset, find_result_tile_record(row, records))


def find_result_tile_record(row, records):
    """Match the measured tile name to exactly one manifest record."""
    tile_name = str((row or {}).get('Tile_Name', ''))
    matches = [record for record in records
               if Path(str(record.get('filename', ''))).stem == tile_name]
    if not tile_name or len(matches) != 1:
        raise ValueError(tr('The selected object has no unambiguous tile in this dataset.'))
    return matches[0]


def resolve_tile_image(dataset, record):
    """Prefer the native crop; a model image may have moved during tile review."""
    base = dataset['path']
    native = record.get('native_filename')
    if native:
        path = tile_artifact_path(base, record, 'native_filename')
        if path.is_file():
            return path, 'native'
    model = record['filename']
    for relative in (record.get('edit_artifacts', {}).get('filename', model), 'excluded_tiles/' + model):
        path = dataset_path(base, relative)
        if path.is_file():
            return path, 'model'
    raise FileNotFoundError(tr('The tile image is missing. Restore its native or model image and try again.'))
