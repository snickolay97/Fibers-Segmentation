"""Exact partition geometry shared by slicing and overview reconstruction."""
import json
import re
import struct
import tempfile
from pathlib import Path
import cv2
import numpy as np


def checked_imwrite(path, image):
    if not cv2.imwrite(str(path), image):
        raise IOError("Could not write image: {}".format(path))


def connected_components_striped(mask, labels, stripe_height=256):
    """8-connected labels with bounded RAM; labels may be a disk-backed array."""
    h, w = mask.shape
    parent = [0]
    boxes = [[0, 0, 0, 0, 0]]

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for y in range(0, h, stripe_height):
        block = np.ascontiguousarray(mask[y:min(y + stripe_height, h)] > 0, dtype=np.uint8)
        n, local, stats, _ = cv2.connectedComponentsWithStats(block, connectivity=8)
        offset = len(parent) - 1
        for k in range(1, n):
            x, yy, ww, hh, area = [int(v) for v in stats[k]]
            parent.append(offset + k)
            boxes.append([x, y + yy, x + ww, y + yy + hh, area])
        local[local > 0] += offset
        if y:
            previous = labels[y - 1]
            current = local[0]
            for delta in (-1, 0, 1):
                a = previous[max(0, delta):min(w, w + delta)]
                b = current[max(0, -delta):min(w, w - delta)]
                valid = (a > 0) & (b > 0)
                if not valid.any():
                    continue
                for aa, bb in np.unique(np.stack((a[valid], b[valid]), axis=1), axis=0):
                    ra, rb = find(int(aa)), find(int(bb))
                    if ra != rb:
                        parent[rb] = ra
        labels[y:y + len(local)] = local
    roots = np.array([find(k) for k in range(len(parent))], dtype=np.int32)
    _, remap = np.unique(roots, return_inverse=True)
    remap = remap.astype(np.int32)
    count = int(remap.max()) + 1
    combined = np.zeros((count, 5), dtype=np.int64)
    combined[:, :2] = [w, h]
    for k in range(1, len(boxes)):
        j = remap[k]
        b = boxes[k]
        combined[j, :2] = np.minimum(combined[j, :2], b[:2])
        combined[j, 2:4] = np.maximum(combined[j, 2:4], b[2:4])
        combined[j, 4] += b[4]
    for y in range(0, h, stripe_height):
        labels[y:y + stripe_height] = remap[labels[y:y + stripe_height]]
    return combined


def ownership_boundary(owners):
    """One-pixel boundary on the lower/right side of each ownership transition."""
    edges = np.zeros(owners.shape, dtype=bool)
    edges[:, 1:] |= (owners[:, 1:] != owners[:, :-1]) & ((owners[:, 1:] > 0) | (owners[:, :-1] > 0))
    edges[1:, :] |= (owners[1:, :] != owners[:-1, :]) & ((owners[1:, :] > 0) | (owners[:-1, :] > 0))
    return edges


def render_overview(raw, owners, records, target_dim):
    h, w = owners.shape
    scale = min(1.0, float(target_dim) / max(h, w))
    size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
    canvas = cv2.resize(raw, size, interpolation=cv2.INTER_AREA)
    if canvas.ndim == 2:
        canvas = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
    # OpenCV does not resize int32 labels. Exact nearest-neighbour index lookup
    # also avoids conversion to float, which would lose sufficiently large IDs.
    ys = np.minimum((np.arange(size[1]) / scale).astype(int), h - 1)
    xs = np.minimum((np.arange(size[0]) / scale).astype(int), w - 1)
    small = owners[np.ix_(ys, xs)]
    canvas[ownership_boundary(small)] = (0, 220, 220)
    for rec in records:
        x1, y1 = max(0, int(rec['x1'] * scale)), max(0, int(rec['y1'] * scale))
        x2, y2 = min(size[0], int(np.ceil(rec['x2'] * scale))), min(size[1], int(np.ceil(rec['y2'] * scale)))
        local = (small[y1:y2, x1:x2] == rec['id']).astype(np.uint8)
        if local.size == 0 or not local.any():
            continue
        dist = cv2.distanceTransform(cv2.copyMakeBorder(local, 1, 1, 1, 1, cv2.BORDER_CONSTANT), cv2.DIST_L2, 3)[1:-1, 1:-1]
        yy, xx = np.unravel_index(np.argmax(dist), dist.shape)
        text = '#{:04d}'.format(rec['id'])
        font_scale = max(0.35, min(0.8, size[0] / 7000.0))
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        # Omit labels in slivers instead of placing them in a neighbouring tile.
        tx, ty = x1 + xx - tw // 2, y1 + yy + th // 2
        if tx >= 0 and ty - th >= 0 and tx + tw < size[0] and ty < size[1] and np.all(small[ty-th:ty+1, tx:tx+tw+1] == rec['id']):
            cv2.putText(canvas, text, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(canvas, text, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 0), 1, cv2.LINE_AA)
    return canvas


def read_manifest(path):
    with open(str(path), encoding='utf-8') as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict) or manifest.get('schema_version') not in (2,3):
        raise ValueError('Exact reconstruction requires a v2/v3 manifest and valid masks. Re-slice the legacy dataset.')
    return manifest


def dataset_path(base_dir, relative_path):
    """Resolve an artifact path without permitting escape from its dataset."""
    base = Path(base_dir).resolve()
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError('Dataset artifact path must be a nonempty relative path')
    normalized = relative_path.replace('\\', '/')
    if normalized.startswith('/') or ':' in normalized or any(p in ('', '.', '..') for p in normalized.split('/')):
        raise ValueError('Unsafe dataset artifact path: {}'.format(relative_path))
    path = (base / normalized).resolve()
    if base not in path.parents:
        raise ValueError('Dataset artifact path escapes its directory: {}'.format(relative_path))
    return path


def png_shape(path):
    """Read the PNG dimensions without decoding a potentially enormous crop."""
    path = Path(path)
    if not path.is_file():
        raise ValueError('Missing PNG: {}'.format(path))
    with path.open('rb') as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR':
        raise ValueError('Invalid PNG header: {}'.format(path))
    width, height = struct.unpack('>II', header[16:24])
    if not width or not height:
        raise ValueError('Invalid PNG dimensions: {}'.format(path))
    return height, width


def find_dataset_manifest(base_dir):
    base = Path(base_dir).resolve()
    candidates = sorted((base / 'overview').glob('*_tiles_coords.json'))
    if len(candidates) != 1:
        raise ValueError('Dataset must have exactly one tiles manifest: {}'.format(base))
    return dataset_path(base, candidates[0].relative_to(base).as_posix())


def validate_dataset(base_dir, manifest=None, require_v3=True, check_pixels=False):
    """Validate a saved dataset, including excluded models; never mutate it.

    The default validates file headers and metadata. ``check_pixels`` also
    decodes every image and verifies exact coverage and model rendering.
    """
    from src.tile_scale import scale_metadata, fixed_canvas
    base = Path(base_dir).resolve()
    if not base.is_dir():
        raise ValueError('Dataset directory does not exist: {}'.format(base))
    if manifest is None:
        manifest = read_manifest(find_dataset_manifest(base))
    supported = (3,) if require_v3 else (2, 3)
    if not isinstance(manifest, dict) or manifest.get('schema_version') not in supported:
        raise ValueError('Dataset requires a {} manifest'.format('v3' if require_v3 else 'v2/v3'))
    version = manifest['schema_version']
    source_name = manifest.get('source_name')
    if source_name is not None and (not isinstance(source_name,str) or not re.fullmatch(r'[^/\\:]+',source_name) or source_name in ('.','..')):
        raise ValueError('Invalid manifest source_name')
    shape = manifest.get('image_shape')
    integer = lambda value: isinstance(value, int) and not isinstance(value, bool)
    if not isinstance(shape, list) or len(shape) != 2 or any(not integer(v) or v <= 0 for v in shape):
        raise ValueError('Manifest image_shape must contain two positive integers')
    h, w = shape
    records = manifest.get('tiles')
    if not isinstance(records, list) or not records:
        raise ValueError('Manifest must contain tile records')
    ids, filenames = set(), set()
    for rec in records:
        if not isinstance(rec, dict):
            raise ValueError('Invalid tile record')
        ident = rec.get('id')
        if not integer(ident) or ident <= 0 or ident in ids:
            raise ValueError('Tile IDs must be unique positive integers')
        ids.add(ident)
        coords = [rec.get(k) for k in ('x1', 'y1', 'x2', 'y2')]
        if any(not integer(v) for v in coords):
            raise ValueError('Tile {} has invalid coordinates'.format(ident))
        x1, y1, x2, y2 = coords
        if not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h):
            raise ValueError('Tile {} coordinates lie outside source'.format(ident))
        crop_shape = (y2-y1, x2-x1)
        filename = rec.get('filename')
        model = dataset_path(base, filename)
        match = re.fullmatch(r'[^/\\]+_tile_(\d+)\.png', filename)
        if not match or int(match.group(1)) != ident or filename in filenames:
            raise ValueError('Tile filename must contain its unique ID: {}'.format(filename))
        filenames.add(filename)
        excluded = dataset_path(base, 'excluded_tiles/' + filename)
        if model.is_file() and excluded.is_file():
            raise ValueError('Tile exists in both active and excluded folders: {}'.format(filename))
        model = model if model.is_file() else excluded
        model_shape = png_shape(model)
        valid = dataset_path(base, rec.get('valid_mask'))
        if png_shape(valid) != crop_shape:
            raise ValueError('Valid mask shape differs from crop: {}'.format(valid))
        count = rec.get('valid_pixels')
        if not integer(count) or not 0 < count <= crop_shape[0]*crop_shape[1]:
            raise ValueError('Invalid valid_pixels for tile {}'.format(ident))
        if version == 3:
            native = dataset_path(base, rec.get('native_filename'))
            if png_shape(native) != crop_shape:
                raise ValueError('Native image shape differs from crop: {}'.format(native))
            transform = rec.get('transform')
            if not isinstance(transform, dict):
                raise ValueError('Missing transform for tile {}'.format(ident))
            target = transform.get('output_shape')
            if not isinstance(target, list) or len(target) != 2 or any(not integer(v) or v <= 0 for v in target) or target[0] != target[1]:
                raise ValueError('Invalid model canvas for tile {}'.format(ident))
            if model_shape != tuple(target) or rec.get('canvas_shape') != target:
                raise ValueError('Model canvas shape mismatch: {}'.format(model))
            expected = scale_metadata(*crop_shape, target[0])
            for key, value in expected.items():
                if isinstance(value, float):
                    actual = transform.get(key)
                    if not isinstance(actual, (int, float)) or not np.isfinite(actual) or not np.isclose(actual, value, rtol=1e-12):
                        raise ValueError('Invalid {} for tile {}'.format(key, ident))
                elif transform.get(key) != value:
                    raise ValueError('Invalid {} for tile {}'.format(key, ident))
        elif model_shape[0] < crop_shape[0] or model_shape[1] < crop_shape[1]:
            raise ValueError('Legacy model smaller than crop: {}'.format(model))
        if rec.get('coverage_mask'):
            coverage = dataset_path(base, rec['coverage_mask'])
            if png_shape(coverage) != model_shape:
                raise ValueError('Coverage shape differs from model: {}'.format(coverage))
    if sum(rec['valid_pixels'] for rec in records) != h*w:
        raise ValueError('Manifest valid_pixels do not sum to source area')
    if check_pixels:
        with tempfile.TemporaryDirectory(prefix='fiber_validation_') as tmp:
            owners = np.memmap(Path(tmp)/'coverage.dat', dtype=np.uint8, mode='w+', shape=(h,w))
            try:
                owners[:] = 0
                for rec in records:
                    x1, y1, x2, y2 = [rec[k] for k in ('x1','y1','x2','y2')]
                    mask = cv2.imread(str(dataset_path(base, rec['valid_mask'])), cv2.IMREAD_UNCHANGED)
                    if mask is None or mask.ndim != 2 or np.any((mask != 0) & (mask != 255)):
                        raise ValueError('Unreadable or nonbinary valid mask: {}'.format(rec['valid_mask']))
                    valid = mask > 0
                    if int(valid.sum()) != rec['valid_pixels']:
                        raise ValueError('valid_pixels mismatch: {}'.format(rec['valid_mask']))
                    view = owners[y1:y2, x1:x2]
                    if np.any(view[valid]):
                        del view
                        raise ValueError('Overlapping valid masks')
                    view[valid] = 1
                    del view
                    if version == 3:
                        native = cv2.imread(str(dataset_path(base, rec['native_filename'])), cv2.IMREAD_UNCHANGED)
                        model_path = dataset_path(base, rec['filename'])
                        if not model_path.is_file():
                            model_path = dataset_path(base, 'excluded_tiles/'+rec['filename'])
                        model = cv2.imread(str(model_path), cv2.IMREAD_UNCHANGED)
                        if native is None or model is None or np.any(native[~valid]):
                            raise ValueError('Corrupt native/model or nonzero outside ownership: {}'.format(rec['filename']))
                        if not np.array_equal(fixed_canvas(native, rec['transform']), model):
                            raise ValueError('Model does not match native transform: {}'.format(rec['filename']))
                        del native, model
                    del mask, valid
                for y in range(0,h,256):
                    if np.any(owners[y:y+256] != 1):
                        raise ValueError('Valid masks leave uncovered source pixels')
            finally:
                owners.flush()
                owners._mmap.close()
    return manifest


def restore_ownership(base_dir, manifest, owners, active_ids=None):
    base = Path(base_dir).resolve()
    owners[:] = 0
    for rec in manifest['tiles']:
        if active_ids is not None and rec['id'] not in active_ids:
            continue
        path = (base / rec['valid_mask']).resolve()
        if base not in path.parents:
            raise ValueError('Mask path must stay inside the dataset')
        mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        x1, y1, x2, y2 = [rec[k] for k in ('x1', 'y1', 'x2', 'y2')]
        if not (0 <= x1 < x2 <= owners.shape[1] and 0 <= y1 < y2 <= owners.shape[0]):
            raise ValueError('Invalid tile coordinates')
        if mask is None or mask.shape != (y2 - y1, x2 - x1):
            raise ValueError('Missing or incorrectly sized valid mask: {}'.format(path))
        view = owners[y1:y2, x1:x2]
        valid = mask > 0
        if np.any(view[valid]):
            raise ValueError('Overlapping valid masks')
        view[valid] = rec['id']
