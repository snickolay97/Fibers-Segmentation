import os
import json
import glob
import re
import cv2
import numpy as np
import pandas as pd
import warnings
from typing import Tuple, List, Optional
from skimage import measure, morphology
import skimage.filters as ski_filters
import scipy.ndimage as ndi

from src import config

warnings.filterwarnings("ignore")

class TopologicalFeatureExtractor:
    """
    BLOCK 3: Topological Feature Extractor Node.
    Extracts geometric and graph descriptors from segmented objects.
    Protects against reading overview or excluded folders via strict white-list matching.
    """

    def __init__(self, image_dir: str, labels_dir: str, output_dir: str,
                 large_image_name: str = "dataset", mask_save_mode: str = 'gray_3filter'):
        self.image_dir = image_dir
        self.labels_dir = labels_dir
        self.output_dir = output_dir
        self.large_image_name = large_image_name
        self.mask_save_mode = mask_save_mode
        self.verification_dir = os.path.join(self.output_dir, "verification_masks")

        self.class_map = {
            0: 'Sphere',
            1: 'Curve',
            2: 'Self-intersecting curve',
            3: 'Intersecting curves',
            4: 'Agglomeration',
            -1: 'Unknown'
        }

    @staticmethod
    def _parse_yolo(label_path: str, img_w: int, img_h: int) -> list:
        objects = []
        with open(label_path, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if not parts:
                    continue
                if len(parts) < 7 or (len(parts)-1) % 2:
                    raise ValueError('Expected YOLO segmentation polygon (at least 3 points): '+label_path)
                class_id = int(parts[0])
                coords = np.array(parts[1:], dtype=float).reshape(-1, 2)
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
        clean_thresh = max(config.MIN_CLEAN_THRESHOLD, int(local_otsu * config.TIER2_THRESHOLD_FACTOR)) if local_otsu > 10 else config.MIN_CLEAN_THRESHOLD
        _, clean_binary = cv2.threshold(isolated_gray, clean_thresh, 255, cv2.THRESH_BINARY)

        padded_gray = cv2.copyMakeBorder(isolated_gray, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
        padded_binary = cv2.copyMakeBorder(clean_binary, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
        return padded_binary, padded_gray

    def _decompose_sub_objects(self, binary_mask: np.ndarray, gray_mask: np.ndarray,
                              min_area: int = config.MIN_SUB_OBJECT_AREA, pad: int = 2) -> List[Tuple[np.ndarray, np.ndarray]]:
        bin_u8 = (binary_mask > 0).astype(np.uint8)
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(bin_u8, connectivity=8)
        valid_labels = [lbl for lbl in range(1, num_labels) if stats[lbl, cv2.CC_STAT_AREA] >= min_area]

        if len(valid_labels) < 2:
            return [(binary_mask, gray_mask)]

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

    def execute(self):
        print(f"   - Processing Directory: {self.image_dir}")
        os.makedirs(self.output_dir, exist_ok=True)

        candidate_files = glob.glob(os.path.join(self.image_dir, '**', '*.png'), recursive=True)
        image_files = [
            f for f in candidate_files
            if re.search(r'tile_\d+', os.path.basename(f))
            and not any(x in f.replace('\\', '/') for x in ['/overview', '/excluded_tiles', '/verification_masks'])
        ]

        if not image_files:
            print(f"   [!] No valid tile images found in '{self.image_dir}'.")
            return

        all_features = []
        records = {}
        manifest_path = os.path.join(self.image_dir,'overview',self.large_image_name+'_tiles_coords.json')
        if os.path.isfile(manifest_path):
            with open(manifest_path,encoding='utf-8') as handle:
                manifest = json.load(handle)
            if isinstance(manifest,dict) and manifest.get('schema_version') == 3:
                records = {r['filename']:r for r in manifest['tiles']}

        for img_path in image_files:
            base_name = os.path.splitext(os.path.basename(img_path))[0]
            label_path = os.path.join(self.labels_dir, f"{base_name}.txt")

            record = records.get(os.path.basename(img_path))
            measurement_path = os.path.join(self.image_dir,record['native_filename']) if record else img_path
            img = cv2.imread(measurement_path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                if record:
                    raise ValueError('Missing native measurement image: '+measurement_path)
                continue

            img_h, img_w = img.shape
            if os.path.exists(label_path):
                # YOLO coordinates are normalized to the square model canvas.
                # Multiplying by the padded native side inverts the resize
                # without rounding the polygon on the smaller image first.
                side = record['transform']['padded_native_shape'][0] if record else None
                objects = self._parse_yolo(label_path, side or img_w, side or img_h)
            else:
                _, envelope_mask = cv2.threshold(img, config.MIN_CLEAN_THRESHOLD, 255, cv2.THRESH_BINARY)
                close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                envelope_closed = cv2.morphologyEx(envelope_mask, cv2.MORPH_CLOSE, close_kernel)
                objects = self._find_contours(envelope_closed, min_area=10)

            if not objects:
                continue

            tile_verify_dir = os.path.join(self.verification_dir, base_name)
            saved_obj_idx = 0

            for class_id, contour in objects:
                x,y,w,h = cv2.boundingRect(contour)
                if x >= img_w or y >= img_h or x+w <= 0 or y+h <= 0:
                    continue  # Annotation lies completely in letterbox padding.
                class_name = self.class_map.get(class_id, 'Unknown')
                clean_binary, clean_gray = self._create_local_mask(contour, img)
                decomposed_units = self._decompose_sub_objects(clean_binary, clean_gray)

                for sub_binary, sub_gray in decomposed_units:
                    geo_features = self._extract_geometry(sub_binary)
                    if not geo_features:
                        continue

                    topo_features = self._extract_topology(sub_binary)
                    saved_obj_idx += 1

                    if not os.path.exists(tile_verify_dir):
                        os.makedirs(tile_verify_dir, exist_ok=True)

                    mask_name = f"obj_{saved_obj_idx:03d}_{class_name}.png"
                    cv2.imwrite(
                        os.path.join(tile_verify_dir, mask_name),
                        sub_gray if self.mask_save_mode == 'gray_3filter' else sub_binary
                    )

                    all_features.append({
                        'Large_Image': self.large_image_name,
                        'Tile_Name': base_name,
                        'Object_ID': saved_obj_idx,
                        'Class_ID': class_id,
                        'Class_Name': class_name,
                        'Measurement_Space': 'source_pixels' if record else 'tile_pixels',
                        'Source_Pixels_Per_Output_Pixel': record['transform']['source_pixels_per_output_pixel'] if record else 1.0,
                        **geo_features,
                        **topo_features
                    })

        if all_features:
            df = pd.DataFrame(all_features)
            csv_path = os.path.join(self.output_dir, f'{self.large_image_name}_features.csv')
            df.to_csv(csv_path, index=False)
            print(f"   [SUCCESS] Extracted features for {len(df)} objects!")
            print(f"   - CSV saved to: {csv_path}")
        else:
            print("   [WARNING] No objects were found in this dataset.")

