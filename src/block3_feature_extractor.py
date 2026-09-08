import os
import glob
import cv2
import numpy as np
import pandas as pd
import warnings
from skimage import measure, morphology
import scipy.ndimage as ndi

warnings.filterwarnings("ignore")


class TopologicalFeatureExtractor:
    """
    BLOCK 3: Topological and Geometrical Feature Extractor Node.
    Analyzes binary objects derived either from YOLO annotations (Training Mode)
    or raw contours (Production Mode).
    """

    def __init__(self, image_dir: str, labels_dir: str, output_dir: str, large_image_name: str = "dataset"):
        self.image_dir = image_dir
        self.labels_dir = labels_dir
        self.output_dir = output_dir
        self.large_image_name = large_image_name
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

                # Un-normalize coordinates to absolute pixel values
                coords[:, 0] *= img_w
                coords[:, 1] *= img_h

                # Reshape to (N, 1, 2) and cast to int32 to mimic cv2.findContours output
                contour = coords.reshape((-1, 1, 2)).astype(np.int32)
                objects.append((class_id, contour))

        return objects

    def _find_contours(self, binary_img: np.ndarray, min_area: int = 5) -> list:
        """
        Mode 2: Finds objects automatically.
        CRITICAL FIX: Filters out microscopic dust/noise using min_area.
        """
        contours, _ = cv2.findContours(binary_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        objects = []
        for contour in contours:
            # Ignore tiny noise artifacts
            if cv2.contourArea(contour) >= min_area:
                objects.append((-1, contour))

        return objects

    def _create_local_mask(self, contour: np.ndarray, img: np.ndarray, pad: int = 2) -> np.ndarray:
        """
        Isolates the object into a minimal bounding box canvas.
        Extracts real pixels using a bitwise_and stencil to preserve holes (topology).
        """
        x, y, w, h = cv2.boundingRect(contour)
        img_h, img_w = img.shape

        # Safe bounding box extraction
        y1, y2 = max(0, y), min(img_h, y + h)
        x1, x2 = max(0, x), min(img_w, x + w)
        raw_crop = img[y1:y2, x1:x2]

        # Create a stencil and draw the filled contour with a negative offset
        stencil = np.zeros((y2 - y1, x2 - x1), dtype=np.uint8)
        shifted_contour = contour.copy()
        shifted_contour[:, 0, 0] -= x1
        shifted_contour[:, 0, 1] -= y1
        cv2.fillPoly(stencil, [shifted_contour], 255)

        # Extract real object pixels (safely keeping holes intact)
        isolated_object = cv2.bitwise_and(raw_crop, raw_crop, mask=stencil)

        # Apply padding to prevent skeleton artifacts at the borders
        padded_canvas = cv2.copyMakeBorder(
            isolated_object,
            top=pad, bottom=pad, left=pad, right=pad,
            borderType=cv2.BORDER_CONSTANT,
            value=0
        )

        return padded_canvas

    def _extract_geometry(self, mask: np.ndarray) -> dict:
        """Extracts classical geometric features using skimage."""
        label_img = (mask > 0).astype(int)
        props = measure.regionprops(label_img)
        if not props:
            return None

        p = props[0]

        # Safeguard against zero division
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

            img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue

            # DUST FIX: Binarize the image first for reliable contour detection and cropping
            _, binary_img = cv2.threshold(img, 10, 255, cv2.THRESH_BINARY)
            img_h, img_w = binary_img.shape

            if os.path.exists(label_path):
                objects = self._parse_yolo(label_path, img_w, img_h)
            else:
                objects = self._find_contours(binary_img, min_area=5)

            if not objects:
                continue

            tile_verify_dir = os.path.join(self.verification_dir, base_name)
            os.makedirs(tile_verify_dir, exist_ok=True)

            for idx, (class_id, contour) in enumerate(objects):
                class_name = self.class_map.get(class_id, 'Unknown')

                local_mask = self._create_local_mask(contour, binary_img)

                geo_features = self._extract_geometry(local_mask)
                if not geo_features:
                    continue

                topo_features = self._extract_topology(local_mask)

                mask_filename = f"obj_{idx:03d}_{class_name}.png"
                cv2.imwrite(os.path.join(tile_verify_dir, mask_filename), local_mask)

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

            # Save to classic CSV
            csv_path = os.path.join(self.output_dir, f'{self.large_image_name}_features.csv')
            df.to_csv(csv_path, index=False)
            print(f"   [SUCCESS] Extracted features for {len(df)} objects!")
            print(f"   - CSV saved to: {csv_path}")

            # Attempt to save in true Excel (.xlsx) format
            try:
                excel_path = os.path.join(self.output_dir, f'{self.large_image_name}_features.xlsx')
                df.to_excel(excel_path, index=False)
                print(f"   - Excel saved to: {excel_path}")
            except ImportError:
                print(
                    "   - [Note] 'openpyxl' module not found. Skipping .xlsx export. You can still open the .csv in Excel.")

        else:
            print("   [WARNING] No objects were processed across all images in this folder.")