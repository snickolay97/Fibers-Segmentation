"""Adaptive slicing with exact pixel ownership and whole-component allocation.

Search boundaries are proposals. Only the validated ownership partition is
exported. The guarantee concerns 8-connected components of the supplied obstacle
mask, not objects omitted by that mask or objects cropped by the source image.
"""
import json
import os
import tempfile
import time
from pathlib import Path
import cv2
import numpy as np
from skimage.graph import MCP_Geometric
from src import config
from src.tile_scale import scale_metadata, fixed_canvas
from src.search_animation import save_search_animation
from src.partition_geometry import (checked_imwrite, connected_components_striped,
                                    render_overview)


class SmartSlicer:
    def __init__(self, target_size=config.TARGET_SIZE, margin_start=config.MARGIN_START,
                 margin_end=config.MARGIN_END, enable_animation=config.ENABLE_ANIMATIONS,
                 animation_dir=config.ANIMATION_DIR, min_corridor_width=config.MIN_CORRIDOR_WIDTH,
                 save_raw_tiles=config.SAVE_RAW_TILES, dynamic_step=None, min_margin_limit=None,
                 oversized_policy=None):
        self.target_size, self.base_step, self.max_step = map(int, (target_size, margin_start, margin_end))
        self.dynamic_step = int(config.DYNAMIC_EXPANSION_STEP if dynamic_step is None else dynamic_step)
        self.min_margin_limit = int(config.MIN_MARGIN_LIMIT if min_margin_limit is None else min_margin_limit)
        self.min_corridor_width = int(min_corridor_width)
        self.enable_animation, self.animation_dir = enable_animation, animation_dir
        self.save_raw_tiles = save_raw_tiles
        self.oversized_policy = oversized_policy or getattr(config, 'OVERSIZED_OBJECT_POLICY', 'preserve')
        if not (0 < self.min_margin_limit <= self.base_step < self.max_step <= self.target_size):
            raise ValueError('Require 0 < min_margin_limit <= margin_start < margin_end <= target_size')
        if self.dynamic_step <= 0 or self.min_corridor_width <= 0:
            raise ValueError('Search step and corridor width must be positive')
        if self.oversized_policy not in ('preserve', 'error'):
            raise ValueError('oversized_policy must be preserve or error')
        self.search_stats = {}

    @staticmethod
    def _find_safe_corridor_cut(sums, min_width):
        zero = np.asarray(sums) == 0
        changes = np.diff(np.r_[False, zero, False].astype(np.int8))
        starts, ends = np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)
        widths = ends - starts
        for limit in (min_width, max(3, min_width // 2)):
            eligible = np.flatnonzero(widths >= limit)
            if eligible.size:
                best = eligible[np.argmax(widths[eligible])]
                return int((starts[best] + ends[best] - 1) // 2)
        return None

    def find_topographical_seam(self, mask_zone, axis):
        if axis not in ('vertical', 'horizontal'):
            raise ValueError('axis must be vertical or horizontal')
        zone = mask_zone if axis == 'vertical' else mask_zone.T
        h, w = zone.shape
        if not h or not w:
            return np.array([], dtype=int), float('inf')
        free = np.ascontiguousarray(zone == 0, dtype=np.uint8)
        if not free[0].any() or not free[-1].any():
            return np.array([], dtype=int), float('inf')
        distance = cv2.distanceTransform(free, cv2.DIST_L2, 5)
        costs = 1.0 / (distance ** config.SEAM_REPULSION_POWER + 1e-3)
        costs[free == 0] = np.inf
        # Directed offsets give exactly one point per row. This prevents the
        # lossy projection of an unrestricted path onto seam[row] in v1.
        mcp = MCP_Geometric(costs, offsets=[(1, -1), (1, 0), (1, 1)])
        starts = [(0, int(x)) for x in np.flatnonzero(free[0])]
        ends = [(h - 1, int(x)) for x in np.flatnonzero(free[-1])]
        cumulative, _ = mcp.find_costs(starts, ends=ends, find_all_ends=False)
        x = int(np.argmin(cumulative[-1]))
        cost = float(cumulative[-1, x])
        if not np.isfinite(cost):
            return np.array([], dtype=int), float('inf')
        path = np.asarray(mcp.traceback((h - 1, x)), dtype=int)
        if len(path) != h or not np.array_equal(path[:, 0], np.arange(h)):
            raise RuntimeError('Non-monotone path from directed solver')
        seam = path[:, 1]
        if np.any(zone[np.arange(h), seam]):
            raise RuntimeError('Path crosses an obstacle')
        return seam, cost

    def _boundary(self, block):
        """Vertical boundary in local coordinates; None means deferred routing."""
        h, w = block.shape
        trials = []
        def finish(seam, method):
            if self.enable_animation and hasattr(self, '_animation_name'):
                self._animation_counter += 1
                save_search_animation(Path(self.animation_dir)/self._animation_name,
                    self._animation_name,self._animation_counter,self._animation_axis,
                    self._animation_origin,block,self._animation_background,trials,seam,method,
                    getattr(config,'ANIMATION_MAX_TRIAL_FRAMES',24))
            return seam
        if w <= self.base_step:
            self.search_stats['edge'] += 1
            return np.full(h, w, dtype=int)
        width = self.max_step - self.base_step
        # Compute the projection once, instead of summing overlapping windows.
        projection = np.any(block[:, :self.max_step], axis=0)
        for offset in range(self.base_step, self.min_margin_limit - 1, -self.dynamic_step):
            trials.append([offset,min(offset+width,w)])
            cut = self._find_safe_corridor_cut(projection[offset:min(offset + width, w)], self.min_corridor_width)
            if cut is not None:
                self.search_stats['corridor'] += 1
                return finish(np.full(h, offset + cut, dtype=int),'straight corridor')
        trials.append([self.base_step,min(self.max_step,w)])
        seam, cost = self.find_topographical_seam(block[:, self.base_step:self.max_step], 'vertical')
        if np.isfinite(cost):
            self.search_stats['dijkstra'] += 1
            return finish(seam+self.base_step,'Dijkstra')
        self.search_stats['deferred'] += 1
        return finish(None,'unreachable')

    def _proposal_partition(self, mask, owners):
        h, w = mask.shape
        records = []
        self.search_stats = dict(edge=0, corridor=0, dijkstra=0, deferred=0)

        def add(x1, y1, x2, y2, local, kind):
            view = owners[y1:y2, x1:x2]
            valid = local & (view == 0)
            if valid.any():
                tid = len(records) + 1
                view[valid] = tid
                records.append(dict(id=tid, x1=x1, y1=y1, x2=x2, y2=y2, kind=kind))

        ya = 0
        while ya < h:
            xa, bottoms = 0, []
            while xa < w:
                span = min(ya + self.target_size, h)
                block = mask[ya:span, xa:min(xa + self.target_size, w)]
                if self.enable_animation:
                    self._animation_axis='right';self._animation_origin=(xa,ya)
                    self._animation_background=self._animation_image[ya:span,xa:min(xa+self.target_size,w)]
                right = self._boundary(block)
                deferred = right is None
                if deferred:
                    right = np.full(len(block), min(self.base_step, w - xa), dtype=int)
                mx = int(right.max())
                if self.enable_animation:
                    self._animation_axis='bottom'
                    self._animation_background=self._animation_image[ya:min(ya+self.target_size,h),xa:xa+mx].swapaxes(0,1)
                bottom = self._boundary(mask[ya:min(ya + self.target_size, h), xa:xa + mx].T)
                deferred |= bottom is None
                if bottom is None:
                    bottom = np.full(mx, min(self.base_step, h - ya), dtype=int)
                my = int(bottom.max())
                local = (np.arange(mx)[None, :] < right[:my, None]) & (np.arange(my)[:, None] < bottom[None, :])
                add(xa, ya, xa + mx, ya + my, local, 'provisional' if deferred else 'adaptive')
                xa += max(1, int(right.min()))
                bottoms.append(ya + int(bottom.min()))
            ya = min(bottoms) if bottoms else min(ya + self.base_step, h)
        # Coverage is checked explicitly even for irregular row intersections.
        for y in range(0, h, self.target_size):
            for x in range(0, w, self.target_size):
                x2, y2 = min(x + self.target_size, w), min(y + self.target_size, h)
                if np.any(owners[y:y2, x:x2] == 0):
                    add(x, y, x2, y2, np.ones((y2-y, x2-x), bool), 'coverage_repair')
        return records

    def _allocate_components(self, labels, stats, owners, records):
        h, w = labels.shape
        repaired, oversized = 0, 0
        component_owner = np.zeros(len(stats), np.int32)
        for component in range(1, len(stats)):
            x1, y1, x2, y2 = [int(v) for v in stats[component, :4]]
            candidates = [r for r in records if r['x1'] <= x1 and r['y1'] <= y1 and r['x2'] >= x2 and r['y2'] >= y2]
            if candidates:
                # Preserve an already intact component. Choosing the first
                # enclosing rectangle creates unnecessary islands across seams.
                votes = {}
                for yy in range(y1,y2,256):
                    stop = min(yy+256,y2)
                    ids, nums = np.unique(owners[yy:stop,x1:x2][labels[yy:stop,x1:x2] == component], return_counts=True)
                    for owner,num in zip(ids,nums):
                        votes[int(owner)] = votes.get(int(owner),0)+int(num)
                rec = max(candidates,key=lambda r:votes.get(r['id'],0))
            else:
                big = x2-x1 > self.target_size or y2-y1 > self.target_size
                if big and self.oversized_policy == 'error':
                    raise ValueError('Component {} needs {}x{} pixels, larger than target'.format(component, x2-x1, y2-y1))
                cw, ch = max(self.target_size, x2-x1), max(self.target_size, y2-y1)
                xx = max(0, min((x1 + x2 - cw)//2, w-cw))
                yy = max(0, min((y1 + y2 - ch)//2, h-ch))
                rec = dict(id=len(records)+1, x1=xx, y1=yy, x2=min(w, xx+cw), y2=min(h, yy+ch), kind='oversized_component' if big else 'component_crop')
                records.append(rec)
                oversized += int(big)
            tid = rec['id']
            changed = False
            for y in range(y1, y2, 256):
                stop = min(y+256, y2)
                valid = labels[y:stop, x1:x2] == component
                view = owners[y:stop, x1:x2]
                changed |= bool(np.any(view[valid] != tid))
                view[valid] = tid
            repaired += int(changed)
            component_owner[component] = tid
        # Validate independently by scanning the final partition. This also
        # catches diagonal components split by intersecting search proposals.
        covered = 0
        for y in range(0, h, 256):
            lab, own = labels[y:y+256], owners[y:y+256]
            if np.any(own == 0):
                raise RuntimeError('Unowned source pixels')
            protected = lab > 0
            if np.any(own[protected] != component_owner[lab[protected]]):
                raise RuntimeError('A protected component spans multiple tiles')
            covered += int(np.count_nonzero(own))
        return dict(protected_components=len(stats)-1, reassigned_components=repaired,
                    oversized_crops=oversized, split_protected_components=0,
                    covered_pixels=covered, total_pixels=h*w)

    def slice(self, filtered_img, raw_img, mask, base_name, output_dir, raw_output_dir=None):
        if mask.ndim != 2 or not mask.size or filtered_img.shape != mask.shape or raw_img.shape[:2] != mask.shape:
            raise ValueError('Expect nonempty 2D filtered/mask arrays and matching raw image dimensions')
        if filtered_img.dtype != np.uint8 or raw_img.dtype not in (np.uint8, np.uint16):
            raise ValueError('Expected uint8 filtered image and uint8/uint16 raw data')
        out = Path(output_dir)
        raw_out = Path(raw_output_dir) if self.save_raw_tiles and raw_output_dir else None
        if self.save_raw_tiles and raw_out is None:
            raise ValueError('raw_output_dir is required when save_raw_tiles=True')
        for folder in [out] + ([raw_out] if raw_out else []):
            if list(folder.glob(base_name + '_tile_*.png')):
                raise FileExistsError('Choose a new output directory; existing tiles will not be overwritten: {}'.format(folder))
            folder.mkdir(parents=True, exist_ok=True)
        if self.enable_animation:
            self._animation_name=base_name;self._animation_counter=0
            self._animation_image=raw_img
        started = time.perf_counter()
        h, w = mask.shape
        with tempfile.TemporaryDirectory(prefix='.partition_', dir=str(out)) as work:
            owners = np.memmap(os.path.join(work, 'owners.dat'), dtype=np.int32, mode='w+', shape=(h,w))
            labels = np.memmap(os.path.join(work, 'labels.dat'), dtype=np.int32, mode='w+', shape=(h,w))
            try:
                print('   - Building adaptive proposals...', flush=True)
                records = self._proposal_partition(mask, owners)
                print('   - Labelling protected components in strips...', flush=True)
                stats = connected_components_striped(mask, labels)
                print('   - Assigning {} complete components...'.format(len(stats)-1), flush=True)
                checks = self._allocate_components(labels, stats, owners, records)
                counts = np.zeros(len(records)+1, np.int64)
                for y in range(0,h,256):
                    counts += np.bincount(owners[y:y+256].ravel(), minlength=len(counts))
                records = [r for r in records if counts[r['id']]]
                for folder in [out] + ([raw_out] if raw_out else []):
                    (folder/'valid_masks').mkdir(exist_ok=True)
                    (folder/'overview').mkdir(exist_ok=True)
                    (folder/'native').mkdir(exist_ok=True)
                    if getattr(config,'SAVE_COVERAGE_MASKS',False):
                        (folder/'coverage_masks').mkdir(exist_ok=True)
                for i, rec in enumerate(records):
                    x1,y1,x2,y2 = [rec[k] for k in ('x1','y1','x2','y2')]
                    valid = owners[y1:y2,x1:x2] == rec['id']
                    if int(valid.sum()) != counts[rec['id']]:
                        raise RuntimeError('Tile ownership extends outside its stored crop')
                    rec['valid_mask'] = 'valid_masks/valid_{:04d}.png'.format(rec['id'])
                    rec['filename'] = '{}_tile_{:04d}.png'.format(base_name,rec['id'])
                    rec['valid_pixels'] = int(valid.sum())
                    rec['canvas_shape'] = [self.target_size,self.target_size]
                    rec['native_filename'] = 'native/native_{:04d}.png'.format(rec['id'])
                    if getattr(config,'SAVE_COVERAGE_MASKS',False):
                        rec['coverage_mask'] = 'coverage_masks/coverage_{:04d}.png'.format(rec['id'])
                    rec['transform'] = scale_metadata(y2-y1,x2-x1,self.target_size)
                    coverage = fixed_canvas(valid.astype(np.uint8)*255,rec['transform'],mask=True) if getattr(config,'SAVE_COVERAGE_MASKS',False) else None
                    raw_crop=raw_img[y1:y2,x1:x2]
                    if raw_crop.ndim == 2 and raw_crop.dtype == np.uint8:
                        rec['quality']={'raw_fraction_ge_250':float(np.mean(raw_crop[valid]>=250))}
                        rec['quality']['review_bright_region']=rec['quality']['raw_fraction_ge_250']>.01
                    for folder,source in [(out,filtered_img)] + ([(raw_out,raw_img)] if raw_out else []):
                        tile = source[y1:y2,x1:x2].copy()
                        tile[~valid] = 0
                        checked_imwrite(folder/rec['native_filename'],tile)
                        checked_imwrite(folder/rec['filename'],fixed_canvas(tile,rec['transform']))
                        checked_imwrite(folder/rec['valid_mask'],valid.astype(np.uint8)*255)
                        if coverage is not None:
                            checked_imwrite(folder/rec['coverage_mask'],coverage)
                    if (i+1)%25==0:
                        print('   - Saved {}/{} tiles'.format(i+1,len(records)),flush=True)
                checks.update(tile_count=len(records), search=self.search_stats, search_animations=getattr(self,'_animation_counter',0),
                              seconds_before_overview=round(time.perf_counter()-started,3))
                manifest = dict(schema_version=3, source_name=base_name, image_shape=[h,w],
                                guarantee='8-connected components of the supplied obstacle mask',
                                parameters=dict(target_size=self.target_size,margin_start=self.base_step,margin_end=self.max_step,dynamic_step=self.dynamic_step,min_margin_limit=self.min_margin_limit,min_corridor_width=self.min_corridor_width,oversized_policy=self.oversized_policy),
                                checks=checks, tiles=records)
                for folder in [out] + ([raw_out] if raw_out else []):
                    with open(str(folder/'overview'/(base_name+'_tiles_coords.json')),'w',encoding='utf-8') as handle:
                        json.dump(manifest,handle,indent=2)
                print('   - Rendering ownership boundaries...',flush=True)
                overview = render_overview(raw_img,owners,records,config.OVERVIEW_MAP_SIZE)
                checked_imwrite(out/'overview'/(base_name+'_TILE_INDEX_MAP_{}px.png'.format(config.OVERVIEW_MAP_SIZE)),overview)
                print('   - Validated: {} tiles, {} protected components, zero component splits.'.format(len(records),len(stats)-1),flush=True)
                return manifest
            finally:
                # Release views before TemporaryDirectory removes mapped files on Windows.
                for attr in ('_animation_image','_animation_background'):
                    if hasattr(self,attr):delattr(self,attr)
                for array in (owners,labels):
                    array.flush()
                    array._mmap.close()
