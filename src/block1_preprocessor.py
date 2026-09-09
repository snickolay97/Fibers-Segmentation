import cv2
import numpy as np
import warnings
from typing import Tuple
from skimage import exposure, util

from src import config

warnings.filterwarnings("ignore")

class GlobalPreprocessor:
    """
    BLOCK 1: Global Preprocessing Node.
    Applies the mathematical morphology and thresholding pipeline to the raw image.
    Uses dual-thresholding: preserves full dynamic range for manual SAM labeling
    while generating an ultra-sensitive obstacle mask for the Smart Slicer.
    """

    @staticmethod
    def to_float(img: np.ndarray) -> np.ndarray:
        """Converts image to float [0.0, 1.0] for accurate skimage calculations."""
        if img.dtype not in [np.float32, np.float64]:
            return util.img_as_float(img)
        return img

    @staticmethod
    def to_uint8(img: np.ndarray) -> np.ndarray:
        """Converts image to 8-bit format for OpenCV compatibility."""
        if img.dtype != np.uint8:
            return util.img_as_ubyte(np.clip(img, 0, 1))
        return img

    def apply_bilateral(self, img: np.ndarray,
                        d: int = config.BILATERAL_D,
                        sigma_color: int = config.BILATERAL_SIGMA_COLOR,
                        sigma_space: int = config.BILATERAL_SIGMA_SPACE) -> np.ndarray:
        """Step 1: Edge-preserving noise reduction."""
        img_u8 = self.to_uint8(img)
        return cv2.bilateralFilter(img_u8, d, sigma_color, sigma_space)

    def apply_tophat(self, img: np.ndarray, radius: int = config.TOPHAT_RADIUS) -> np.ndarray:
        """Step 2: Background subtraction using a massive elliptical kernel."""
        img_u8 = self.to_uint8(img)
        k_size = radius * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
        processed = cv2.morphologyEx(img_u8, cv2.MORPH_TOPHAT, kernel)
        return cv2.normalize(processed, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)

    def apply_gamma(self, img: np.ndarray, gamma: float = config.GAMMA_VALUE) -> np.ndarray:
        """Step 3: Power-law transform to clean residual noise without clipping thin tubes."""
        img_f = self.to_float(img)
        adjusted = exposure.adjust_gamma(img_f, gamma)
        return self.to_uint8(adjusted)

    def process(self, img: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Runs the strict sequential filter pipeline.
        Returns:
        - gamma_img: Contrast-enhanced grayscale image for SAM labeling & feature extraction.
        - binary_mask: High-sensitivity obstacle mask ensuring faint loops & bridges never get cut.
        """
        print("      -> Step 1: Denoise (Bilateral)...")
        denoised = self.apply_bilateral(img)

        print("      -> Step 2: Background Extraction (White Top-Hat)...")
        tophat = self.apply_tophat(denoised)

        print(f"      -> Step 3: Contrast Enhancement (Gamma={config.GAMMA_VALUE})...")
        gamma_img = self.apply_gamma(tophat)

        print("      -> Step 4: Sensitive Obstacle Mask Generation...")
        # Calculate Otsu baseline
        otsu_val, _ = cv2.threshold(gamma_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Relax threshold to capture faint bridges and dim loops
        safety_threshold = max(12, int(otsu_val * config.OTSU_SAFETY_FACTOR))
        _, sensitive_mask = cv2.threshold(gamma_img, safety_threshold, 255, cv2.THRESH_BINARY)

        # Morphological Closing: bridges microscopic gaps across faint cylindrical walls
        close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        obstacle_mask = cv2.morphologyEx(sensitive_mask, cv2.MORPH_CLOSE, close_kernel)

        print(f"         [Otsu Baseline: {otsu_val:.1f} | Safety Threshold: {safety_threshold}]")

        return gamma_img, obstacle_mask