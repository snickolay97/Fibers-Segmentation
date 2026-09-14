import cv2
import numpy as np
import warnings
from typing import Tuple

from src import config

warnings.filterwarnings("ignore")

class GlobalPreprocessor:
    """
    BLOCK 1: Global Preprocessing Node.
    Produces:
    1. gamma_img: Contrast-enhanced grayscale image for SAM and feature extraction.
    2. obstacle_mask: Fortified binary barrier map with bridged gaps and safety buffers.
    """

    @staticmethod
    def _compute_fast_otsu(img_u8: np.ndarray) -> float:
        """Computes Otsu threshold in <1ms via 256-bin histogram, avoiding giant array allocations."""
        hist = cv2.calcHist([img_u8], [0], None, [256], [0, 256]).ravel()
        hist[0] = 0  # Ignore background zeros
        total = hist.sum()
        if total < 50:
            return 40.0

        current_max, threshold = 0.0, 40.0
        weight_bg, sum_bg = 0.0, 0.0
        sum_total = np.dot(np.arange(256), hist)

        for t in range(256):
            weight_bg += hist[t]
            if weight_bg == 0:
                continue
            weight_fg = total - weight_bg
            if weight_fg == 0:
                break
            sum_bg += t * hist[t]
            mean_bg = sum_bg / weight_bg
            mean_fg = (sum_total - sum_bg) / weight_fg
            var_between = weight_bg * weight_fg * ((mean_bg - mean_fg) ** 2)
            if var_between > current_max:
                current_max = var_between
                threshold = float(t)

        return threshold

    def apply_bilateral(self, img_u8: np.ndarray) -> np.ndarray:
        return cv2.bilateralFilter(
            img_u8,
            config.BILATERAL_D,
            config.BILATERAL_SIGMA_COLOR,
            config.BILATERAL_SIGMA_SPACE
        )

    def apply_tophat(self, img_u8: np.ndarray) -> np.ndarray:
        k_size = config.TOPHAT_RADIUS * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
        processed = cv2.morphologyEx(img_u8, cv2.MORPH_TOPHAT, kernel)
        return cv2.normalize(processed, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)

    def apply_gamma(self, img_u8: np.ndarray) -> np.ndarray:
        inv_gamma = 1.0 / config.GAMMA_VALUE
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype(np.uint8)
        return cv2.LUT(img_u8, table)

    def process(self, img_u8: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        print("      -> Step 1: Denoise (Bilateral Filter)...")
        denoised = self.apply_bilateral(img_u8)

        print("      -> Step 2: Background Extraction (White Top-Hat)...")
        tophat = self.apply_tophat(denoised)

        print(f"      -> Step 3: Contrast Enhancement (Gamma LUT={config.GAMMA_VALUE})...")
        gamma_img = self.apply_gamma(tophat)

        print("      -> Step 4: Fortified Obstacle Mask Generation...")
        otsu_val = self._compute_fast_otsu(gamma_img)
        safety_threshold = max(10, int(otsu_val * config.OTSU_SAFETY_FACTOR))

        _, raw_binary = cv2.threshold(gamma_img, safety_threshold, 255, cv2.THRESH_BINARY)

        # Bridge gaps between neighboring beads (17x17 ellipse)
        bridge_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (config.BRIDGE_KERNEL_SIZE, config.BRIDGE_KERNEL_SIZE))
        closed_mask = cv2.morphologyEx(raw_binary, cv2.MORPH_CLOSE, bridge_kernel)

        # Safety buffer around fibers (5x5 ellipse)
        buffer_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (config.BUFFER_KERNEL_SIZE, config.BUFFER_KERNEL_SIZE))
        obstacle_mask = cv2.dilate(closed_mask, buffer_kernel, iterations=1)

        print(f"         [Otsu Baseline: {otsu_val:.1f} | Safety Threshold: {safety_threshold}]")
        return gamma_img, obstacle_mask