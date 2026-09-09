import os
import glob
import cv2
import numpy as np
import pandas as pd
import warnings
from typing import Tuple, List, Optional
from skimage import measure, morphology
import scipy.ndimage as ndi

from src import config

warnings.filterwarnings("ignore")

class TopologicalFeatureExtractor:
    """
    BLOCK 3: Topological Feature Extractor Node.
    Uses a Two-Tier Architecture:
    1. Tier 1 (4-Filter Envelope): Used strictly to discover and bound the complete object
       (keeping beads, dim bridges, and loops together as a single unified entity).
    2. Tier 2 (3-Filter Extraction): Cuts the true, undistorted representation directly from
       the 3-filter tile (Bilateral + TopHat + Gamma) preserving real fiber radius and loop topology.
    """

    def __init__(self, image_dir: str, labels_dir: str, output_dir: str,
                 large_image_name: str = "dataset", mask_save_mode: str = 'gray_3filter'):
        self.image_dir = image_dir
        self.labels_dir = labels_dir
        self.output_dir = output_dir
        self.large_image_name = large_image_name
        self.mask_save_mode = mask_save_mode  # 'gray_3filter' (pure 3-filter tile) or 'binary'
        self.verification_dir = os.path.join(self.output_dir, "verification_masks")

        # 5-Class Taxonomy + Unknown for Production Mode
        self.class_map = {
            0: 'Sphere',
            1: 'Curve',
            2: 'Self-intersecting curve',
            3: 'Intersecting curves',
            4: 'Agglomeration',
            -1: 'Unknown'
        }

    def _parse_yolo(self, label_path: str, img_w: int, img_h: int) -> list:
        """
        Mode 1: Parses YOLO format text files and converts normalized polygons
        into standard OpenCV contour formats (N, 1, 2).
        """
        objects = []
        with open(label_path, 'r') as f:
            lines = f.readlines()
            for line in lines:
                parts = line.strip().split()
                if len(parts) < 3:
                    continue

                class_id = int(parts[0])
                coords = np.array(parts[1:], dtype=float).reshape(-1, 2)

                coords[:, 0] *= img_w
                coords[:, 1] *= img_h

                contour = coords.reshape((-1, 1, 2)).astype(np.int32)
                objects.append((class_id, contour))

        return objects

    def _find_contours(self, binary_img: np.ndarray, min_area: int = 10) -> list:
        """
        Mode 2: Discovers objects on the localized 4-filter envelope mask.
        Filters out microscopic noise using min_area.
        """
        contours, _ = cv2.findContours(binary_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        objects = []
        for contour in contours:
            if cv2.contourArea(contour) >= min_area:
                objects.append((-1, contour))

        return objects

    def _create_local_mask(self, contour: np.ndarray, gray_tile: np.ndarray,
                           otsu_val: float, pad: int = 2) -> Tuple[np.ndarray, np.ndarray]:
        """
        Extracts clean, undistorted object representations directly from the 3-filter tile:
        - padded_gray: The true 3-filter image crop (Bilateral + TopHat + Gamma) preserving real
          fiber diameter, bead textures, and intact loop holes without any binary distortion.
        - padded_binary: Crisp binary mask for graph/geometric feature extraction.
        """
        x, y, w, h = cv2.boundingRect(contour)
        img_h, img_w = gray_tile.shape

        # Safe bounding box coordinates within the 3-filter tile
        y1, y2 = max(0, y), min(img_h, y + h)
        x1, x2 = max(0, x), min(img_w, x + w)
        raw_crop = gray_tile[y1:y2, x1:x2]

        # Stencil mask from outer envelope contour to discard unrelated neighboring particles
        stencil = np.zeros((y2 - y1, x2 - x1), dtype=np.uint8)
        shifted_contour = contour.copy()
        shifted_contour[:, 0, 0] -= x1
        shifted_contour[:, 0, 1] -= y1
        cv2.drawContours(stencil, [shifted_contour], -1, 255, thickness=-1)

        # 1. Undistorted 3-filter representation (Bilateral + TopHat + Gamma)
        isolated_gray = cv2.bitwise_and(raw_crop, raw_crop, mask=stencil)

        # 2. Crisp binary mask computed for mathematical morphology (without 4-filter dilation)
        obj_pixels = isolated_gray[isolated_gray > 0]
        if len(obj_pixels) > 25:
            local_otsu, _ = cv2.threshold(obj_pixels, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            clean_thresh = max(18, int(local_otsu * 0.50))
        else:
            clean_thresh = max(18, int(otsu_val * 0.50))

        _, clean_binary = cv2.threshold(isolated_gray, clean_thresh, 255, cv2.THRESH_BINARY)

        # Apply standard padding to prevent boundary clipping
        padded_gray = cv2.copyMakeBorder(
            isolated_gray, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0
        )
        padded_binary = cv2.copyMakeBorder(
            clean_binary, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0
        )

        return padded_binary, padded_gray

    def _extract_geometry(self, mask: np.ndarray) -> Optional[dict]:
        """Extracts classical geometric features using skimage on the clean binary mask."""
        label_img = (mask > 0).astype(int)
        props = measure.regionprops(label_img)
        if not props:
            return None

        p = props[0]
        minor_axis = p.minor_axis_length
        aspect_ratio = (p.major_axis_length / minor_axis) if minor_axis > 1e-6 else 1.0

        return {
            'Area': p.area,
            'Aspect_Ratio': aspect_ratio,
            'Solidity': p.solidity,
            'Euler_Number': p.euler_number
        }

    def _extract_topology(self, mask: np.ndarray) -> dict:
        """Extracts graph features using skeletonization and 3x3 convolution."""
        skeleton = morphology.skeletonize(mask > 0)

        kernel = np.array([[1, 1, 1],
                           [1, 0, 1],
                           [1, 1, 1]])

        neighbor_count = ndi.convolve(skeleton.astype(int), kernel, mode='constant', cval=0)

        endpoints = np.sum((neighbor_count == 1) & skeleton)
        branch_points = np.sum((neighbor_count > 2) & skeleton)

        return {
            'Endpoints': int(endpoints),
            'Branch_Points': int(branch_points)
        }

    def execute(self):
        """Main orchestrator for Block 3."""
        print(f"   - Processing Directory: {self.image_dir}")

        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.verification_dir, exist_ok=True)

        search_pattern = os.path.join(self.image_dir, '**', '*.png')
        image_files = glob.glob(search_pattern, recursive=True)

        if not image_files:
            print(f"   [!] No .png images found.")
            return

        all_features = []

        for img_path in image_files:
            base_name = os.path.splitext(os.path.basename(img_path))[0]
            label_path = os.path.join(self.labels_dir, f"{base_name}.txt")

            # Load the pristine 3-filter tile (Bilateral + TopHat + Gamma)
            img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue

            img_h, img_w = img.shape

            # Compute tile Otsu baseline (ignoring pure background padding = 0)
            active_pixels = img[img > 0]
            if len(active_pixels) > 50:
                otsu_val, _ = cv2.threshold(active_pixels, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            else:
                otsu_val = 50.0

            # --- DUAL-MODE ROUTER ---
            if os.path.exists(label_path):
                # Mode 1: Training Prep (YOLO labels exist)
                objects = self._parse_yolo(label_path, img_w, img_h)
            else:
                # Mode 2: Object Localization via Tier-1 Safety Envelope (4th Filter)
                # Finds the complete object envelope so beads, faint bridges, and loops stay as ONE entity.
                safety_thresh = max(12, int(otsu_val * config.OTSU_SAFETY_FACTOR))
                _, envelope_mask = cv2.threshold(img, safety_thresh, 255, cv2.THRESH_BINARY)
                close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                envelope_closed = cv2.morphologyEx(envelope_mask, cv2.MORPH_CLOSE, close_kernel)

                objects = self._find_contours(envelope_closed, min_area=10)

            if not objects:
                continue

            tile_verify_dir = os.path.join(self.verification_dir, base_name)
            os.makedirs(tile_verify_dir, exist_ok=True)

            for idx, (class_id, contour) in enumerate(objects):
                class_name = self.class_map.get(class_id, 'Unknown')

                # Extract both clean binary (for math) and undistorted 3-filter tile crop (for saving)
                clean_binary, clean_gray = self._create_local_mask(contour, img, otsu_val=otsu_val)

                geo_features = self._extract_geometry(clean_binary)
                if not geo_features:
                    continue

                topo_features = self._extract_topology(clean_binary)

                # Save EXACTLY ONE file: the pristine 3-filter image crop
                mask_filename = f"obj_{idx:03d}_{class_name}.png"
                if self.mask_save_mode == 'gray_3filter':
                    # Saves the undistorted 3-filter tile crop (Bilateral + TopHat + Gamma)
                    cv2.imwrite(os.path.join(tile_verify_dir, mask_filename), clean_gray)
                else:
                    cv2.imwrite(os.path.join(tile_verify_dir, mask_filename), clean_binary)

                feature_row = {
                    'Large_Image': self.large_image_name,
                    'Tile_Name': base_name,
                    'Object_ID': idx + 1,
                    'Class_ID': class_id,
                    'Class_Name': class_name,
                    **geo_features,
                    **topo_features
                }
                all_features.append(feature_row)

        if all_features:
            df = pd.DataFrame(all_features)
            csv_path = os.path.join(self.output_dir, f'{self.large_image_name}_features.csv')
            df.to_csv(csv_path, index=False)
            print(f"   [SUCCESS] Extracted features for {len(df)} objects!")
            print(f"   - CSV saved to: {csv_path}")

            try:
                excel_path = os.path.join(self.output_dir, f'{self.large_image_name}_features.xlsx')
                df.to_excel(excel_path, index=False)
                print(f"   - Excel saved to: {excel_path}")
            except ImportError:
                pass
        else:
            print("   [WARNING] No objects were processed across all images in this folder.")