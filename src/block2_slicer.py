import os
import cv2
import numpy as np
from skimage.graph import MCP_Geometric
from typing import Tuple

from src import config


class SmartSlicer:
    """
    BLOCK 2: Smart Slicer Node.
    Slices the image into tiles using Topographical Seams (Dijkstra) to avoid cutting objects.
    Enforces the Shared Border Rule and includes Dynamic Expansion to bypass obstacles.
    """

    def __init__(self,
                 target_size: int = config.TARGET_SIZE,
                 margin_start: int = config.MARGIN_START,
                 margin_end: int = config.MARGIN_END):
        self.target_size = target_size
        self.margin_start = margin_start
        self.margin_end = margin_end

    def find_vertical_seam(self, mask_zone: np.ndarray) -> Tuple[np.ndarray, float]:
        """Finds the lowest cost path. Returns the seam and its minimum cost."""
        h, w = mask_zone.shape

        bg_mask = (mask_zone == 0).astype(np.uint8)
        dist = cv2.distanceTransform(bg_mask, cv2.DIST_L2, 5)

        cost_map = 1.0 / (dist + 1e-3)
        cost_map[mask_zone > 0] = 10000.0

        mcp = MCP_Geometric(cost_map)
        starts = [[0, c] for c in range(w)]

        cumulative_costs, _ = mcp.find_costs(starts)
        ends = [[h - 1, c] for c in range(w)]

        min_cost = float('inf')
        best_end = None
        for end_pt in ends:
            cst = cumulative_costs[tuple(end_pt)]
            if cst < min_cost:
                min_cost = cst
                best_end = tuple(end_pt)

        if best_end is None:
            return np.full(h, w // 2), float('inf')

        path = mcp.traceback(best_end)

        seam_x = np.full(h, -1, dtype=int)
        for py, px in path:
            seam_x[py] = px

        for i in range(1, h):
            if seam_x[i] == -1:
                seam_x[i] = seam_x[i - 1]
        for i in range(h - 2, -1, -1):
            if seam_x[i] == -1:
                seam_x[i] = seam_x[i + 1]

        return seam_x, min_cost

    def find_horizontal_seam(self, mask_zone: np.ndarray) -> Tuple[np.ndarray, float]:
        """Finds the lowest cost path. Returns the seam and its minimum cost."""
        h, w = mask_zone.shape
        bg_mask = (mask_zone == 0).astype(np.uint8)
        dist = cv2.distanceTransform(bg_mask, cv2.DIST_L2, 5)

        cost_map = 1.0 / (dist + 1e-3)
        cost_map[mask_zone > 0] = 10000.0

        mcp = MCP_Geometric(cost_map)
        starts = [[r, 0] for r in range(h)]

        cumulative_costs, _ = mcp.find_costs(starts)
        ends = [[r, w - 1] for r in range(h)]

        min_cost = float('inf')
        best_end = None
        for end_pt in ends:
            cst = cumulative_costs[tuple(end_pt)]
            if cst < min_cost:
                min_cost = cst
                best_end = tuple(end_pt)

        if best_end is None:
            return np.full(w, h // 2), float('inf')

        path = mcp.traceback(best_end)

        seam_y = np.full(w, -1, dtype=int)
        for py, px in path:
            seam_y[px] = py

        for i in range(1, w):
            if seam_y[i] == -1:
                seam_y[i] = seam_y[i - 1]
        for i in range(w - 2, -1, -1):
            if seam_y[i] == -1:
                seam_y[i] = seam_y[i + 1]

        return seam_y, min_cost

    def slice(self, img: np.ndarray, raw_img: np.ndarray, mask: np.ndarray, base_name: str, output_dir: str,
              raw_output_dir: str):
        """Orchestrates the intelligent topographical tiling with dynamic window expansion."""
        H, W = img.shape[:2]
        extracted_mask = np.zeros((H, W), dtype=bool)

        y_anchor = 0
        tile_count = 0

        print("   - Starting Adaptive Topographical Slicing...")

        while y_anchor < H:
            x_anchor = 0
            bottom_seams = []

            while x_anchor < W:
                tile_count += 1
                y_span = min(y_anchor + self.target_size, H)

                # --- 1. RIGHT BOUNDARY SEARCH WITH DYNAMIC EXPANSION ---
                current_margin_x = self.margin_start
                while True:
                    x_search_start = min(x_anchor + current_margin_x, W)
                    x_search_end = min(x_anchor + self.margin_end, W)
                    zone_r = mask[y_anchor:y_span, x_search_start:x_search_end]

                    if zone_r.size == 0 or x_search_start == W:
                        R_boundary = np.full(y_span - y_anchor, W)
                        break

                    col_sums = np.sum(zone_r, axis=0)
                    if np.any(col_sums == 0):
                        local_x = np.where(col_sums == 0)[0][0]
                        R_boundary = np.full(y_span - y_anchor, x_search_start + local_x)
                        break
                    else:
                        temp_R_boundary, R_cost = self.find_vertical_seam(zone_r)

                        if R_cost < 10000.0 or current_margin_x <= config.MIN_MARGIN_LIMIT:
                            R_boundary = temp_R_boundary + x_search_start
                            break
                        else:
                            current_margin_x -= config.DYNAMIC_EXPANSION_STEP

                # --- 2. BOTTOM BOUNDARY SEARCH WITH DYNAMIC EXPANSION ---
                x_span = min(x_anchor + self.target_size, W)
                current_margin_y = self.margin_start

                while True:
                    y_search_start = min(y_anchor + current_margin_y, H)
                    y_search_end = min(y_anchor + self.margin_end, H)
                    zone_b = mask[y_search_start:y_search_end, x_anchor:x_span]

                    if zone_b.size == 0 or y_search_start == H:
                        B_boundary = np.full(x_span - x_anchor, H)
                        break

                    row_sums = np.sum(zone_b, axis=1)
                    if np.any(row_sums == 0):
                        local_y = np.where(row_sums == 0)[0][0]
                        B_boundary = np.full(x_span - x_anchor, y_search_start + local_y)
                        break
                    else:
                        temp_B_boundary, B_cost = self.find_horizontal_seam(zone_b)

                        if B_cost < 10000.0 or current_margin_y <= config.MIN_MARGIN_LIMIT:
                            B_boundary = temp_B_boundary + y_search_start
                            break
                        else:
                            current_margin_y -= config.DYNAMIC_EXPANSION_STEP

                # --- 3. BOUNDING BOX EXTRACTION & MEMORIZATION ---
                max_x = max(R_boundary) if R_boundary.size > 0 else W
                max_y = max(B_boundary) if B_boundary.size > 0 else H

                local_mask = np.ones((max_y - y_anchor, max_x - x_anchor), dtype=bool)

                for i, r_val in enumerate(R_boundary):
                    if i < local_mask.shape[0]:
                        rel_x = r_val - x_anchor
                        if rel_x < local_mask.shape[1]:
                            local_mask[i, max(0, rel_x):] = False

                for j, b_val in enumerate(B_boundary):
                    if j < local_mask.shape[1]:
                        rel_y = b_val - y_anchor
                        if rel_y < local_mask.shape[0]:
                            local_mask[max(0, rel_y):, j] = False

                available_pixels = ~extracted_mask[y_anchor:max_y, x_anchor:max_x]
                final_tile_mask = local_mask & available_pixels

                if not np.any(final_tile_mask):
                    x_anchor = min(R_boundary) if R_boundary.size > 0 else W
                    continue

                extracted_mask[y_anchor:max_y, x_anchor:max_x] |= final_tile_mask

                tile_img = img[y_anchor:max_y, x_anchor:max_x].copy()
                tile_img[~final_tile_mask] = 0

                raw_tile_img = raw_img[y_anchor:max_y, x_anchor:max_x].copy()
                raw_tile_img[~final_tile_mask] = 0

                # --- 4. PERFECT PADDING ---
                pad_bottom = max(0, self.target_size - tile_img.shape[0])
                pad_right = max(0, self.target_size - tile_img.shape[1])

                padded_tile = cv2.copyMakeBorder(tile_img, 0, pad_bottom, 0, pad_right, cv2.BORDER_CONSTANT, value=0)
                raw_padded_tile = cv2.copyMakeBorder(raw_tile_img, 0, pad_bottom, 0, pad_right, cv2.BORDER_CONSTANT,
                                                     value=0)

                save_name = f"{base_name}_tile_{tile_count:04d}.png"
                cv2.imwrite(os.path.join(output_dir, save_name), padded_tile)
                cv2.imwrite(os.path.join(raw_output_dir, save_name), raw_padded_tile)

                x_anchor = min(R_boundary) if R_boundary.size > 0 else W
                if B_boundary.size > 0:
                    bottom_seams.append(min(B_boundary))

            if bottom_seams:
                y_anchor = min(bottom_seams)
            else:
                y_anchor += self.target_size

        print(f"   - Done! Generated {tile_count} perfectly tailored {self.target_size}x{self.target_size} tiles.")