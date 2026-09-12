import os
import json
import cv2
import numpy as np
import imageio
from skimage.graph import MCP_Geometric
from typing import Tuple, Optional, List

from src import config

class SmartSlicer:
    """
    BLOCK 2: Smart Slicer Node.
    Performs dynamic corridor-first backoff and Dijkstra seam finding.
    Supports animated GIF generation of pathfinding searches and optional raw tile export.
    """

    def __init__(self,
                 target_size: int = config.TARGET_SIZE,
                 margin_start: int = config.MARGIN_START,
                 margin_end: int = config.MARGIN_END,
                 enable_animation: bool = config.ENABLE_ANIMATIONS,
                 animation_dir: str = config.ANIMATION_DIR,
                 min_corridor_width: int = config.MIN_CORRIDOR_WIDTH,
                 save_raw_tiles: bool = config.SAVE_RAW_TILES):

        self.base_step = margin_start
        self.max_step = margin_end
        self.target_size = target_size
        self.min_corridor_width = min_corridor_width

        self.dynamic_step = config.DYNAMIC_EXPANSION_STEP
        self.min_margin_limit = config.MIN_MARGIN_LIMIT
        self.obstacle_penalty = config.SEAM_OBSTACLE_PENALTY

        self.enable_animation = enable_animation
        self.animation_dir = animation_dir
        self.save_raw_tiles = save_raw_tiles

        if self.enable_animation:
            os.makedirs(self.animation_dir, exist_ok=True)

    @staticmethod
    def _find_safe_corridor_cut(sums: np.ndarray, min_width: int) -> Optional[int]:
        """Finds widest continuous zero-obstacle corridor."""
        zero_runs = []
        in_run = False
        start_idx = 0

        for i, val in enumerate(sums):
            if val == 0:
                if not in_run:
                    in_run = True
                    start_idx = i
            else:
                if in_run:
                    in_run = False
                    run_len = i - start_idx
                    if run_len >= min_width:
                        zero_runs.append((start_idx, i - 1, run_len))

        if in_run and (len(sums) - start_idx) >= min_width:
            zero_runs.append((start_idx, len(sums) - 1, len(sums) - start_idx))

        if not zero_runs:
            relaxed_width = max(3, min_width // 2)
            for i, val in enumerate(sums):
                if val == 0:
                    if not in_run:
                        in_run = True
                        start_idx = i
                else:
                    if in_run:
                        in_run = False
                        if (i - start_idx) >= relaxed_width:
                            zero_runs.append((start_idx, i - 1, i - start_idx))

        if not zero_runs:
            return None

        best_run = max(zero_runs, key=lambda r: r[2])
        return (best_run[0] + best_run[1]) // 2

    def find_topographical_seam(self, mask_zone: np.ndarray, axis: str) -> Tuple[np.ndarray, float]:
        h, w = mask_zone.shape
        if h == 0 or w == 0:
            return np.array([]), float('inf')

        bg_mask = (mask_zone == 0).astype(np.uint8)
        dist = cv2.distanceTransform(bg_mask, cv2.DIST_L2, 5)

        cost_map = 1.0 / (dist ** config.SEAM_REPULSION_POWER + 1e-3)
        cost_map[mask_zone > 0] = self.obstacle_penalty

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
            default_val = w // 2 if axis == 'vertical' else h // 2
            return np.full(h if axis == 'vertical' else w, default_val), float('inf')

        path = mcp.traceback(best_end)
        seam = np.full(h if axis == 'vertical' else w, -1, dtype=int)
        for py, px in path:
            if axis == 'vertical':
                seam[py] = px
            else:
                seam[px] = py

        limit = len(seam)
        for i in range(1, limit):
            if seam[i] == -1: seam[i] = seam[i - 1]
        for i in range(limit - 2, -1, -1):
            if seam[i] == -1: seam[i] = seam[i + 1]

        return seam, min_cost

    def _create_search_gif(self, mask_block: np.ndarray,
                           scanned_zones: List[Tuple[int, int, str]],
                           straight_seam: Optional[int],
                           dijkstra_seam: Optional[np.ndarray],
                           save_name: str):
        """Generates dynamic pathfinding GIF visualizing straight scans and Dijkstra trajectories."""
        h, w = mask_block.shape
        pad_bottom = max(0, self.target_size - h)
        pad_right = max(0, self.target_size - w)
        padded_mask = cv2.copyMakeBorder(mask_block, 0, pad_bottom, 0, pad_right, cv2.BORDER_CONSTANT, value=0)

        h_pad, w_pad = padded_mask.shape
        base_frame = np.zeros((h_pad, w_pad, 3), dtype=np.uint8)
        base_frame[padded_mask > 0] = [255, 255, 255]
        base_frame[padded_mask == 0] = [35, 20, 20]

        frames = [base_frame.copy(), base_frame.copy()]

        # Animate corridor scanning steps
        for x_start, x_end, zone_type in scanned_zones:
            color = (0, 165, 255) if zone_type == 'forward' else (255, 180, 0)
            step = max(6, (x_end - x_start) // 10) if x_end > x_start else 1

            for col in range(x_start, x_end, step):
                if 0 <= col < w_pad:
                    frame = base_frame.copy()
                    cv2.line(frame, (int(col), 0), (int(col), h_pad), color, 2)
                    frames.append(frame)

        draw_frame = base_frame.copy()

        # Render final established seam
        if straight_seam is not None and 0 <= straight_seam < w_pad:
            cv2.line(draw_frame, (int(straight_seam), 0), (int(straight_seam), h_pad), (0, 255, 0), 3)
            frames.append(draw_frame.copy())
        elif dijkstra_seam is not None and len(dijkstra_seam) > 0:
            pts = [(int(x), int(y)) for y, x in enumerate(dijkstra_seam) if 0 <= x < w_pad and 0 <= y < h_pad]
            if pts:
                chunk_size = max(1, len(pts) // 12)
                for end_idx in range(chunk_size, len(pts) + chunk_size, chunk_size):
                    sub_pts = np.array([pts[:min(end_idx, len(pts))]], dtype=np.int32)
                    frame = base_frame.copy()
                    cv2.polylines(frame, [sub_pts], False, (0, 255, 0), 3)
                    frames.append(frame)
                    draw_frame = frame

        for _ in range(6):
            frames.append(draw_frame.copy())

        os.makedirs(self.animation_dir, exist_ok=True)
        gif_path = os.path.join(self.animation_dir, save_name)
        imageio.mimsave(gif_path, frames, fps=14)

    def _find_x_boundary_with_backoff(self, mask: np.ndarray, x_anchor: int, y_anchor: int,
                                      y_span: int, W: int) -> Tuple[np.ndarray, Optional[int], Optional[np.ndarray], List]:
        search_window = self.max_step - self.base_step
        curr_step = self.base_step
        scanned_zones = []

        # Phase 1: Straight clear corridor scan across backoff window
        while curr_step >= self.min_margin_limit:
            target_x = min(x_anchor + curr_step, W)
            if target_x >= W:
                return np.full(y_span - y_anchor, W), W - x_anchor, None, scanned_zones

            x_right_end = min(x_anchor + curr_step + search_window, W)
            zone_r = mask[y_anchor:y_span, target_x:x_right_end]
            scanned_zones.append((target_x - x_anchor, x_right_end - x_anchor, 'forward'))

            col_sums_r = np.sum(zone_r, axis=0) if zone_r.size > 0 else np.array([1])
            cut_r = self._find_safe_corridor_cut(col_sums_r, self.min_corridor_width)
            if cut_r is not None:
                abs_x = target_x + cut_r
                return np.full(y_span - y_anchor, abs_x), abs_x - x_anchor, None, scanned_zones

            curr_step -= self.dynamic_step

        # Phase 2: Dijkstra routing on primary candidate window
        target_x = min(x_anchor + self.base_step, W)
        x_right_end = min(target_x + search_window, W)
        zone_r = mask[y_anchor:y_span, target_x:x_right_end]

        seam_r, cost_r = self.find_topographical_seam(zone_r, 'vertical')
        if cost_r < self.obstacle_penalty:
            abs_boundary = seam_r + target_x
            return abs_boundary, None, seam_r + (target_x - x_anchor), scanned_zones

        # Fallback to standard base step
        default_x = min(x_anchor + self.base_step, W)
        return np.full(y_span - y_anchor, default_x), default_x - x_anchor, None, scanned_zones

    def _find_y_boundary_with_backoff(self, mask: np.ndarray, x_anchor: int, y_anchor: int,
                                      max_local_x: int, H: int) -> np.ndarray:
        search_window = self.max_step - self.base_step
        curr_step = self.base_step

        while curr_step >= self.min_margin_limit:
            target_y = min(y_anchor + curr_step, H)
            if target_y >= H:
                return np.full(max_local_x - x_anchor, H)

            y_down_end = min(y_anchor + curr_step + search_window, H)
            zone_b = mask[target_y:y_down_end, x_anchor:max_local_x]

            if zone_b.size == 0:
                return np.full(max_local_x - x_anchor, target_y)

            row_sums = np.sum(zone_b, axis=1)
            cut_b = self._find_safe_corridor_cut(row_sums, self.min_corridor_width)
            if cut_b is not None:
                return np.full(max_local_x - x_anchor, target_y + cut_b)

            curr_step -= self.dynamic_step

        # Dijkstra fallback on base window
        target_y = min(y_anchor + self.base_step, H)
        y_down_end = min(target_y + search_window, H)
        zone_b = mask[target_y:y_down_end, x_anchor:max_local_x]

        seam_b, cost_b = self.find_topographical_seam(zone_b, 'horizontal')
        if cost_b < self.obstacle_penalty:
            return seam_b + target_y

        return np.full(max_local_x - x_anchor, min(y_anchor + self.base_step, H))

    def _generate_global_tile_index_map(self, raw_img: np.ndarray, tile_records: List[dict],
                                        output_dir: str, base_name: str):
        overview_dim = config.OVERVIEW_MAP_SIZE
        H, W = raw_img.shape[:2]
        scale = overview_dim / max(H, W)
        new_w, new_h = int(W * scale), int(H * scale)

        print(f"   - Generating High-Resolution Tile Index Map ({new_w}x{new_h} px)...")

        thumb = cv2.resize(raw_img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        overview_bgr = cv2.cvtColor(thumb, cv2.COLOR_GRAY2BGR) if thumb.ndim == 2 else thumb.copy()

        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.rectangle(overview_bgr, (0, 0), (new_w - 1, new_h - 1), (0, 180, 180), 2)

        for rec in tile_records:
            t_id = rec['id']
            x1, y1 = int(rec['x1'] * scale), int(rec['y1'] * scale)
            x2, y2 = min(new_w - 1, int(rec['x2'] * scale)), min(new_h - 1, int(rec['y2'] * scale))

            if 'r_seam' in rec and len(rec['r_seam']) > 1:
                r_pts = (np.array(rec['r_seam'], dtype=np.float32) * scale).astype(np.int32)
                cv2.polylines(overview_bgr, [r_pts], False, (0, 255, 255), 2, cv2.LINE_AA)
            elif x2 < new_w - 2:
                cv2.line(overview_bgr, (x2, y1), (x2, y2), (0, 255, 255), 2)

            if 'b_seam' in rec and len(rec['b_seam']) > 1:
                b_pts = (np.array(rec['b_seam'], dtype=np.float32) * scale).astype(np.int32)
                cv2.polylines(overview_bgr, [b_pts], False, (0, 255, 255), 2, cv2.LINE_AA)
            elif y2 < new_h - 2:
                cv2.line(overview_bgr, (x1, y2), (x2, y2), (0, 255, 255), 2)

            if rec['x1'] == 0:
                cv2.line(overview_bgr, (0, y1), (0, y2), (0, 255, 255), 2)
            if rec['y1'] == 0:
                cv2.line(overview_bgr, (x1, 0), (x2, 0), (0, 255, 255), 2)

            label = f"#{t_id:04d}"
            font_scale = max(0.65, min(1.2, (x2 - x1) / 450.0))
            thickness = max(2, int(font_scale * 2.2))
            (tw, th), baseline = cv2.getTextSize(label, font, font_scale, thickness)
            tx, ty = x1 + 12, y1 + th + 12

            cv2.rectangle(overview_bgr, (tx - 5, ty - th - 5), (tx + tw + 6, ty + baseline + 4), (0, 0, 0), -1)
            cv2.rectangle(overview_bgr, (tx - 5, ty - th - 5), (tx + tw + 6, ty + baseline + 4), (0, 255, 0), 1)
            cv2.putText(overview_bgr, label, (tx, ty), font, font_scale, (0, 255, 0), thickness, cv2.LINE_AA)

        map_path = os.path.join(output_dir, f"{base_name}_TILE_INDEX_MAP_{overview_dim}px.png")
        cv2.imwrite(map_path, overview_bgr)
        print(f"   [OK] High-Resolution Puzzle Map saved to: {map_path}")

    def slice(self, filtered_img: np.ndarray, raw_img: np.ndarray, mask: np.ndarray,
              base_name: str, output_dir: str, raw_output_dir: Optional[str] = None):
        H, W = mask.shape[:2]
        extracted_mask = np.zeros((H, W), dtype=bool)

        y_anchor = 0
        tile_count = 0
        tile_records = []

        overview_dir = os.path.join(output_dir, 'overview')
        os.makedirs(overview_dir, exist_ok=True)

        print(f"   - Slicing {W}x{H} image with Dynamic Back-Off (Save Raw Tiles: {self.save_raw_tiles}, Animations: {self.enable_animation})...")

        while y_anchor < H:
            x_anchor = 0
            bottom_seams = []

            while x_anchor < W:
                tile_count += 1
                y_span = min(y_anchor + self.target_size, H)
                x_span = min(x_anchor + self.target_size, W)

                R_boundary, straight_seam, dijkstra_seam, scanned_zones = self._find_x_boundary_with_backoff(
                    mask, x_anchor, y_anchor, y_span, W
                )

                # Generate animated GIF visualization if enabled
                if self.enable_animation:
                    anim_block = mask[y_anchor:y_span, x_anchor:x_span]
                    if anim_block.size > 0:
                        gif_name = f"{base_name}_{tile_count:04d}_X_Cut.gif"
                        self._create_search_gif(
                            mask_block=anim_block,
                            scanned_zones=scanned_zones,
                            straight_seam=straight_seam,
                            dijkstra_seam=dijkstra_seam,
                            save_name=gif_name
                        )

                max_local_x = max(R_boundary) if R_boundary.size > 0 else W
                B_boundary = self._find_y_boundary_with_backoff(
                    mask, x_anchor, y_anchor, max_local_x, H
                )

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

                tile_img = filtered_img[y_anchor:max_y, x_anchor:max_x].copy()
                tile_img[~final_tile_mask] = 0

                pad_bottom = max(0, self.target_size - tile_img.shape[0])
                pad_right = max(0, self.target_size - tile_img.shape[1])
                padded_tile = cv2.copyMakeBorder(tile_img, 0, pad_bottom, 0, pad_right, cv2.BORDER_CONSTANT, value=0)

                save_name = f"{base_name}_tile_{tile_count:04d}.png"
                cv2.imwrite(os.path.join(output_dir, save_name), padded_tile)

                # Conditionally save raw tile only if toggle is True
                if self.save_raw_tiles and raw_output_dir is not None:
                    raw_tile_img = raw_img[y_anchor:max_y, x_anchor:max_x].copy()
                    raw_tile_img[~final_tile_mask] = 0
                    padded_raw = cv2.copyMakeBorder(raw_tile_img, 0, pad_bottom, 0, pad_right, cv2.BORDER_CONSTANT, value=0)
                    cv2.imwrite(os.path.join(raw_output_dir, save_name), padded_raw)

                step = 15
                r_seam_pts = [
                    [int(r_val), int(y_anchor + idx)]
                    for idx, r_val in enumerate(R_boundary)
                    if idx % step == 0 or idx == len(R_boundary) - 1
                ]
                b_seam_pts = [
                    [int(x_anchor + jdx), int(b_val)]
                    for jdx, b_val in enumerate(B_boundary)
                    if jdx % step == 0 or jdx == len(B_boundary) - 1
                ]

                tile_records.append({
                    'id': tile_count,
                    'x1': int(x_anchor),
                    'y1': int(y_anchor),
                    'x2': int(max_x),
                    'y2': int(max_y),
                    'r_seam': r_seam_pts,
                    'b_seam': b_seam_pts
                })

                x_anchor = min(R_boundary) if R_boundary.size > 0 else W
                if B_boundary.size > 0:
                    bottom_seams.append(min(B_boundary))

            y_anchor = min(bottom_seams) if bottom_seams else y_anchor + self.base_step

        coords_path = os.path.join(overview_dir, f"{base_name}_tiles_coords.json")
        try:
            with open(coords_path, 'w', encoding='utf-8') as f:
                json.dump(tile_records, f, indent=2)
            print(f"   [OK] Coordinates Manifest saved to: {coords_path}")
        except Exception as e:
            print(f"   [!] Error saving JSON: {e}")

        self._generate_global_tile_index_map(raw_img, tile_records, overview_dir, base_name)
        print(f"   - Finished! Generated {tile_count} tailored tiles with zero object cuts.")
