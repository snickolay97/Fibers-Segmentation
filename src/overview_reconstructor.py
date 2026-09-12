import os
import glob
import json
import re
import cv2
import numpy as np
import tifffile
from typing import Optional, List, Dict, Tuple

from src import config


class HighResOverviewReconstructor:
    """
    High-Resolution Global Overview & Tile Mosaic Engine.
    Renders pure puzzle-piece seams (r_seam, b_seam) without overlapping bounding
    box lines, producing a clean mosaic of tiles within the microfluidic channel.
    """

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = project_root or os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    @staticmethod
    def extract_tile_id(filename: str) -> int:
        """Extracts integer ID from tile filename (e.g. '..._tile_0042.png' -> 42)."""
        match = re.search(r'tile_(\d+)', filename)
        return int(match.group(1)) if match else 0

    def _load_base_canvas(self, dataset_name: str, canvas_w: int, canvas_h: int) -> Tuple[np.ndarray, int, int]:
        """Loads true background image from data/1_raw_large_images/ scaled to canvas dimensions."""
        input_dir = os.path.join(self.project_root, config.INPUT_DIR)
        raw_candidates = (glob.glob(os.path.join(input_dir, f"{dataset_name}.tif*")) +
                          glob.glob(os.path.join(input_dir, f"{dataset_name}.*")) +
                          glob.glob(os.path.join(input_dir, '*.tif*')))

        if raw_candidates:
            target_raw_path = raw_candidates[0]
            print(f"     [+] Reading raw background from: {os.path.basename(target_raw_path)}...")
            try:
                raw_img = tifffile.imread(target_raw_path)
                full_h, full_w = raw_img.shape[:2]

                if raw_img.dtype == np.uint16:
                    raw_img = (raw_img / 256).astype(np.uint8)
                elif raw_img.dtype != np.uint8:
                    raw_img = np.clip(raw_img, 0, 255).astype(np.uint8)

                if raw_img.ndim == 2:
                    resized_gray = cv2.resize(raw_img, (canvas_w, canvas_h), interpolation=cv2.INTER_AREA)
                    canvas_bgr = cv2.cvtColor(resized_gray, cv2.COLOR_GRAY2BGR)
                elif raw_img.ndim == 3:
                    if raw_img.shape[2] >= 3:
                        raw_img = raw_img[:, :, :3]
                    resized_color = cv2.resize(raw_img, (canvas_w, canvas_h), interpolation=cv2.INTER_AREA)
                    canvas_bgr = cv2.cvtColor(resized_color, cv2.COLOR_RGB2BGR)
                else:
                    canvas_bgr = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)

                return canvas_bgr, full_w, full_h

            except Exception as e:
                print(f"     [!] Warning: Could not read raw TIFF ({e}). Initializing fallback canvas.")

        return np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8), 17920, 19440

    def _resolve_tile_coordinates(self, base_dir: str, dataset_name: str,
                                  tile_files: List[str], full_w: int, full_h: int) -> Dict[int, Dict]:
        """Checks for JSON coordinates manifest in overview/ subfolder or base directory."""
        candidates = [
            os.path.join(base_dir, 'overview', f"{dataset_name}_tiles_coords.json"),
            os.path.join(base_dir, f"{dataset_name}_tiles_coords.json")
        ]

        for coords_file in candidates:
            if os.path.exists(coords_file):
                try:
                    with open(coords_file, 'r', encoding='utf-8') as f:
                        records = json.load(f)
                        print(
                            f"     [+] Loaded {len(records)} exact tile coordinates and seams from '{os.path.basename(coords_file)}'.")
                        return {rec['id']: rec for rec in records}
                except Exception as exc:
                    print(f"     [!] Could not parse {coords_file}: {exc}")

        print(f"     [i] Synthesizing precise grid layout for {len(tile_files)} tiles...")
        target_size = getattr(config, 'TARGET_SIZE', 1500)
        base_step = getattr(config, 'MARGIN_START', 1300)

        num_cols = max(1, int(np.ceil(full_w / base_step)))
        step_x = full_w / float(num_cols)

        num_tiles = len(tile_files)
        num_rows = max(1, int(np.ceil(num_tiles / float(num_cols))))
        step_y = full_h / float(num_rows)

        tile_coords = {}
        for idx, tile_path in enumerate(tile_files):
            t_id = self.extract_tile_id(tile_path)
            col = idx % num_cols
            row = idx // num_cols

            x1 = int(col * step_x)
            y1 = int(row * step_y)
            x2 = min(full_w, x1 + target_size)
            y2 = min(full_h, y1 + target_size)

            tile_coords[t_id] = {
                'id': t_id,
                'x1': x1,
                'y1': y1,
                'x2': x2,
                'y2': y2
            }

        return tile_coords

    def reconstruct(self,
                    dataset_name: str,
                    target_dim: Optional[int] = None,
                    source_type: str = 'filtered') -> Optional[str]:
        """Builds a single, clean global overview map without overlapping bounding box lines."""
        target_dim = target_dim or getattr(config, 'OVERVIEW_MAP_SIZE', 6000)
        print(f"\n---> [Overview Engine] Generating {target_dim}x{target_dim} px Map for '{dataset_name}'...")

        folder_name = '2_sliced_tiles' if source_type == 'filtered' else '3_raw_sliced_tiles'
        base_dir = os.path.join(self.project_root, 'data', folder_name, dataset_name)
        if not os.path.exists(base_dir):
            print(f"[!] Directory not found: {base_dir}")
            return None

        overview_dir = os.path.join(base_dir, 'overview')
        os.makedirs(overview_dir, exist_ok=True)

        search_pattern = os.path.join(base_dir, '*.png')
        tile_files = [
            f for f in glob.glob(search_pattern)
            if re.search(r'tile_\d+', os.path.basename(f)) and
               '_TILE_INDEX_MAP' not in f and 'excluded_tiles' not in f
        ]

        if not tile_files:
            print(f"[!] No tile images found in '{base_dir}'. Run slicing first.")
            return None

        tile_files.sort(key=self.extract_tile_id)

        input_dir = os.path.join(self.project_root, config.INPUT_DIR)
        raw_candidates = (glob.glob(os.path.join(input_dir, f"{dataset_name}.tif*")) +
                          glob.glob(os.path.join(input_dir, f"{dataset_name}.*")) +
                          glob.glob(os.path.join(input_dir, '*.tif*')))

        full_w, full_h = 17920, 19440
        if raw_candidates:
            try:
                with tifffile.TiffFile(raw_candidates[0]) as tif:
                    full_h, full_w = tif.pages[0].shape[:2]
            except Exception:
                pass

        scale = target_dim / max(full_h, full_w)
        canvas_w = int(full_w * scale)
        canvas_h = int(full_h * scale)

        print(f"     Full Dimensions: {full_w}x{full_h} px")
        print(f"     Canvas Dimensions: {canvas_w}x{canvas_h} px (Scale: {scale:.4f})")

        canvas, full_w, full_h = self._load_base_canvas(dataset_name, canvas_w, canvas_h)
        tile_coords = self._resolve_tile_coordinates(base_dir, dataset_name, tile_files, full_w, full_h)

        has_curved_seams = any('r_seam' in rec and len(rec['r_seam']) > 1 for rec in tile_coords.values())
        font = cv2.FONT_HERSHEY_SIMPLEX

        # Outer canvas frame boundaries
        cv2.rectangle(canvas, (0, 0), (canvas_w - 1, canvas_h - 1), (0, 180, 180), 2)

        if has_curved_seams:
            print("     [+] Rendering pure puzzle seams (zero overlapping bounding box lines)...")

            # Draw ONLY the actual physical division seams:
            # - Right seam: separates tile from right neighbor
            # - Bottom seam: separates tile from bottom neighbor
            # NO horizontal or vertical bounding box lines cutting through adjacent tiles!
            for tile_path in tile_files:
                t_id = self.extract_tile_id(tile_path)
                if t_id not in tile_coords:
                    continue

                rec = tile_coords[t_id]
                x1_s = int(rec['x1'] * scale)
                y1_s = int(rec['y1'] * scale)
                x2_s = min(canvas_w - 1, int(rec['x2'] * scale))
                y2_s = min(canvas_h - 1, int(rec['y2'] * scale))

                # 1. Right Seam (Curved Dijkstra or straight corridor cut)
                if 'r_seam' in rec and len(rec['r_seam']) > 1:
                    r_pts = (np.array(rec['r_seam'], dtype=np.float32) * scale).astype(np.int32)
                    cv2.polylines(canvas, [r_pts], False, (0, 255, 255), 2, cv2.LINE_AA)
                else:
                    if x2_s < canvas_w - 2:
                        cv2.line(canvas, (x2_s, y1_s), (x2_s, y2_s), (0, 255, 255), 2)

                # 2. Bottom Seam (Curved Dijkstra or straight corridor cut)
                if 'b_seam' in rec and len(rec['b_seam']) > 1:
                    b_pts = (np.array(rec['b_seam'], dtype=np.float32) * scale).astype(np.int32)
                    cv2.polylines(canvas, [b_pts], False, (0, 255, 255), 2, cv2.LINE_AA)
                else:
                    if y2_s < canvas_h - 2:
                        cv2.line(canvas, (x1_s, y2_s), (x2_s, y2_s), (0, 255, 255), 2)

                # 3. Outer image borders only (never internal dividing lines)
                if rec['x1'] == 0:
                    cv2.line(canvas, (0, y1_s), (0, y2_s), (0, 255, 255), 2)
                if rec['y1'] == 0:
                    cv2.line(canvas, (x1_s, 0), (x2_s, 0), (0, 255, 255), 2)

        else:
            print("     [+] Rendering non-overlapping grid partitions...")
            # Fallback for older datasets without seam arrays:
            # Draw unified boundary cells to prevent overlapping frames
            for tile_path in tile_files:
                t_id = self.extract_tile_id(tile_path)
                if t_id not in tile_coords:
                    continue

                rec = tile_coords[t_id]
                x1_s = int(rec['x1'] * scale)
                y1_s = int(rec['y1'] * scale)
                x2_s = min(canvas_w - 1, int(rec['x2'] * scale))
                y2_s = min(canvas_h - 1, int(rec['y2'] * scale))

                cv2.line(canvas, (x2_s, y1_s), (x2_s, y2_s), (0, 255, 255), 2)
                cv2.line(canvas, (x1_s, y2_s), (x2_s, y2_s), (0, 255, 255), 2)

        # Draw clean ID badges inside each tile's interior
        for tile_path in tile_files:
            t_id = self.extract_tile_id(tile_path)
            if t_id not in tile_coords:
                continue

            rec = tile_coords[t_id]
            x1_s = int(rec['x1'] * scale)
            y1_s = int(rec['y1'] * scale)
            x2_s = min(canvas_w - 1, int(rec['x2'] * scale))

            label = f"#{t_id:04d}"
            font_scale = max(0.65, min(1.2, (x2_s - x1_s) / 450.0))
            thickness = max(2, int(font_scale * 2.2))

            (tw, th), baseline = cv2.getTextSize(label, font, font_scale, thickness)
            tx = x1_s + 12
            ty = y1_s + th + 12

            # Semi-transparent dark background for pristine badge legibility
            cv2.rectangle(canvas, (tx - 5, ty - th - 5), (tx + tw + 6, ty + baseline + 4), (0, 0, 0), -1)
            cv2.rectangle(canvas, (tx - 5, ty - th - 5), (tx + tw + 6, ty + baseline + 4), (0, 255, 0), 1)
            cv2.putText(canvas, label, (tx, ty), font, font_scale, (0, 255, 0), thickness, cv2.LINE_AA)

        # Save single canonical overview map without creating duplicate files
        out_filename = f"{dataset_name}_TILE_INDEX_MAP_{target_dim}px.png"
        output_path = os.path.join(overview_dir, out_filename)
        cv2.imwrite(output_path, canvas)

        print(f"[SUCCESS] High-Resolution Puzzle Map Generated: {output_path}")
        return output_path