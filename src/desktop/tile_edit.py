"""Pixel-preserving working copies of model and native tiles."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np

from src.partition_geometry import dataset_path, png_shape
from src.default_settings import EDITOR_DEFAULTS, EDITOR_DEFAULTS_VERSION
from src.tile_scale import fixed_canvas
from src.tile_edits import (ACTIVE_EDITS_FILE, EDIT_ARTIFACTS, active_tile_edits,
                            effective_tile_record, file_sha256, tile_artifact_path)
from .i18n import register_translations, tr
from .project import atomic_json, timestamp
from .storage_names import readable_name, version_path


ERASE_RADIUS = (0, 150, EDITOR_DEFAULTS['erase_radius'])
PAINT_RADIUS = (0, 150, EDITOR_DEFAULTS['paint_radius'])
BACKGROUND_RADIUS = (1, 85, EDITOR_DEFAULTS['background_radius'])
GAMMA_RANGE = (0.25, 4.0, EDITOR_DEFAULTS['gamma'])
MAX_MASK_PIXELS = 32_000_000
UNDO_BYTES = 128 * 1024**2

register_translations({
    'This tile changed in another window. Reopen it before saving.': 'Тайл изменился в другом окне. Откройте его заново перед сохранением.',
    'Another tile edit is being saved. Try again.': 'Сохраняется другая правка тайла. Повторите попытку.',
    'Only a project-owned dataset can use edited tiles.': 'Правки можно применять только к набору внутри проекта.',
    'Open the native tile to save edits for measurement.': 'Откройте native-тайл для сохранения правок в измерения.',
    'This saved edit belongs to another tile or dataset.': 'Эта сохранённая правка относится к другому тайлу или набору.',
    'The prepared pixels differ from this saved edit.': 'Исходные пиксели отличаются от основы сохранённой правки.',
    'This resized model copy cannot become native measurement data. Redo the edit on the native tile.': 'Уменьшенную модельную копию нельзя использовать как native-данные измерений. Повторите правку на native-тайле.',
    'The saved edit has invalid image dimensions or ownership.': 'У сохранённой правки неверные размеры или принадлежность пикселей.',
}, hebrew={
    'This tile changed in another window. Reopen it before saving.': 'האריח השתנה בחלון אחר. פתחו אותו מחדש לפני שמירה.',
    'Another tile edit is being saved. Try again.': 'עריכה אחרת של אריח נשמרת כעת. נסו שוב.',
    'Only a project-owned dataset can use edited tiles.': 'אפשר להחיל עריכות רק במערך שנמצא בתוך הפרויקט.',
    'Open the native tile to save edits for measurement.': 'פתחו את אריח המקור כדי לשמור עריכות למדידה.',
    'This saved edit belongs to another tile or dataset.': 'העריכה השמורה שייכת לאריח או למערך אחר.',
    'The prepared pixels differ from this saved edit.': 'פיקסלי ההכנה שונים מהבסיס של העריכה השמורה.',
    'This resized model copy cannot become native measurement data. Redo the edit on the native tile.': 'אי אפשר להשתמש בעותק המודל המוקטן כנתוני מקור למדידה. חזרו על העריכה באריח המקור.',
    'The saved edit has invalid image dimensions or ownership.': 'לעריכה השמורה יש ממדים או שיוך פיקסלים לא תקינים.',
})


@dataclass(frozen=True)
class TileEditContext:
    """Manifest identity and coordinate space of the tile shown in the viewer."""
    workspace: str
    dataset_id: str
    dataset_dir: str
    record: dict
    space: str
    expected_revision: str = None
    editor_defaults: dict | None = None


def _read_png(path):
    data = path.read_bytes()
    pixels = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    return pixels, hashlib.sha256(data).hexdigest()


def _write_png(path, pixels):
    ok, data = cv2.imencode('.png', pixels)
    if not ok:
        raise OSError(tr('Could not encode the edited PNG.'))
    path.write_bytes(data.tobytes())


def _region(box):
    """Convert a half-open XY rectangle to NumPy's row/column indexing."""
    left, top, right, bottom = box
    return np.s_[top:bottom, left:right]


class TileEdit:
    """Track operations and bounded undo without rewriting prepared pixel files."""

    def __init__(self, filename, context):
        self.context = context
        self._expected_revision = context.expected_revision
        self.source = Path(filename).resolve()
        base = Path(context.dataset_dir).resolve()
        self.relative_source = self.source.relative_to(base).as_posix()
        self.pixels, self.source_hash = _read_png(self.source)
        if self.pixels is None or self.pixels.ndim != 2 or self.pixels.dtype not in (np.uint8, np.uint16):
            raise ValueError(tr('Tile editing requires an 8-bit or 16-bit grayscale PNG.'))
        self.relative_mask = context.record.get('edit_artifacts', {}).get('valid_mask', context.record['valid_mask'])
        mask_file = dataset_path(base, self.relative_mask)
        height, width = png_shape(mask_file)
        transform = context.record.get('transform') if context.space == 'model' else None
        padded_h, padded_w = transform['padded_native_shape'] if transform else (height, width)
        if max(height * width, padded_h * padded_w) > MAX_MASK_PIXELS:
            raise ValueError(tr('The tile ownership mask exceeds the 32 MP editor limit.'))
        mask, self.mask_hash = _read_png(mask_file)
        if mask is None or mask.shape != (height, width):
            raise ValueError(tr('The tile ownership mask is unreadable.'))
        if transform:
            # Float coverage retains even contributions below 1/255 on a resized tile.
            mask = fixed_canvas((mask > 0).astype(np.float32), transform, mask=True)
        if mask.shape != self.pixels.shape:
            raise ValueError(tr('The tile ownership mask does not match this canvas.'))
        self.valid = mask > 0
        self.operations = []
        self._undo = []
        self._undo_bytes = 0

    @property
    def can_undo(self):
        return bool(self._undo)

    def _remember(self, box, operation, *, removes_pixels=False):
        # Tone operations change only intensities. Erasures also need a copy
        # of the affected ownership mask to restore the previous selection.
        region = _region(box)
        pixels = self.pixels[region].copy()
        valid = self.valid[region].copy() if removes_pixels else None
        size = pixels.nbytes + (valid.nbytes if valid is not None else 0)
        while self._undo and self._undo_bytes + size > UNDO_BYTES:
            self._undo_bytes -= self._undo.pop(0)[-1]
        self._undo.append((box, pixels, valid, size))
        self._undo_bytes += size
        self.operations.append(operation)

    def _erase_selection(self, box, selected, operation):
        if not selected.any():
            return False
        self._remember(box, operation, removes_pixels=True)
        region = _region(box)
        self.pixels[region][selected] = 0
        self.valid[region][selected] = False
        return True

    def erase(self, points, radius, mode):
        """Rasterize a stroke in its bounding box and erase owned pixels inside it."""
        box, footprint = self._stroke(points, radius)
        selected = footprint & self.valid[_region(box)]
        return self._erase_selection(box, selected, dict(tool=mode, points=points, radius_px=radius))

    def _stroke(self, points, radius):
        """Use the same Euclidean brush footprint for drawing and erasing."""
        height, width = self.pixels.shape
        xs, ys = zip(*points)
        left, top = max(0, min(xs) - radius), max(0, min(ys) - radius)
        right, bottom = min(width, max(xs) + radius + 1), min(height, max(ys) + radius + 1)
        box = (left, top, right, bottom)
        region = _region(box)
        path = np.asarray(points, dtype=np.int32) - np.array([left, top], dtype=np.int32)
        stroke = np.ones((bottom - top, right - left), dtype=np.uint8)
        stroke[path[0, 1], path[0, 0]] = 0
        cv2.polylines(stroke, [path], False, 0, thickness=1, lineType=cv2.LINE_8)
        if radius:
            # distanceTransform measures from each pixel to the zero-valued
            # centerline. The radius defines the Euclidean stroke footprint.
            distance = cv2.distanceTransform(stroke, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
            footprint = distance <= radius
        else:
            footprint = stroke == 0
        return box, footprint

    def paint(self, points, radius, intensity, sampled_at=None):
        """Set owned pixels to a sampled value and record the synthetic signal."""
        ceiling = np.iinfo(self.pixels.dtype).max
        if not isinstance(intensity, (int, np.integer)) or not 0 <= intensity <= ceiling:
            raise ValueError('Paint intensity is outside the native bit-depth range')
        box, footprint = self._stroke(points, radius)
        region = _region(box)
        selected = footprint & self.valid[region]
        if not np.any(selected & (self.pixels[region] != intensity)):
            return False
        self._remember(box, dict(tool='paint_signal', points=points, radius_px=radius,
                                 intensity=int(intensity), sampled_at=sampled_at,
                                 synthetic_signal=True))
        self.pixels[region][selected] = intensity
        return True

    def _cut_axes(self, first, last):
        """Two broadcast terms of the signed cross product at each pixel center."""
        height, width = self.pixels.shape
        x0, y0 = first
        x1, y1 = last
        xs = (np.arange(width, dtype=np.int32) - x0) * (y1 - y0)
        ys = (np.arange(height, dtype=np.int32) - y0) * (x1 - x0)
        return ys[:, None], xs[None, :]

    def smaller_cut_side(self, first, last):
        """Find the smaller nonempty side by valid pixels. Ties require a manual choice."""
        ys, xs = self._cut_axes(first, last)
        positive = np.count_nonzero(self.valid & (ys > xs))
        negative = np.count_nonzero(self.valid & (ys < xs))
        if not positive or not negative or positive == negative:
            return None
        return 1 if positive < negative else -1

    def cut_side(self, first, last, side):
        """Pad one strict half-plane of the infinite line through the two pixels."""
        if side not in (-1, 1):
            return False
        ys, xs = self._cut_axes(first, last)
        selected = ys > xs if side == 1 else ys < xs
        selected &= self.valid
        rows = selected.any(axis=1)
        if not rows.any():
            return False
        columns = selected.any(axis=0)
        box = (int(columns.argmax()), int(rows.argmax()),
               columns.size - int(columns[::-1].argmax()), rows.size - int(rows[::-1].argmax()))
        operation = dict(tool='cut_side', points=[tuple(first), tuple(last)], side=int(side))
        return self._erase_selection(box, selected[_region(box)], operation)

    def remove_background(self, box, radius):
        """Subtract the local opening on owned pixels while preserving native depth."""
        left, top, right, bottom = box
        height, width = self.pixels.shape
        # Opening has two passes; a 2r halo keeps the selection border out of both.
        x0, y0 = max(0, left - 2 * radius), max(0, top - 2 * radius)
        x1, y1 = min(width, right + 2 * radius), min(height, bottom + 2 * radius)
        context = np.s_[y0:y1, x0:x1]
        valid = self.valid[context]
        region = _region(box)
        selected = self.valid[region]
        if not selected.any():
            return False
        work = self.pixels[context].copy()
        # Make unowned pixels neutral to the min pass, then neutral to the max
        # pass. Padding should contribute neither a dark pit nor a bright peak.
        work[~valid] = np.iinfo(work.dtype).max
        diameter = 2 * radius + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (diameter, diameter))
        eroded = cv2.erode(work, kernel)
        eroded[~valid] = 0
        background = cv2.dilate(eroded, kernel)[top - y0:bottom - y0, left - x0:right - x0]
        residual = cv2.subtract(self.pixels[region], background)
        if not np.any((residual != self.pixels[region]) & selected):
            return False
        self._remember(box, dict(tool='background', bounds_ltrb=box, radius_px=radius))
        self.pixels[region][selected] = residual[selected]
        return True

    def _gamma_region(self, gamma, region):
        lower, upper, neutral = GAMMA_RANGE
        if not lower <= gamma <= upper:
            raise ValueError(tr('Gamma is outside the editor range.'))
        pixels = self.pixels[region]
        adjusted = pixels.copy()
        if gamma != neutral:
            ceiling = np.iinfo(pixels.dtype).max
            values = np.arange(ceiling + 1, dtype=np.float64) / ceiling
            lookup = (values ** (1.0 / gamma) * ceiling).astype(pixels.dtype)
            valid = self.valid[region]
            adjusted[valid] = lookup[pixels[valid]]
        return adjusted

    def gamma_preview(self, gamma, box=None):
        """Preview the tone change without adding an operation or changing the mask."""
        if box is None:
            return self._gamma_region(gamma, np.s_[:, :])
        region = _region(box)
        preview = self.pixels.copy()
        preview[region] = self._gamma_region(gamma, region)
        return preview

    def apply_gamma(self, gamma, box=None):
        if box is None:
            height, width = self.pixels.shape
            box = (0, 0, width, height)
        region = _region(box)
        adjusted = self._gamma_region(gamma, region)
        if np.array_equal(self.pixels[region], adjusted):
            return False
        self._remember(box, dict(tool='gamma', gamma=float(gamma), bounds_ltrb=box))
        self.pixels[region] = adjusted
        return True

    def undo(self):
        box, pixels, valid, size = self._undo.pop()
        self._undo_bytes -= size
        self.operations.pop()
        region = _region(box)
        self.pixels[region] = pixels
        if valid is not None:
            self.valid[region] = valid

    def save(self):
        """Publish one versioned image, ownership mask and edit record together."""
        if self.context.record.get('native_filename') and self.context.record.get('transform'):
            if self.context.space != 'native':
                raise ValueError(tr('Open the native tile to save edits for measurement.'))
            if (file_sha256(self.source) != self.source_hash
                    or file_sha256(dataset_path(self.context.dataset_dir, self.relative_mask)) != self.mask_hash):
                raise ValueError(tr('The prepared pixels differ from this saved edit.'))
            from dataclasses import replace
            context = replace(self.context, expected_revision=self._expected_revision)
            target = publish_active_tile(context, self.pixels, self.valid, dict(
                source_image=self.relative_source, source_sha256=self.source_hash,
                source_mask=self.relative_mask, source_mask_sha256=self.mask_hash,
                pixel_coordinates='zero_based_xy', rectangle_bounds='right_and_bottom_exclusive',
                operations=self.operations))
            self._expected_revision = target.relative_to(Path(context.dataset_dir).resolve()).as_posix()
            return target
        tile = readable_name(Path(self.context.record['filename']).stem)
        parent = dataset_path(self.context.workspace, f'tile_edits/{tile}')
        parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix='.edit-', dir=parent) as temporary:
            staged = Path(temporary)
            _write_png(staged / 'tile.png', self.pixels)
            _write_png(staged / 'valid_mask.png', self.valid.astype(np.uint8) * 255)
            atomic_json(staged / 'edit.json', dict(
                schema_version=1, editor_defaults_version=EDITOR_DEFAULTS_VERSION,
                created_at=timestamp(), dataset_id=self.context.dataset_id,
                tile_id=self.context.record['id'], source_image=self.relative_source,
                source_sha256=self.source_hash, source_mask=self.relative_mask,
                source_mask_sha256=self.mask_hash, space=self.context.space,
                source_bounds_ltrb=[self.context.record.get(key) for key in ('x1', 'y1', 'x2', 'y2')],
                transform=self.context.record.get('transform'), shape=self.pixels.shape,
                dtype=self.pixels.dtype.name, pixel_coordinates='zero_based_xy',
                rectangle_bounds='right_and_bottom_exclusive', operations=self.operations,
            ))
            # Publish the PNG, validity mask and provenance together. A simultaneous
            # save can win the name, in which case this copy takes the next version.
            while True:
                target = version_path(parent, 'Edit')
                try:
                    os.rename(staged, target)
                    return target
                except OSError:
                    if staged.exists() and target.exists():
                        continue
                    raise


def _owned_dataset(context):
    base = Path(context.dataset_dir).resolve()
    workspace = Path(context.workspace).resolve()
    if workspace not in base.parents and base != workspace:
        raise ValueError(tr('Only a project-owned dataset can use edited tiles.'))
    return base


def activate_tile_version(context, version):
    """Compare and switch one pointer under a short lock after all files exist."""
    from .qt import QtCore
    base = _owned_dataset(context)
    lock = QtCore.QLockFile(str(base / '.tile_edits.lock'))
    if not lock.tryLock(0):
        raise ValueError(tr('Another tile edit is being saved. Try again.'))
    try:
        active = active_tile_edits(base)
        key = str(context.record['id'])
        if active.get(key, {}).get('version') != context.expected_revision:
            raise ValueError(tr('This tile changed in another window. Reopen it before saving.'))
        if version is None:
            active.pop(key, None)
        else:
            folder = dataset_path(base, version)
            effective_tile_record(base, context.record, {key: dict(version=version)})
            active[key] = dict(version=version, sha256={
                name: file_sha256(folder / name) for name in (*EDIT_ARTIFACTS.values(), 'edit.json')})
        registry = base / ACTIVE_EDITS_FILE
        old = json.loads(registry.read_text(encoding='utf-8')) if registry.exists() else {}
        history = old.get('history', []) + [dict(time=timestamp(), tile_id=context.record['id'], version=version)]
        atomic_json(registry, dict(schema_version=1, tiles=active, history=history))
    finally:
        lock.unlock()


def publish_active_tile(context, pixels, valid, metadata):
    """Publish source-scale pixels and regenerate their fixed model canvas together."""
    base = _owned_dataset(context)
    transform = context.record['transform']
    if np.prod(transform['padded_native_shape'], dtype=np.int64) > MAX_MASK_PIXELS:
        raise ValueError(tr('The tile ownership mask exceeds the 32 MP editor limit.'))
    if list(pixels.shape) != transform['native_crop_shape'] or valid.shape != pixels.shape:
        raise ValueError(tr('The saved edit has invalid image dimensions or ownership.'))
    prepared_mask, _ = _read_png(dataset_path(base, context.record['valid_mask']))
    if prepared_mask is None or prepared_mask.shape != valid.shape or np.any(valid & (prepared_mask == 0)):
        raise ValueError(tr('The saved edit has invalid image dimensions or ownership.'))
    pixels = pixels.copy()
    pixels[~valid] = 0
    parent = dataset_path(base, 'tile_edits/' + readable_name(Path(context.record['filename']).stem))
    parent.mkdir(parents=True, exist_ok=True)
    previous = {}
    if context.expected_revision:
        previous = json.loads((dataset_path(base, context.expected_revision)/'edit.json').read_text(encoding='utf-8'))
    synthetic = metadata.get('contains_synthetic_signal', False) or previous.get('contains_synthetic_signal', False) or any(
        op.get('synthetic_signal', False) for op in metadata.get('operations', []))
    with TemporaryDirectory(prefix='.edit-', dir=parent) as temporary:
        staged = Path(temporary)
        _write_png(staged / 'native.png', pixels)
        _write_png(staged / 'valid_mask.png', valid.astype(np.uint8) * 255)
        _write_png(staged / 'model.png', fixed_canvas(pixels, transform))
        _write_png(staged / 'coverage.png', fixed_canvas(valid.astype(np.uint8) * 255, transform, mask=True))
        metadata.update(schema_version=2, editor_defaults_version=EDITOR_DEFAULTS_VERSION,
                        created_at=timestamp(), dataset_id=context.dataset_id, tile_id=context.record['id'],
                        tile_filename=context.record['filename'], transform=transform,
                        shape=list(pixels.shape), dtype=pixels.dtype.name, valid_pixels=int(valid.sum()),
                        removed_prepared_pixels=int(np.count_nonzero(prepared_mask) - valid.sum()),
                        contains_synthetic_signal=bool(synthetic),
                        parent_revision=context.expected_revision, space='native',
                        prepared_native_sha256=file_sha256(dataset_path(base, context.record['native_filename'])),
                        prepared_mask_sha256=file_sha256(dataset_path(base, context.record['valid_mask'])),
                        preservation='manual edits can remove pixels or synthesize signal within owned pixels')
        atomic_json(staged / 'edit.json', metadata)
        while True:
            target = version_path(parent, 'Edit')
            try:
                os.rename(staged, target)
                break
            except OSError:
                if staged.exists() and target.exists():
                    continue
                raise
    activate_tile_version(context, target.relative_to(base).as_posix())
    return target


def import_saved_tile_edit(context, metadata_file):
    """Activate an older copy only when its source pixels and scale are provable."""
    base = _owned_dataset(context)
    source = Path(metadata_file).resolve()
    metadata = json.loads(source.read_text(encoding='utf-8'))
    record = context.record
    if metadata.get('dataset_id') != context.dataset_id or metadata.get('tile_id') != record['id']:
        raise ValueError(tr('This saved edit belongs to another tile or dataset.'))
    transform = record['transform']
    if metadata.get('transform') != transform:
        raise ValueError(tr('The saved edit has invalid image dimensions or ownership.'))
    if metadata.get('schema_version') == 2:
        if (metadata.get('prepared_native_sha256') != file_sha256(dataset_path(base, record['native_filename']))
                or metadata.get('prepared_mask_sha256') != file_sha256(dataset_path(base, record['valid_mask']))):
            raise ValueError(tr('The prepared pixels differ from this saved edit.'))
        pixels, _ = _read_png(source.parent / 'native.png')
    elif metadata.get('schema_version') == 1:
        allowed_sources = (record['native_filename'], record['filename'], 'excluded_tiles/' + record['filename'])
        relative = metadata.get('source_image')
        if relative not in allowed_sources or metadata.get('source_sha256') != file_sha256(dataset_path(base, relative)):
            raise ValueError(tr('The prepared pixels differ from this saved edit.'))
        if metadata.get('source_mask_sha256') != file_sha256(dataset_path(base, record['valid_mask'])):
            raise ValueError(tr('The prepared pixels differ from this saved edit.'))
        if metadata.get('space') == 'model' and transform['source_pixels_per_output_pixel'] != 1.0:
            raise ValueError(tr('This resized model copy cannot become native measurement data. Redo the edit on the native tile.'))
        pixels, _ = _read_png(source.parent / 'tile.png')
    else:
        raise ValueError(tr('The saved edit has invalid image dimensions or ownership.'))
    valid, _ = _read_png(source.parent / 'valid_mask.png')
    if pixels is None or valid is None or pixels.ndim != 2 or valid.shape != pixels.shape:
        raise ValueError(tr('The saved edit has invalid image dimensions or ownership.'))
    native, _ = _read_png(dataset_path(base, record['native_filename']))
    expected = transform['output_shape'] if metadata.get('space') == 'model' else transform['native_crop_shape']
    if list(pixels.shape) != expected or pixels.dtype != native.dtype:
        raise ValueError(tr('The saved edit has invalid image dimensions or ownership.'))
    height, width = transform['native_crop_shape']
    return publish_active_tile(context, pixels[:height, :width], valid[:height, :width] > 0, dict(
        operations=metadata.get('operations', []), imported_copy=str(source),
        contains_synthetic_signal=metadata.get('contains_synthetic_signal', False),
        imported_copy_sha256=file_sha256(source), pixel_coordinates='zero_based_xy',
        rectangle_bounds='right_and_bottom_exclusive'))
