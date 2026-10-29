import os
import json
import glob
import re
import cv2
import numpy as np
import pandas as pd
import warnings
import shutil
import tempfile
from pathlib import Path
from typing import Tuple, List, Optional
from skimage import measure, morphology
import skimage.filters as ski_filters
import scipy.ndimage as ndi

from src import config
from src.object_classes import OBJECT_CLASS_CATALOG
from src.partition_geometry import dataset_path, png_shape, checked_imwrite
from src.tile_scale import scale_metadata

warnings.filterwarnings("ignore")

CLASS_MAP = {item['id']: item['source_label'] for item in OBJECT_CLASS_CATALOG}
CLASS_MAP[-1] = 'Unknown'
FEATURE_COLUMNS = ['Large_Image', 'Tile_Name', 'Object_ID', 'Class_ID', 'Class_Name',
                   'Measurement_Space', 'Source_Pixels_Per_Output_Pixel', 'Area',
                   'Aspect_Ratio', 'Solidity', 'Euler_Number', 'Endpoints', 'Branch_Points']


def _tile_files(dataset_dir):
    return sorted(p for p in Path(dataset_dir).glob('*.png')
                  if re.fullmatch(r'.+_tile_\d+\.png', p.name))


def inspect_labels(dataset_dir, labels_dir):
    """Read-only annotation preflight. Empty files differ from missing files."""
    images = _tile_files(dataset_dir)
    labels = Path(labels_dir)
    result = dict(tiles=len(images), annotated=0, empty=0, missing=0, errors=[],
                  orphan_names=[], missing_names=[], empty_names=[], annotated_names=[])
    expected = {p.stem+'.txt' for p in images}
    for image in images:
        label = labels/(image.stem+'.txt')
        if not label.is_file():
            result['missing'] += 1
            result['missing_names'].append(label.name)
            continue
        try:
            polygons = TopologicalFeatureExtractor._parse_yolo(str(label), 1, 1)
            key = 'annotated' if polygons else 'empty'
            result[key] += 1
            result[key+'_names'].append(label.name)
        except (ValueError, OSError) as error:
            result['errors'].append(dict(file=str(label), error=str(error)))
    if labels.is_dir():
        result['orphan_names'] = sorted(p.name for p in labels.glob('*.txt') if p.name not in expected)
    return result

class TopologicalFeatureExtractor:
    """
    BLOCK 3: Topological Feature Extractor Node.
    Extracts geometric and graph descriptors from segmented objects.
    Protects against reading overview or excluded folders via strict white-list matching.
    """

    def __init__(self, image_dir: str, labels_dir: str, output_dir: str,
                 large_image_name: str = "dataset", mask_save_mode: str = 'gray_3filter',
                 settings=None, progress=None, cancelled=None, labels_mode='auto', allow_legacy=True):
        self.image_dir = image_dir
        self.labels_dir = labels_dir
        self.output_dir = output_dir
        self.large_image_name = large_image_name
        self.mask_save_mode = mask_save_mode
        self.verification_dir = os.path.join(self.output_dir, "verification_masks")
        if labels_mode not in ('auto', 'annotations_only', 'require_annotations'):
            raise ValueError('Invalid labels_mode')
        if not re.fullmatch(r'[^/\\:]+', large_image_name) or large_image_name in ('.', '..'):
            raise ValueError('Dataset name must be a safe filename')
        self.settings, self.progress, self.cancelled = settings, progress, cancelled
        self.labels_mode, self.allow_legacy = labels_mode, allow_legacy
        self.class_map = CLASS_MAP.copy()

    def _setting(self, name):
        return getattr(self.settings, name.lower(), getattr(config, name))

    def _check_cancelled(self):
        if self.cancelled and self.cancelled():
            from src.app_settings import PipelineCancelled
            raise PipelineCancelled('Operation cancelled')

    def _emit(self, **event):
        if self.progress:
            self.progress(dict(stage='features', **event))

    @staticmethod
    def _parse_yolo(label_path: str, img_w: int, img_h: int) -> list:
        objects = []
        with open(label_path, 'r', encoding='utf-8-sig') as f:
            for line_number, line in enumerate(f, 1):
                parts = line.strip().split()
                if not parts:
                    continue
                if len(parts) < 7 or (len(parts)-1) % 2:
                    raise ValueError('Expected YOLO segmentation polygon (at least 3 points): '+label_path)
                try:
                    class_id = int(parts[0])
                    coords = np.array(parts[1:], dtype=float).reshape(-1, 2)
                except ValueError as error:
                    raise ValueError('Invalid YOLO numeric values at {}:{}'.format(label_path, line_number)) from error
                if class_id not in CLASS_MAP or class_id == -1:
                    raise ValueError('Unknown annotation class at {}:{}'.format(label_path, line_number))
                if not np.all(np.isfinite(coords)) or np.any(coords < 0) or np.any(coords > 1):
                    raise ValueError('YOLO coordinates must be finite and normalized to 0..1 at {}:{}'.format(label_path, line_number))
                coords[:, 0] *= img_w
                coords[:, 1] *= img_h
                contour = coords.reshape((-1, 1, 2)).astype(np.int32)
                objects.append((class_id, contour))
        return objects

    @staticmethod
    def _find_contours(binary_img: np.ndarray, min_area: int = 10) -> list:
        contours, _ = cv2.findContours(binary_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return [(-1, c) for c in contours if cv2.contourArea(c) >= min_area]

    def _create_local_mask(self, contour: np.ndarray, gray_tile: np.ndarray,
                           pad: int = 2) -> Tuple[np.ndarray, np.ndarray]:
        x, y, w, h = cv2.boundingRect(contour)
        img_h, img_w = gray_tile.shape

        y1, y2 = max(0, y), min(img_h, y + h)
        x1, x2 = max(0, x), min(img_w, x + w)
        raw_crop = gray_tile[y1:y2, x1:x2]

        stencil = np.zeros((y2 - y1, x2 - x1), dtype=np.uint8)
        shifted_contour = contour.copy()
        shifted_contour[:, 0, 0] -= x1
        shifted_contour[:, 0, 1] -= y1
        cv2.drawContours(stencil, [shifted_contour], -1, 255, thickness=-1)

        isolated_gray = cv2.bitwise_and(raw_crop, raw_crop, mask=stencil)

        local_otsu, _ = cv2.threshold(isolated_gray[stencil > 0], 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU) if np.any(stencil > 0) else (40, 0)
        minimum = self._setting('MIN_CLEAN_THRESHOLD')
        clean_thresh = max(minimum, int(local_otsu * self._setting('TIER2_THRESHOLD_FACTOR'))) if local_otsu > 10 else minimum
        _, clean_binary = cv2.threshold(isolated_gray, clean_thresh, 255, cv2.THRESH_BINARY)

        padded_gray = cv2.copyMakeBorder(isolated_gray, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
        padded_binary = cv2.copyMakeBorder(clean_binary, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
        return padded_binary, padded_gray

    def _decompose_sub_objects(self, binary_mask: np.ndarray, gray_mask: np.ndarray,
                              min_area: Optional[int] = None, pad: int = 2) -> List[Tuple[np.ndarray, np.ndarray]]:
        min_area = self._setting('MIN_SUB_OBJECT_AREA') if min_area is None else min_area
        bin_u8 = (binary_mask > 0).astype(np.uint8)
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(bin_u8, connectivity=8)
        valid_labels = [lbl for lbl in range(1, num_labels) if stats[lbl, cv2.CC_STAT_AREA] >= min_area]

        decomposed = []
        for lbl in valid_labels:
            comp_mask = (labels == lbl).astype(np.uint8) * 255
            bx, by, bw, bh = cv2.boundingRect(comp_mask)
            if bw == 0 or bh == 0:
                continue

            sub_mask = comp_mask[by:by + bh, bx:bx + bw]
            sub_gray = cv2.bitwise_and(gray_mask[by:by + bh, bx:bx + bw], gray_mask[by:by + bh, bx:bx + bw], mask=sub_mask)
            decomposed.append((
                cv2.copyMakeBorder(sub_mask, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0),
                cv2.copyMakeBorder(sub_gray, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
            ))

        return decomposed

    @staticmethod
    def _extract_geometry(mask: np.ndarray) -> Optional[dict]:
        props = measure.regionprops((mask > 0).astype(int))
        if not props:
            return None
        p = props[0]
        minor = p.minor_axis_length
        aspect_ratio = (p.major_axis_length / minor) if minor > 1e-6 else 1.0
        return {
            'Area': p.area,
            'Aspect_Ratio': aspect_ratio,
            'Solidity': p.solidity,
            'Euler_Number': p.euler_number
        }

    @staticmethod
    def _extract_topology(mask: np.ndarray) -> dict:
        skeleton = morphology.skeletonize(mask > 0)
        kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=int)
        neighbor_count = ndi.convolve(skeleton.astype(int), kernel, mode='constant', cval=0)

        endpoints = np.sum((neighbor_count == 1) & skeleton)
        branch_points = np.sum((neighbor_count > 2) & skeleton)
        return {
            'Endpoints': int(endpoints),
            'Branch_Points': int(branch_points)
        }

    def _measurement_records(self, image_files):
        base = Path(self.image_dir).resolve()
        manifests = sorted((base/'overview').glob('*_tiles_coords.json'))
        if len(manifests) > 1:
            raise ValueError('Multiple dataset manifests found')
        if not manifests:
            if (base/'native').exists() or not self.allow_legacy:
                raise ValueError('Native dataset requires a v3 manifest; re-slice or restore metadata')
            return {}
        manifest_path = dataset_path(base, manifests[0].relative_to(base).as_posix())
        with manifest_path.open(encoding='utf-8') as handle:
            manifest = json.load(handle)
        if not isinstance(manifest, dict) or manifest.get('schema_version') != 3:
            if (base/'native').exists() or not self.allow_legacy:
                raise ValueError('Native measurement requires a v3 manifest')
            return {}
        records = {}
        for record in manifest.get('tiles', []):
            filename = record.get('filename')
            path = dataset_path(base, filename)
            if path.parent != base or filename in records:
                raise ValueError('Invalid or duplicate model filename in manifest')
            native = dataset_path(base, record.get('native_filename'))
            shape = png_shape(native)
            tr = record.get('transform', {})
            side = tr.get('padded_native_shape', [])
            factor = tr.get('source_pixels_per_output_pixel')
            if tr.get('native_crop_shape') != list(shape) or len(side) != 2 or side[0] != side[1] or side[0] < max(shape):
                raise ValueError('Invalid native transform for '+filename)
            if not isinstance(factor, (int,float)) or not np.isfinite(factor) or factor <= 0:
                raise ValueError('Invalid scale factor for '+filename)
            output_shape = tr.get('output_shape')
            if not isinstance(output_shape,list) or len(output_shape) != 2 or any(not isinstance(v,int) or v <= 0 for v in output_shape) or output_shape[0] != output_shape[1]:
                raise ValueError('Invalid output canvas for '+filename)
            if tr != scale_metadata(*shape, output_shape[0]):
                raise ValueError('Inconsistent measurement transform for '+filename)
            model_path = path if path.is_file() else dataset_path(base,'excluded_tiles/'+filename)
            if png_shape(model_path) != tuple(output_shape):
                raise ValueError('Model size differs from transform: '+filename)
            if record.get('valid_mask') and png_shape(dataset_path(base,record['valid_mask'])) != shape:
                raise ValueError('Valid mask size differs from native crop: '+filename)
            records[filename] = record
        for image in image_files:
            if image.name not in records:
                raise ValueError('Active tile is absent from v3 manifest: '+image.name)
        return records

    def _publish(self, stage, staged_csv, staged_masks, csv_path):
        """Publish the two outputs together, rolling back either on failure."""
        target_masks = Path(self.verification_dir)
        old_csv, old_masks = stage/'previous.csv', stage/'previous_masks'
        for target in (target_masks, csv_path):
            if target.is_symlink():
                raise ValueError('Output destinations must not be symlinks')
        moved_csv = moved_masks = new_csv = new_masks = False
        try:
            if csv_path.exists():
                os.replace(csv_path, old_csv); moved_csv = True
            if target_masks.exists():
                os.replace(target_masks, old_masks); moved_masks = True
            os.replace(staged_masks, target_masks); new_masks = True
            os.replace(staged_csv, csv_path); new_csv = True
        except BaseException:
            if new_csv:
                csv_path.unlink()
            if new_masks:
                shutil.rmtree(target_masks)
            if moved_csv:
                os.replace(old_csv, csv_path)
            if moved_masks:
                os.replace(old_masks, target_masks)
            raise

    def execute(self):
        self._check_cancelled()
        base = Path(self.image_dir).resolve()
        if not base.is_dir():
            raise ValueError('Dataset directory does not exist: '+str(base))
        image_files = _tile_files(base)
        records = self._measurement_records(image_files)
        preflight = inspect_labels(base, self.labels_dir)
        if preflight['errors']:
            raise ValueError('Invalid annotation: '+str(preflight['errors'][0]))
        if self.labels_mode == 'require_annotations' and preflight['missing']:
            raise ValueError('Annotations missing for {} active tiles'.format(preflight['missing']))
        output = Path(self.output_dir).resolve()
        output.mkdir(parents=True, exist_ok=True)
        self.verification_dir = str(output/'verification_masks')
        csv_path = output/(self.large_image_name+'_features.csv')
        pixel_size = getattr(self.settings, 'pixel_size_um', None)
        if pixel_size is not None and (not np.isfinite(pixel_size) or pixel_size <= 0):
            raise ValueError('Pixel calibration must be positive and finite')
        columns = FEATURE_COLUMNS + (['Area_um2'] if pixel_size is not None else [])
        all_features, skipped = [], 0
        with tempfile.TemporaryDirectory(prefix='.features_', dir=str(output)) as work:
            stage = Path(work)
            staged_masks = stage/'verification_masks'
            staged_masks.mkdir()
            for index, img_path in enumerate(image_files):
                self._check_cancelled()
                label_path = Path(self.labels_dir)/(img_path.stem+'.txt')
                if not label_path.is_file() and self.labels_mode == 'annotations_only':
                    skipped += 1
                    self._emit(completed=index+1, total=len(image_files), tile=img_path.name, skipped=True)
                    continue
                record = records.get(img_path.name)
                measurement_path = dataset_path(base, record['native_filename']) if record else img_path
                img = cv2.imread(str(measurement_path), cv2.IMREAD_GRAYSCALE)
                if img is None:
                    raise ValueError('Unreadable measurement image: '+str(measurement_path))
                img_h, img_w = img.shape
                if label_path.is_file():
                    side = record['transform']['padded_native_shape'][0] if record else None
                    objects = self._parse_yolo(str(label_path), side or img_w, side or img_h)
                else:
                    _, envelope = cv2.threshold(img, self._setting('MIN_CLEAN_THRESHOLD'), 255, cv2.THRESH_BINARY)
                    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
                    objects = self._find_contours(cv2.morphologyEx(envelope, cv2.MORPH_CLOSE, kernel), min_area=0)
                saved_obj_idx = 0
                for class_id, contour in objects:
                    self._check_cancelled()
                    x,y,w,h = cv2.boundingRect(contour)
                    if x >= img_w or y >= img_h or x+w <= 0 or y+h <= 0:
                        continue
                    binary, gray = self._create_local_mask(contour, img)
                    for sub_binary, sub_gray in self._decompose_sub_objects(binary, gray):
                        self._check_cancelled()
                        geometry = self._extract_geometry(sub_binary)
                        if not geometry:
                            continue
                        saved_obj_idx += 1
                        class_name = self.class_map[class_id]
                        tile_dir = staged_masks/img_path.stem
                        tile_dir.mkdir(exist_ok=True)
                        mask_path = tile_dir/'obj_{:03d}_{}.png'.format(saved_obj_idx, class_name)
                        checked_imwrite(mask_path, sub_gray if self.mask_save_mode == 'gray_3filter' else sub_binary)
                        row = dict(Large_Image=self.large_image_name, Tile_Name=img_path.stem,
                                   Object_ID=saved_obj_idx, Class_ID=class_id, Class_Name=class_name,
                                   Measurement_Space='source_pixels' if record else 'tile_pixels',
                                   Source_Pixels_Per_Output_Pixel=record['transform']['source_pixels_per_output_pixel'] if record else 1.0,
                                   **geometry, **self._extract_topology(sub_binary))
                        if pixel_size is not None:
                            row['Area_um2'] = row['Area']*pixel_size*pixel_size
                        all_features.append(row)
                self._emit(completed=index+1, total=len(image_files), tile=img_path.name, objects=len(all_features))
            staged_csv = stage/'features.csv'
            pd.DataFrame(all_features, columns=columns).to_csv(staged_csv, index=False)
            self._check_cancelled()
            self._publish(stage, staged_csv, staged_masks, csv_path)
        return dict(status='completed', objects=len(all_features), csv_path=str(csv_path),
                    tiles=len(image_files), skipped_unlabeled=skipped,
                    measurement_space='source_pixels' if records else 'tile_pixels')

