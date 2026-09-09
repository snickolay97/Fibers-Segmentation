"""
Diagnostic Script: Faint Fiber & Loop Detection Evaluation
---------------------------------------------------------
Loads a crop from the raw microscope data, runs Block 1 preprocessing,
and visually contrasts:
1. Standard Otsu (Current behavior: loses loops and faint bridges)
2. Relaxed Safety Threshold (Captures dim loops and thin connections)
3. Morphologically Closed Safety Mask (Guarantees no gaps for Smart Slicer)

Outputs are saved to 'data/faint_fiber_evaluation/'.
"""

import os
import sys
import glob
import cv2
import numpy as np
import tifffile
from skimage import util

# Dynamically resolve project root regardless of where script is launched
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..')) if os.path.basename(CURRENT_DIR) in ['test', 'tests'] else CURRENT_DIR

# Ensure project root is in sys.path and set it as active working directory
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from src import config
from src.block1_preprocessor import GlobalPreprocessor


def evaluate_faint_fiber_detection(crop_size: int = 2048):
    output_dir = os.path.join(PROJECT_ROOT, 'data', 'faint_fiber_evaluation')
    os.makedirs(output_dir, exist_ok=True)

    # Resolve absolute path to input directory
    input_dir = os.path.join(PROJECT_ROOT, config.INPUT_DIR)

    # Search for both .tif and .tiff (case-insensitive)
    tif_files = glob.glob(os.path.join(input_dir, '*.tif')) + \
                glob.glob(os.path.join(input_dir, '*.tiff')) + \
                glob.glob(os.path.join(input_dir, '*.TIF'))

    if not tif_files:
        print(f"[!] No .tif images found in '{input_dir}'.")
        print(f"    Current Active Working Directory: {os.getcwd()}")
        return

    target_path = tif_files[0]
    base_name = os.path.splitext(os.path.basename(target_path))[0]
    print(f"---> Diagnosing Threshold Sensitivity on: {base_name}")
    print(f"     Image Source: {target_path}")

    raw_full = tifffile.imread(target_path)
    if len(raw_full.shape) == 3:
        raw_full = raw_full[:, :, 0]

    if raw_full.dtype == np.uint16:
        raw_full = (raw_full / 256).astype(np.uint8)
    elif raw_full.dtype != np.uint8:
        raw_full = util.img_as_ubyte(np.clip(raw_full, 0, 1))

    H, W = raw_full.shape[:2]
    cy, cx = H // 2, W // 2
    half = crop_size // 2
    raw_crop = raw_full[max(0, cy - half):min(H, cy + half), max(0, cx - half):min(W, cx + half)].copy()

    preprocessor = GlobalPreprocessor()

    # Step 1: Bilateral
    denoised = preprocessor.apply_bilateral(raw_crop)

    # Step 2: Top-Hat
    tophat = preprocessor.apply_tophat(denoised)

    # Step 3: Contrast Enhancement
    gamma_img = preprocessor.apply_gamma(tophat)

    # 1. Standard Global Otsu (Loses faint bridges)
    otsu_val, mask_standard_otsu = cv2.threshold(gamma_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 2. Relaxed Safety Threshold (Preserves dim fibers and loops)
    safety_threshold = max(12, int(otsu_val * config.OTSU_SAFETY_FACTOR))
    _, mask_relaxed = cv2.threshold(gamma_img, safety_threshold, 255, cv2.THRESH_BINARY)

    # 3. Morphological Closing (Bridges tiny gaps between fluorescent nodes)
    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask_closed = cv2.morphologyEx(mask_relaxed, cv2.MORPH_CLOSE, close_kernel)

    print(f"     [+] Standard Otsu Threshold: {otsu_val:.1f}")
    print(f"     [+] Relaxed Safety Threshold (Factor={config.OTSU_SAFETY_FACTOR}): {safety_threshold}")

    cv2.imwrite(os.path.join(output_dir, f"{base_name}_01_gamma_enhanced.png"), gamma_img)
    cv2.imwrite(os.path.join(output_dir, f"{base_name}_02_mask_standard_otsu.png"), mask_standard_otsu)
    cv2.imwrite(os.path.join(output_dir, f"{base_name}_03_mask_relaxed_safety.png"), mask_relaxed)
    cv2.imwrite(os.path.join(output_dir, f"{base_name}_04_mask_closed_final.png"), mask_closed)

    # Side-by-side diagnostic visualizer
    thumb_size = 800
    r_gray = cv2.resize(gamma_img, (thumb_size, thumb_size))
    r_otsu = cv2.resize(mask_standard_otsu, (thumb_size, thumb_size))
    r_relax = cv2.resize(mask_relaxed, (thumb_size, thumb_size))
    r_close = cv2.resize(mask_closed, (thumb_size, thumb_size))

    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(r_gray, "1. Filtered Grayscale", (20, 45), font, 1.0, 255, 2)
    cv2.putText(r_otsu, f"2. Standard Otsu (T={int(otsu_val)}) [BROKEN]", (20, 45), font, 0.9, 255, 2)
    cv2.putText(r_relax, f"3. Relaxed Safety (T={safety_threshold})", (20, 45), font, 1.0, 255, 2)
    cv2.putText(r_close, "4. Closed Safety Mask [SAFE FOR SLICING]", (20, 45), font, 0.85, 255, 2)

    top_row = np.hstack([r_gray, r_otsu])
    bot_row = np.hstack([r_relax, r_close])
    grid = np.vstack([top_row, bot_row])

    cv2.imwrite(os.path.join(output_dir, f"{base_name}_comparison_grid.png"), grid)
    print(f"[SUCCESS] Diagnostic files generated in '{output_dir}'. Check 'comparison_grid.png'!")


if __name__ == "__main__":
    evaluate_faint_fiber_detection(crop_size=2048)