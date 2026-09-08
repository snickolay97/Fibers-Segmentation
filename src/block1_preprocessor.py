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
        """Step 3: Power-law transform to suppress dark artifacts and boost bright fibers."""
        img_f = self.to_float(img)
        adjusted = exposure.adjust_gamma(img_f, gamma)
        return self.to_uint8(adjusted)

    def process(self, img: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Runs the strict sequential filter pipeline. Returns both the filtered image and binary mask."""
        print("      -> Step 1: Denoise (Bilateral)...")
        denoised = self.apply_bilateral(img)

        print("      -> Step 2: Background Extraction (White Top-Hat)...")
        tophat = self.apply_tophat(denoised)

        print("      -> Step 3: Contrast Enhancement (Gamma)...")
        gamma_img = self.apply_gamma(tophat)

        print("      -> Step 4: Global Binarization...")
        _, binary_mask = cv2.threshold(gamma_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Возвращаем КОРТЕЖ (Отфильтрованная картинка, Бинарная маска)
        return gamma_img, binary_mask