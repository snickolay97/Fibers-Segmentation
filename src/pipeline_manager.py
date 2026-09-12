import os
import glob
import numpy as np
import tifffile

from src import config
from src.block1_preprocessor import GlobalPreprocessor
from src.block2_slicer import SmartSlicer
from src.block3_feature_extractor import TopologicalFeatureExtractor
from src.tile_manager import TileManager

class BiomedicalPipelineManager:
    """
    Core DAG Orchestrator. Coordinates image loading, preprocessing,
    slicing with Dijkstra and animations, and topological feature extraction.
    """

    def __init__(self,
                 input_dir: str = config.INPUT_DIR,
                 output_dir: str = config.OUTPUT_DIR,
                 raw_output_dir: str = config.RAW_OUTPUT_DIR,
                 labels_dir: str = config.LABELS_DIR,
                 features_dir: str = config.FEATURES_DIR):

        self.input_dir = input_dir
        self.output_dir = output_dir
        self.raw_output_dir = raw_output_dir
        self.labels_dir = labels_dir
        self.features_dir = features_dir

        self.preprocessor = GlobalPreprocessor()
        self.slicer = SmartSlicer(
            target_size=config.TARGET_SIZE,
            margin_start=config.MARGIN_START,
            margin_end=config.MARGIN_END,
            enable_animation=config.ENABLE_ANIMATIONS,
            animation_dir=config.ANIMATION_DIR,
            min_corridor_width=config.MIN_CORRIDOR_WIDTH,
            save_raw_tiles=config.SAVE_RAW_TILES
        )
        self.tile_manager = TileManager()

    def run(self, mode: str = 'filter_and_slice', **kwargs):
        if mode == 'filter_and_slice':
            self._execute_filter_and_slice()
        elif mode == 'manage_tiles':
            dataset = kwargs.get('dataset_name', 'FL01_G3_RGB_Red')
            specs = kwargs.get('exclude_specs', [])
            self.tile_manager.exclude(dataset_name=dataset, tile_specs=specs)
        elif mode == 'extract_features':
            self._execute_extract_features()
        elif mode == 'end_to_end':
            self._execute_filter_and_slice()
            self._execute_extract_features()
        else:
            print(f"[!] Unknown mode '{mode}'. Available: 'filter_and_slice', 'manage_tiles', 'extract_features', 'end_to_end'.")

    def _execute_filter_and_slice(self):
        if not os.path.exists(self.input_dir):
            os.makedirs(self.input_dir, exist_ok=True)
            print(f"Created input directory '{self.input_dir}'. Please place .tif images there.")
            return

        image_files = glob.glob(os.path.join(self.input_dir, '*.tif*'))
        if not image_files:
            print(f"No .tif images found in '{self.input_dir}'.")
            return

        print(f"Found {len(image_files)} large TIFF images. Initializing pipeline...")

        for img_path in image_files:
            base_name = os.path.splitext(os.path.basename(img_path))[0]
            print(f"\n---> [Processing Image] {base_name}")

            image_out_dir = os.path.join(self.output_dir, base_name)
            os.makedirs(image_out_dir, exist_ok=True)

            raw_image_out_dir = None
            if config.SAVE_RAW_TILES:
                raw_image_out_dir = os.path.join(self.raw_output_dir, base_name)
                os.makedirs(raw_image_out_dir, exist_ok=True)

            try:
                img = tifffile.imread(img_path)
                if img.ndim == 3:
                    img = img[:, :, 0]  # Force single channel

                # Fast zero-copy 16-bit to 8-bit normalization
                if img.dtype == np.uint16:
                    img = (img >> 8).astype(np.uint8)
                elif img.dtype != np.uint8:
                    img = np.clip(img, 0, 255).astype(np.uint8)

            except Exception as e:
                print(f"[!] Error loading {img_path}: {e}")
                continue

            print(f"   - Loaded resolution: {img.shape[1]}x{img.shape[0]} px | Type: {img.dtype}")

            filtered_img, obstacle_mask = self.preprocessor.process(img)
            self.slicer.slice(
                filtered_img=filtered_img,
                raw_img=img,
                mask=obstacle_mask,
                base_name=base_name,
                output_dir=image_out_dir,
                raw_output_dir=raw_image_out_dir
            )

        print("\n[SUCCESS] Slicing and Overview Mapping Finished!")

    def _execute_extract_features(self):
        if not os.path.exists(self.output_dir):
            print(f"[!] Sliced tiles directory not found: '{self.output_dir}'. Run 'filter_and_slice' first.")
            return

        large_image_folders = [f.path for f in os.scandir(self.output_dir) if f.is_dir()]
        if not large_image_folders:
            print(f"[!] No tile folders found inside '{self.output_dir}'.")
            return

        print(f"Found {len(large_image_folders)} dataset folders. Starting feature extraction...")

        for tile_dir in large_image_folders:
            base_name = os.path.basename(tile_dir)
            print(f"\n---> [Extracting Features] {base_name}")

            specific_output_dir = os.path.join(self.features_dir, base_name)
            extractor = TopologicalFeatureExtractor(
                image_dir=tile_dir,
                labels_dir=self.labels_dir,
                output_dir=specific_output_dir,
                large_image_name=base_name
            )
            extractor.execute()

        print("\n[SUCCESS] Feature Extraction Finished!")
