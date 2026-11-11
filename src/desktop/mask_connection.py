"""Native-grid mask corrections, independent of Qt and original intensities.

Routing prefers bright evidence inside a bounded ROI. It does not establish
biological continuity. Publication replays the same raster operations against
the current saved masks; Otsu is never reapplied to the accepted correction.
"""
from copy import deepcopy
from dataclasses import dataclass
import math

import cv2
import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.graph import route_through_array
from skimage.morphology import skeletonize

from src.default_settings import MASK_EDITOR_DEFAULTS as DEFAULTS
from .i18n import tr
from . import mask_correction_text


def component_count(mask):
    return int(ndi.label(mask, structure=np.ones((3, 3)))[1])


def endpoint_pairs(mask):
    """Rank ends from different components by distance and outward alignment.

    The ranking affects suggestions only; it never prunes the measurement
    skeleton or changes the existing Endpoints predictor semantics.
    """
    labels, _ = ndi.label(mask, structure=np.ones((3, 3)))
    skeleton = skeletonize(mask)
    neighbours = ndi.convolve(skeleton.astype(np.uint8), np.ones((3, 3), np.uint8), mode='constant')
    ys, xs = np.nonzero(skeleton & (neighbours == 2))  # Center plus one neighbor.
    if len(xs) > 4096:
        raise ValueError(tr('Too many ends. Select fewer parts or use the mask brush.'))
    ends = []
    for x, y in zip(xs, ys):
        left, top = max(0, x-8), max(0, y-8)
        sy, sx = np.nonzero(skeleton[top:y+9, left:x+9] &
                            (labels[top:y+9, left:x+9] == labels[y, x]))
        direction = np.array([x-(sx+left).mean(), y-(sy+top).mean()])
        norm = np.linalg.norm(direction)
        ends.append(dict(x=int(x), y=int(y), component=int(labels[y, x]),
                         direction=direction / norm if norm else np.zeros(2)))
    pairs = []
    if len(ends) > 1:
        xy = np.array([[e['x'], e['y']] for e in ends])
        # Query each other component separately: a component with many nearby
        # spurs must not hide every valid inter-component suggestion.
        groups = {}
        for i, e in enumerate(ends): groups.setdefault(e['component'], []).append(i)
        for indices in groups.values():
            tree = cKDTree(xy[indices])
            for i, a in enumerate(ends):
                if a['component'] == ends[indices[0]]['component']: continue
                _, nearest = tree.query(xy[i], k=min(4, len(indices)))
                for pos in np.atleast_1d(nearest):
                    j = indices[int(pos)]
                    if i >= j: continue
                    b = ends[j]; vector = xy[j]-xy[i]; distance = float(np.linalg.norm(vector))
                    unit = vector / max(distance, 1e-9)
                    penalty = (1-float(np.dot(a['direction'], unit))) + (1-float(np.dot(b['direction'], -unit)))
                    pairs.append(dict(first=i, last=j, distance=distance, score=distance*(1+.75*penalty)))
    pairs.sort(key=lambda p: (p['score'], p['distance'], p['first'], p['last']))
    return ends, pairs[:32]


def _validate_width(width):
    if type(width) is not int or not 1 <= width <= 101 or width % 2 != 1:
        raise ValueError(tr('Width must be an odd number from 1 to 101 native pixels.'))


def footprint(shape, points, width):
    """Rasterize an odd-width Euclidean tube; return its bounds and bitmap."""
    _validate_width(width)
    if not isinstance(points, (list, tuple)) or not 1 <= len(points) <= 100_000:
        raise ValueError(tr('Invalid mask stroke.'))
    h, w = shape
    for p in points:
        if (not isinstance(p, (list, tuple)) or len(p) != 2 or
                any(type(v) is not int for v in p) or not (0 <= p[0] < w and 0 <= p[1] < h)):
            raise ValueError(tr('Invalid mask stroke.'))
    radius = (width-1)//2
    xy = np.array(points, dtype=np.int32)
    left, top = np.maximum(0, xy.min(axis=0)-radius)
    right, bottom = np.minimum([w, h], xy.max(axis=0)+radius+1)
    raster = np.ones((bottom-top, right-left), np.uint8)
    shifted = xy-[left, top]
    raster[shifted[0, 1], shifted[0, 0]] = 0
    cv2.polylines(raster, [shifted], False, 0, 1, cv2.LINE_8)
    selected = ndi.distance_transform_edt(raster) <= radius if radius else raster == 0
    return (int(left), int(top), int(right), int(bottom)), selected


@dataclass(frozen=True)
class MaskCrop:
    """A binary mask stored on a local crop in native tile coordinates."""

    x: int
    y: int
    pixels: np.ndarray

    @property
    def box(self):
        h, w = self.pixels.shape
        return self.x, self.y, self.x + w, self.y + h

    def trim(self):
        ys = np.flatnonzero(self.pixels.any(axis=1))
        xs = np.flatnonzero(self.pixels.any(axis=0))
        if not len(xs):
            return MaskCrop(0, 0, np.zeros((0, 0), bool))
        left, top = int(xs[0]), int(ys[0])
        return MaskCrop(self.x + left, self.y + top,
                        self.pixels[top:ys[-1]+1, left:xs[-1]+1].copy())

    def overlay(self, target, box):
        """OR the intersecting crop into the raster represented by box."""
        x0, y0, x1, y1 = box
        left, top = max(self.x, x0), max(self.y, y0)
        right, bottom = min(self.box[2], x1), min(self.box[3], y1)
        if left < right and top < bottom:
            target[top-y0:bottom-y0, left-x0:right-x0] |= self.pixels[
                top-self.y:bottom-self.y, left-self.x:right-self.x]

    def raster(self, box):
        x0, y0, x1, y1 = box
        result = np.zeros((y1-y0, x1-x0), bool)
        self.overlay(result, box)
        return result


class MaskBatchCorrection:
    """Edit selected objects on one canvas while retaining their identities."""

    def __init__(self, objects, selected_ids, valid, gray):
        self.gray = gray
        self.valid = valid
        self._original = {
            int(obj['row']['Object_ID']): MaskCrop(*obj['origin'], obj['mask']).trim()
            for obj in objects
        }
        self.selected_ids = tuple(sorted(selected_ids))
        self.crops = dict(self._original)
        self.mask = np.zeros_like(valid)
        self._update_view((0, 0, valid.shape[1], valid.shape[0]))
        self.original = self.mask.copy()
        self.operations = []

    def _update_view(self, box):
        x0, y0, x1, y1 = box
        region = self.mask[y0:y1, x0:x1]
        region.fill(False)
        for ident in self.selected_ids:
            self.crops[ident].overlay(region, box)

    def _check_additions(self, ident, box, added, crops):
        x0, y0, x1, y1 = box
        # Include a one-pixel halo beyond the swept area to catch diagonal
        # contact with any other object, including its proposed additions.
        height, width = self.valid.shape
        halo = max(0, x0-1), max(0, y0-1), min(width, x1+1), min(height, y1+1)
        hx0, hy0, hx1, hy1 = halo
        foreign = np.zeros((hy1-hy0, hx1-hx0), bool)
        for other, other_crop in crops.items():
            if other != ident:
                other_crop.overlay(foreign, halo)
        forbidden = ndi.binary_dilation(foreign, np.ones((3, 3)))[y0-hy0:y1-hy0, x0-hx0:x1-hx0]
        if np.any(added & (forbidden | ~self.valid[y0:y1, x0:x1])):
            raise ValueError(tr('The stroke touches another object or padding. Reduce its width or change the path.'))

    @staticmethod
    def _extend(crop, box, added):
        x0, y0, x1, y1 = box
        ax0, ay0, ax1, ay1 = crop.box if crop.pixels.size else box
        left, top, right, bottom = min(ax0, x0), min(ay0, y0), max(ax1, x1), max(ay1, y1)
        revised = crop.raster((left, top, right, bottom))
        revised[y0-top:y1-top, x0-left:x1-left] |= added
        return MaskCrop(left, top, revised).trim()

    def _paint_touched(self, line_box, line, width):
        _validate_width(width)
        lx0, ly0, lx1, ly1 = line_box
        radius = (width-1)//2
        changed, additions = {}, {}
        if radius == 0:
            return line_box, changed
        h, w = self.valid.shape
        for ident in self.selected_ids:
            crop = self.crops[ident]
            x0, y0, x1, y1 = crop.box
            box = max(x0, lx0), max(y0, ly0), min(x1, lx1), min(y1, ly1)
            left, top, right, bottom = box
            if left >= right or top >= bottom:
                continue
            # Stamp the brush only at centers that touch this object's mask.
            # A stroke across background can never create a bridge by itself.
            seed_pixels = line[top-ly0:bottom-ly0, left-lx0:right-lx0] & crop.raster(box)
            seeds = MaskCrop(left, top, seed_pixels).trim()
            if not seeds.pixels.size:
                continue
            sx0, sy0, sx1, sy1 = seeds.box
            area = max(0, sx0-radius), max(0, sy0-radius), min(w, sx1+radius), min(h, sy1+radius)
            brush = ndi.distance_transform_edt(~seeds.raster(area)) <= radius
            added = brush & ~crop.raster(area)
            if added.any():
                changed[ident] = self._extend(crop, area, added)
                additions[ident] = (area, added)
        # Check against the final set before any change is installed. The
        # result is independent of the order of the selected mask IDs.
        proposed = self.crops | changed
        for ident, (area, added) in additions.items():
            self._check_additions(ident, area, added, proposed)
        return (max(0, lx0-radius), max(0, ly0-radius), min(w, lx1+radius), min(h, ly1+radius)), changed

    def apply(self, operation, *, update_view=True):
        if not isinstance(operation, dict) or operation.get('tool') not in ('paint', 'paint_touched', 'erase'):
            raise ValueError(tr('Invalid mask stroke.'))
        tool = operation['tool']
        width = operation.get('width')
        box, stroke = footprint(self.valid.shape, operation.get('points'), 1 if tool == 'paint_touched' else width)
        x0, y0, x1, y1 = box
        changed = {}
        if tool == 'paint':
            ident = operation.get('object_id')
            if type(ident) is not int or ident not in self.selected_ids:
                raise ValueError(tr('Choose an active mask for the brush.'))
            crop = self.crops[ident]
            added = stroke & ~crop.raster(box)
            if not added.any():
                return False
            self._check_additions(ident, box, added, self.crops)
            changed[ident] = self._extend(crop, box, added)
        elif tool == 'paint_touched':
            box, changed = self._paint_touched(box, stroke, width)
        else:
            # Only the selected masks are eligible for erasure, even if a
            # stroke passes across a nearby unselected object.
            for ident in self.selected_ids:
                crop = self.crops[ident]
                left, top = max(crop.x, x0), max(crop.y, y0)
                right, bottom = min(crop.box[2], x1), min(crop.box[3], y1)
                if left >= right or top >= bottom:
                    continue
                region = np.s_[top-crop.y:bottom-crop.y, left-crop.x:right-crop.x]
                cut = stroke[top-y0:bottom-y0, left-x0:right-x0]
                if np.any(crop.pixels[region] & cut):
                    revised = crop.pixels.copy()
                    revised[region] &= ~cut
                    changed[ident] = MaskCrop(crop.x, crop.y, revised).trim()
        if not changed:
            return False
        if len(self.operations) >= 500:
            raise ValueError(tr('Save these edits before adding more strokes.'))
        self.crops.update(changed)
        if update_view:
            self._update_view(box)
        self.operations.append(deepcopy(operation))
        return True

    def undo(self):
        operations = self.operations[:-1]
        self.crops = dict(self._original)
        self.operations = []
        for operation in operations:
            self.apply(operation, update_view=False)
        self._update_view((0, 0, self.mask.shape[1], self.mask.shape[0]))

    def changed_ids(self):
        return [ident for ident in self.selected_ids
                if self.crops[ident] is not self._original[ident] and
                (self.crops[ident].box != self._original[ident].box or
                 not np.array_equal(self.crops[ident].pixels, self._original[ident].pixels))]

    def original_crop(self, ident):
        return self._original[ident]

    def added_mask(self):
        result = np.zeros_like(self.mask)
        for ident in self.changed_ids():
            crop = self.crops[ident]
            x0, y0, x1, y1 = crop.box
            result[y0:y1, x0:x1] |= crop.pixels & ~self._original[ident].raster(crop.box)
        return result

    def validate(self):
        changed = self.changed_ids()
        if not changed:
            raise ValueError(tr('Make a mask correction before saving.'))
        for ident in changed:
            pixels = self.crops[ident].pixels
            if not pixels.size or component_count(pixels) != 1:
                raise ValueError(tr('Mask #{id} must stay nonempty and connected. Undo the stroke or use Delete selected masks.',
                                    id=ident))
        return changed


class MaskCorrection:
    def __init__(self, original, valid, other, gray):
        if original.shape != valid.shape or original.shape != other.shape or original.shape != gray.shape:
            raise ValueError(tr('Mask and tile dimensions do not match.'))
        if original.size > DEFAULTS['max_editor_pixels']:
            raise ValueError(tr('Mask editing is limited to 32 MP native tiles.'))
        self.original = original.astype(bool).copy()
        self.mask = self.original.copy()
        self.valid = valid.astype(bool).copy()
        self.other = other.astype(bool).copy()
        self.gray = gray
        # Include contact by a corner: a bridge must not join an unselected ID.
        self.forbidden = ndi.binary_dilation(self.other, np.ones((3, 3))) | ~self.valid
        self.operations = []

    def apply(self, operation):
        if not isinstance(operation, dict) or operation.get('tool') not in ('bridge', 'paint', 'erase'):
            raise ValueError(tr('Invalid mask stroke.'))
        tool = operation['tool']
        box, stroke = footprint(self.mask.shape, operation.get('points'), operation.get('width'))
        left, top, right, bottom = box
        area = np.s_[top:bottom, left:right]
        added = stroke & ~self.mask[area] if tool != 'erase' else np.zeros_like(stroke)
        if np.any(added & self.forbidden[area]):
            raise ValueError(tr('The stroke touches another object or padding. Reduce its width or change the path.'))
        if tool == 'bridge':
            labels, _ = ndi.label(self.mask, structure=np.ones((3, 3)))
            a, b = operation['points'][0], operation['points'][-1]
            if not labels[a[1], a[0]] or not labels[b[1], b[0]] or labels[a[1], a[0]] == labels[b[1], b[0]]:
                raise ValueError(tr('Choose ends on two different mask components.'))
        revised = self.mask[area].copy()
        revised[stroke] = tool != 'erase'
        if np.array_equal(revised, self.mask[area]): return False
        self.mask[area] = revised
        self.operations.append(deepcopy(operation))
        return True

    def undo(self):
        operations = deepcopy(self.operations[:-1])
        self.mask = self.original.copy(); self.operations = []
        for op in operations: self.apply(op)

    def validate(self):
        if not self.operations or np.array_equal(self.mask, self.original):
            raise ValueError(tr('Make a mask correction before saving.'))
        if component_count(self.mask) != 1:
            raise ValueError(tr('The corrected mask must contain one connected component. Connect the remaining parts, or use Delete selected masks.'))

    def route(self, first, last, width, margin, method='image'):
        if method not in ('image', 'straight') or type(margin) is not int or not 4 <= margin <= 256:
            raise ValueError(tr('Invalid connection settings.'))
        # Validate endpoint coordinates and width before indexing arrays.
        footprint(self.mask.shape, [first, last], width)
        labels, _ = ndi.label(self.mask, structure=np.ones((3, 3)))
        if not labels[first[1], first[0]] or not labels[last[1], last[0]] or labels[first[1], first[0]] == labels[last[1], last[0]]:
            raise ValueError(tr('Choose ends on two different mask components.'))
        h, w = self.mask.shape
        radius = (width-1)//2
        left, top = max(0, min(first[0], last[0])-margin), max(0, min(first[1], last[1])-margin)
        right, bottom = min(w, max(first[0], last[0])+margin+1), min(h, max(first[1], last[1])+margin+1)
        bounds = [left, top, right, bottom]
        if method == 'straight':
            points = [first, last]
        else:
            if (right-left)*(bottom-top) > DEFAULTS['max_route_pixels']:
                raise ValueError(tr('The search region is too large. Reduce the margin or use a straight line or brush.'))
            # Pad the ROI so a thick route cannot escape it at the edges.
            blocked = self.forbidden[top:bottom, left:right].copy()
            allowed = np.pad(~blocked, 1)
            clear = ndi.distance_transform_edt(allowed)[1:-1, 1:-1] > radius
            intensity = self.gray[top:bottom, left:right].astype(float)/255.0
            cost = 1 + DEFAULTS['path_intensity_weight']*(1-intensity)**2
            cost[~clear] = np.inf
            # Conservatively prevent diagonal shortcuts at an obstacle corner.
            # The final swept-width check below is still authoritative.
            cost[ndi.binary_dilation(blocked, np.ones((3, 3))) & ~blocked] = np.inf
            start = (first[1]-top, first[0]-left); end = (last[1]-top, last[0]-left)
            if not np.isfinite(cost[start]) or not np.isfinite(cost[end]):
                raise ValueError(tr('No safe connection at this width. Reduce the width or choose different ends.'))
            try:
                path, total = route_through_array(cost, start, end, fully_connected=True, geometric=True)
            except ValueError as error:
                raise ValueError(tr('No safe path in this region. Change the ends, margin or width.')) from error
            if not math.isfinite(total):
                raise ValueError(tr('No safe path in this region. Change the ends, margin or width.'))
            points = [[int(x+left), int(y+top)] for y, x in path]
            length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
            if length > 3*math.dist(first, last)+20:
                raise ValueError(tr('The proposed route is too indirect. Choose different ends or use the brush.'))
        operation = dict(tool='bridge', points=points, width=width, method=method, search_bounds=bounds,
                         endpoints=[first, last])
        # Validate the entire thickened route against ownership and other IDs.
        box, stroke = footprint(self.mask.shape, points, width)
        x0, y0, x1, y1 = box
        if np.any(stroke & ~self.mask[y0:y1, x0:x1] & self.forbidden[y0:y1, x0:x1]):
            raise ValueError(tr('The stroke touches another object or padding. Reduce its width or change the path.'))
        return operation
