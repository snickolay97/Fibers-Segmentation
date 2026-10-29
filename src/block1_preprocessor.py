import cv2
import numpy as np
from typing import Tuple

from src.app_settings import PipelineSettings, PipelineCancelled

class GlobalPreprocessor:
    """
    BLOCK 1: Global Preprocessing Node.
    Produces:
    1. filtered_img: Grayscale image after the enabled processing steps.
    2. obstacle_mask: Thresholded protective mask with optional closing/dilation.

    Individual apply_* helpers always perform their named operation. ``process``
    selects steps using the run settings, keeping the historical order.
    """

    def __init__(self, settings=None, progress=None, cancelled=None):
        self.settings = (settings or PipelineSettings()).validate()
        self.progress = progress
        self.cancelled = cancelled

    def _checkpoint(self, message=None, current=None, status='running', operation=None):
        if self.cancelled and self.cancelled():
            raise PipelineCancelled('Operation cancelled')
        if message and self.progress:
            self.progress(dict(stage='filter', status=status, message=message,
                               operation=operation, current=current, total=6))

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
            self.settings.bilateral_d,
            self.settings.bilateral_sigma_color,
            self.settings.bilateral_sigma_space
        )

    def apply_tophat(self, img_u8: np.ndarray) -> np.ndarray:
        k_size = self.settings.tophat_radius * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
        processed = cv2.morphologyEx(img_u8, cv2.MORPH_TOPHAT, kernel)
        return cv2.normalize(processed, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)

    def apply_gamma(self, img_u8: np.ndarray) -> np.ndarray:
        inv_gamma = 1.0 / self.settings.gamma
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype(np.uint8)
        return cv2.LUT(img_u8, table)

    def process(self, img_u8: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        if img_u8.ndim != 2 or img_u8.dtype != np.uint8 or not img_u8.size:
            raise ValueError('Preprocessing requires a nonempty 2D uint8 image')
        filtered_img = img_u8
        grayscale_steps = (
            ('bilateral', self.settings.enable_bilateral, self.apply_bilateral, 'Denoising', 'Skipping bilateral filter'),
            ('tophat', self.settings.enable_tophat, self.apply_tophat, 'Subtracting background', 'Skipping white top-hat'),
            ('gamma', self.settings.enable_gamma, self.apply_gamma, 'Enhancing contrast', 'Skipping gamma correction'),
        )
        for index, (operation, enabled, apply, message, skipped_message) in enumerate(grayscale_steps):
            if enabled:
                self._checkpoint(message, index, operation=operation)
                print('      -> Step {}: {}...'.format(index+1, message))
                filtered_img = apply(filtered_img)
            else:
                self._checkpoint(skipped_message, index+1, status='skipped', operation=operation)
                print('      -> Step {}: {}.'.format(index+1, skipped_message))

        self._checkpoint('Building protective mask', 3, operation='otsu')
        print("      -> Step 4: Protective Mask Thresholding...")
        otsu_val = self._compute_fast_otsu(filtered_img)
        safety_threshold = max(10, int(otsu_val * self.settings.otsu_safety_factor))

        _, raw_binary = cv2.threshold(filtered_img, safety_threshold, 255, cv2.THRESH_BINARY)

        if self.settings.enable_closing:
            self._checkpoint('Closing protective gaps', 4, operation='closing')
            print('      -> Step 5: Closing protective gaps...')
            bridge_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (self.settings.bridge_kernel_size, self.settings.bridge_kernel_size))
            closed_mask = cv2.morphologyEx(raw_binary, cv2.MORPH_CLOSE, bridge_kernel)
        else:
            self._checkpoint('Skipping protective closing', 5, status='skipped', operation='closing')
            print('      -> Step 5: Skipping protective closing.')
            closed_mask = raw_binary

        if self.settings.enable_dilation:
            self._checkpoint('Adding protective buffer', 5, operation='dilation')
            print('      -> Step 6: Adding protective buffer...')
            buffer_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (self.settings.buffer_kernel_size, self.settings.buffer_kernel_size))
            obstacle_mask = cv2.dilate(closed_mask, buffer_kernel, iterations=1)
        else:
            self._checkpoint('Skipping protective dilation', 6, status='skipped', operation='dilation')
            print('      -> Step 6: Skipping protective dilation.')
            obstacle_mask = closed_mask

        print(f"         [Otsu Baseline: {otsu_val:.1f} | Safety Threshold: {safety_threshold}]")
        self._checkpoint('Filtering complete', 6, status='completed')
        return filtered_img, obstacle_mask
