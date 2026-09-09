import os
import cv2
import numpy as np
import imageio
from skimage.graph import MCP_Geometric
from typing import Tuple, Optional

from src import config


class SmartSlicer:
    """
    BLOCK 2: Smart Slicer Node.
    Advanced Topographical Slicer with Strict Bidirectional Search:
    1. Scans Right for a clean cut.
    2. Scans Left for a clean cut if Right fails.
    3. Calculates Dijkstra on BOTH sides and picks the lowest cost if straight cuts fail.

    Generates comprehensive 1500x1500 visualizations of the search process for every tile.
    """

    def __init__(self,
                 target_size: int = config.TARGET_SIZE,
                 margin_start: int = config.MARGIN_START,
                 margin_end: int = config.MARGIN_END,
                 enable_animation: bool = False,
                 animation_dir: str = 'data/animations'):

        self.base_step = margin_start
        self.max_step = margin_end
        self.target_size = target_size

        self.enable_animation = enable_animation
        self.animation_dir = animation_dir

        if self.enable_animation and not os.path.exists(self.animation_dir):
            os.makedirs(self.animation_dir, exist_ok=True)

    def _create_search_gif(self, mask_block: np.ndarray,
                           right_cols: Optional[np.ndarray], left_cols: Optional[np.ndarray],
                           straight_seam: Optional[int], dijkstra_seam: Optional[np.ndarray],
                           save_name: str):
        """
        Generates a STRICTLY 1500x1500 GIF animating the logical search:
        - Orange line: Scanning Right
        - Blue line: Scanning Left (if Right failed)
        - Green line: Final successful cut (Straight or Topographical)
        """
        frames = []
        h, w = mask_block.shape

        # 1. Pad the animation canvas to be EXACTLY target_size x target_size (1500x1500)
        pad_bottom = max(0, self.target_size - h)
        pad_right = max(0, self.target_size - w)
        padded_mask = cv2.copyMakeBorder(mask_block, 0, pad_bottom, 0, pad_right, cv2.BORDER_CONSTANT, value=0)

        h_pad, w_pad = padded_mask.shape

        # 2. Base canvas setup (Fibers = White, Background = Dark Blue)
        base_frame = np.zeros((h_pad, w_pad, 3), dtype=np.uint8)
        base_frame[padded_mask > 0] = [255, 255, 255]
        base_frame[padded_mask == 0] = [40, 20, 20]

        # Initial hold for visual context
        for _ in range(3):
            frames.append(base_frame.copy())

        # Frame step optimization to prevent RAM overload on 1500x1500 frames
        anim_step = 10

        # Phase 1: Scan Right
        if right_cols is not None:
            for col in right_cols[::anim_step]:
                draw_frame = base_frame.copy()
                cv2.line(draw_frame, (int(col), 0), (int(col), h_pad), (0, 150, 255), 2)  # Orange
                frames.append(draw_frame)

        # Phase 2: Scan Left (Only runs if Right failed)
        if left_cols is not None:
            reversed_left = left_cols[::-1]  # Animate moving backwards
            for col in reversed_left[::anim_step]:
                draw_frame = base_frame.copy()
                cv2.line(draw_frame, (int(col), 0), (int(col), h_pad), (255, 100, 0), 2)  # Blue
                frames.append(draw_frame)

        # Phase 3: Final Cut Visualization
        draw_frame = base_frame.copy()

        if straight_seam is not None:
            # Draw the successful straight vertical line fully
            cv2.line(draw_frame, (int(straight_seam), 0), (int(straight_seam), h_pad), (0, 255, 0), 3)
            frames.append(draw_frame.copy())

        elif dijkstra_seam is not None:
            # Draw the continuous Dijkstra topographical path progressively
            pts = np.array([[(int(x), int(y)) for y, x in enumerate(dijkstra_seam)]], dtype=np.int32)
            draw_step = max(1, len(dijkstra_seam) // 15)

            for i in range(0, len(dijkstra_seam), draw_step):
                chunk_pts = pts[:, :i + draw_step, :]
                cv2.polylines(draw_frame, [chunk_pts], False, (0, 255, 0), 3)
                frames.append(draw_frame.copy())

        # Hold the final established cut so the user can see it
        for _ in range(8):
            frames.append(draw_frame.copy())

        gif_path = os.path.join(self.animation_dir, save_name)
        imageio.mimsave(gif_path, frames, fps=15)

    def find_topographical_seam(self, mask_zone: np.ndarray, axis: str) -> Tuple[np.ndarray, float]:
        """Calculates Dijkstra minimum cost path."""
        h, w = mask_zone.shape
        bg_mask = (mask_zone == 0).astype(np.uint8)
        dist = cv2.distanceTransform(bg_mask, cv2.DIST_L2, 5)

        cost_map = 1.0 / (dist ** config.SEAM_REPULSION_POWER + 1e-3)
        cost_map[mask_zone > 0] = config.SEAM_OBSTACLE_PENALTY

        mcp = MCP_Geometric(cost_map)

        if axis == 'vertical':
            starts = [[0, c] for c in range(w)]
            cumulative_costs, _ = mcp.find_costs(starts)
            ends = [[h - 1, c] for c in range(w)]
        else:
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
            return np.full(h if axis == 'vertical' else w, (w // 2 if axis == 'vertical' else h // 2)), float('inf')

        path = mcp.traceback(best_end)

        seam = np.full(h if axis == 'vertical' else w, -1, dtype=int)
        for py, px in path:
            if axis == 'vertical':
                seam[py] = px
            else:
                seam[px] = py

        # Forward and backward fill to bridge any diagonal jumps
        limit = h if axis == 'vertical' else w
        for i in range(1, limit):
            if seam[i] == -1: seam[i] = seam[i - 1]
        for i in range(limit - 2, -1, -1):
            if seam[i] == -1: seam[i] = seam[i + 1]

        return seam, min_cost

    def slice(self, filtered_img: np.ndarray, raw_img: np.ndarray, mask: np.ndarray,
              base_name: str, output_dir: str, raw_output_dir: str):
        """Orchestrates the intelligent topographical tiling with bidirectional search."""
        H, W = mask.shape[:2]
        extracted_mask = np.zeros((H, W), dtype=bool)

        y_anchor = 0
        tile_count = 0
        search_window = self.max_step - self.base_step

        print(f"   - Starting Adaptive Bidirectional Slicing on {W}x{H} image...")

        while y_anchor < H:
            x_anchor = 0
            bottom_seams = []

            while x_anchor < W:
                tile_count += 1

                # Setup visual block for processing limits
                y_span = min(y_anchor + self.target_size, H)
                x_span = min(x_anchor + self.target_size, W)
                anim_block = mask[y_anchor:y_span, x_anchor:x_span]

                print(
                    f"      [Slicer] Processing Tile {tile_count:04d} (X: {x_anchor}->{x_span}, Y: {y_anchor}->{y_span})...")

                # ==========================================
                # 1. BIDIRECTIONAL RIGHT BOUNDARY SEARCH (X-axis)
                # ==========================================
                R_boundary = np.array([])
                target_x = min(x_anchor + self.base_step, W)

                right_cols_to_anim = None
                left_cols_to_anim = None
                straight_anim_seam = None
                dijkstra_anim_seam = None

                if target_x < W:
                    # ZONE RIGHT: [base_step : max_step]
                    x_right_end = min(x_anchor + self.max_step, W)
                    zone_r = mask[y_anchor:y_span, target_x: x_right_end]

                    # ZONE LEFT: [base_step - window : base_step]
                    x_left_start = max(x_anchor, target_x - search_window)
                    zone_l = mask[y_anchor:y_span, x_left_start: target_x]

                    col_sums_r = np.sum(zone_r, axis=0)
                    col_sums_l = np.sum(zone_l, axis=0)

                    right_cols_to_anim = np.arange(target_x - x_anchor, x_right_end - x_anchor)
                    left_cols_to_anim = np.arange(x_left_start - x_anchor, target_x - x_anchor)

                    # LOGIC 1: Search Right
                    if np.any(col_sums_r == 0):
                        # Grab the right-most possible clean cut
                        local_x = np.where(col_sums_r == 0)[0][-1]
                        abs_x = target_x + local_x
                        R_boundary = np.full(y_span - y_anchor, abs_x)
                        straight_anim_seam = abs_x - x_anchor
                        left_cols_to_anim = None  # Don't animate left if right succeeded

                    # LOGIC 2: Search Left
                    elif np.any(col_sums_l == 0):
                        # Grab the right-most possible clean cut in the left zone
                        local_x = np.where(col_sums_l == 0)[0][-1]
                        abs_x = x_left_start + local_x
                        R_boundary = np.full(y_span - y_anchor, abs_x)
                        straight_anim_seam = abs_x - x_anchor

                    # LOGIC 3: Dynamic Dijkstra Right AND Left, Pick Best
                    else:
                        seam_r, cost_r = self.find_topographical_seam(zone_r, 'vertical')
                        seam_l, cost_l = self.find_topographical_seam(zone_l, 'vertical')

                        if cost_r <= cost_l:
                            R_boundary = seam_r + target_x
                            dijkstra_anim_seam = seam_r + (target_x - x_anchor)
                        else:
                            R_boundary = seam_l + x_left_start
                            dijkstra_anim_seam = seam_l + (x_left_start - x_anchor)
                else:
                    R_boundary = np.full(y_span - y_anchor, W)
                    straight_anim_seam = W - x_anchor

                # Generate Search Animation for X-axis (Rendered as 1500x1500)
                if self.enable_animation and anim_block.size > 0:
                    self._create_search_gif(anim_block, right_cols_to_anim, left_cols_to_anim,
                                            straight_anim_seam, dijkstra_anim_seam,
                                            f"{base_name}_{tile_count:04d}_X_Search.gif")

                # ==========================================
                # 2. BOTTOM BOUNDARY SEARCH (Y-axis - DOWN ONLY)
                # ==========================================
                B_boundary = np.array([])
                target_y = min(y_anchor + self.base_step, H)

                if target_y < H:
                    y_down_end = min(y_anchor + self.max_step, H)
                    # Limit X search zone to the actual calculated right boundary
                    max_local_x = max(R_boundary) if R_boundary.size > 0 else W
                    zone_b = mask[target_y: y_down_end, x_anchor: max_local_x]

                    row_sums = np.sum(zone_b, axis=1)

                    if np.any(row_sums == 0):
                        # Grab the lowest possible boundary
                        local_y = np.where(row_sums == 0)[0][-1]
                        B_boundary = np.full(max_local_x - x_anchor, target_y + local_y)
                    else:
                        seam_b, _ = self.find_topographical_seam(zone_b, 'horizontal')
                        B_boundary = seam_b + target_y
                else:
                    B_boundary = np.full(W - x_anchor, H)

                # ==========================================
                # 3. EXTRACTION, PADDING & SHARED BORDER MEMORY
                # ==========================================
                max_x = max(R_boundary) if R_boundary.size > 0 else W
                max_y = max(B_boundary) if B_boundary.size > 0 else H

                local_mask = np.ones((max_y - y_anchor, max_x - x_anchor), dtype=bool)

                for i, r_val in enumerate(R_boundary):
                    if i < local_mask.shape[0] and r_val - x_anchor < local_mask.shape[1]:
                        local_mask[i, max(0, r_val - x_anchor):] = False

                for j, b_val in enumerate(B_boundary):
                    if j < local_mask.shape[1] and b_val - y_anchor < local_mask.shape[0]:
                        local_mask[max(0, b_val - y_anchor):, j] = False

                available_pixels = ~extracted_mask[y_anchor:max_y, x_anchor:max_x]
                final_tile_mask = local_mask & available_pixels

                if not np.any(final_tile_mask):
                    x_anchor = min(R_boundary) if R_boundary.size > 0 else W
                    continue

                extracted_mask[y_anchor:max_y, x_anchor:max_x] |= final_tile_mask

                # Filtered Tile Extraction
                tile_img = filtered_img[y_anchor:max_y, x_anchor:max_x].copy()
                tile_img[~final_tile_mask] = 0

                # Raw Tile Extraction
                raw_tile_img = raw_img[y_anchor:max_y, x_anchor:max_x].copy()
                raw_tile_img[~final_tile_mask] = 0

                # Target Size Padding (Strictly 1500x1500)
                pad_bottom = max(0, self.target_size - tile_img.shape[0])
                pad_right = max(0, self.target_size - tile_img.shape[1])

                padded_tile = cv2.copyMakeBorder(tile_img, 0, pad_bottom, 0, pad_right, cv2.BORDER_CONSTANT, value=0)
                padded_raw = cv2.copyMakeBorder(raw_tile_img, 0, pad_bottom, 0, pad_right, cv2.BORDER_CONSTANT, value=0)

                save_name = f"{base_name}_tile_{tile_count:04d}.png"
                cv2.imwrite(os.path.join(output_dir, save_name), padded_tile)
                cv2.imwrite(os.path.join(raw_output_dir, save_name), padded_raw)

                # Move anchor up to the tightest calculated border
                x_anchor = min(R_boundary) if R_boundary.size > 0 else W
                if B_boundary.size > 0:
                    bottom_seams.append(min(B_boundary))

            if bottom_seams:
                y_anchor = min(bottom_seams)
            else:
                y_anchor += self.base_step

        print(f"   - Done! Generated {tile_count} perfectly tailored tiles with animated boundaries.")