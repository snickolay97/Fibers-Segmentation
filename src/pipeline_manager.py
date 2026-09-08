import os
import glob
import numpy as np
import tifffile

from src import config
from src.block1_preprocessor import GlobalPreprocessor
from src.block2_slicer import SmartSlicer
from src.block3_feature_extractor import TopologicalFeatureExtractor


class BiomedicalPipelineManager:
    """
    Orchestrator class managing execution flows (DAG Node Manager).
    Connects the independent logical nodes dynamically.
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

        # Initialize Blocks 1 & 2
        self.preprocessor = GlobalPreprocessor()
        self.slicer = SmartSlicer(target_size=config.TARGET_SIZE,
                                  margin_start=config.MARGIN_START,
                                  margin_end=config.MARGIN_END)
        # Блок 3 инициализируется динамически в методе _execute_extract_features

    def run(self, mode: str = 'filter_and_slice'):
        """Управление режимами работы Оркестратора"""
        if mode == 'filter_and_slice':
            self._execute_filter_and_slice()
        elif mode == 'extract_features':
            self._execute_extract_features()
        elif mode == 'end_to_end':
            self._execute_filter_and_slice()
            self._execute_extract_features()
        else:
            print(f"Mode '{mode}' not recognized.")

    def _execute_filter_and_slice(self):
        if not os.path.exists(self.input_dir):
            os.makedirs(self.input_dir)
            print(f"Created input directory '{self.input_dir}'. Please add your .tif files and run again.")
            return

        image_files = glob.glob(os.path.join(self.input_dir, '*.tif'))
        if not image_files:
            print(f"No .tif images found in '{self.input_dir}'. Exiting.")
            return

        print(f"Found {len(image_files)} massive .tif images. Initializing Topographical Tiling...")

        for img_path in image_files:
            base_name = os.path.splitext(os.path.basename(img_path))[0]
            print(f"\n---> [Processing] {base_name}")

            image_out_dir = os.path.join(self.output_dir, base_name)
            raw_image_out_dir = os.path.join(self.raw_output_dir, base_name)
            os.makedirs(image_out_dir, exist_ok=True)
            os.makedirs(raw_image_out_dir, exist_ok=True)

            try:
                img = tifffile.imread(img_path)
                if len(img.shape) == 3:
                    img = img[:, :, 0]  # Force grayscale

                if img.dtype == np.uint16:
                    img = (img / 256).astype(np.uint8)

            except Exception as e:
                print(f"Error loading {img_path}: {e}")
                continue

            print(f"   - Resolution loaded: {img.shape[1]}x{img.shape[0]} px")

            filtered_img, global_mask = self.preprocessor.process(img)
            self.slicer.slice(filtered_img, img, global_mask, base_name, image_out_dir, raw_image_out_dir)

        print("\n[SUCCESS] Smart Slicing Node Pipeline Finished!")

    def _execute_extract_features(self):
        """
        Ищет папки с нарезанными тайлами и для каждой большой картинки
        запускает Блок 3, чтобы результаты сохранялись в отдельные папки.
        """
        if not os.path.exists(self.output_dir):
            print(f"No sliced tiles found in '{self.output_dir}'. Run 'filter_and_slice' first.")
            return

        # Находим все подпапки (например: 2_sliced_tiles/FL01_G3_RGB_Red)
        large_image_folders = [f.path for f in os.scandir(self.output_dir) if f.is_dir()]

        if not large_image_folders:
            print(f"No tile folders found inside '{self.output_dir}'.")
            return

        print(f"Found {len(large_image_folders)} processed large image sets. Starting Topology Extraction...")

        for tile_dir in large_image_folders:
            base_name = os.path.basename(tile_dir)
            print(f"\n---> [Extracting Features] {base_name}")

            # Динамически создаем путь для сохранения результатов ЭТОЙ картинки
            # Например: data/4_final_results/FL01_G3_RGB_Red/
            specific_output_dir = os.path.join(self.features_dir, base_name)

            # Инициализируем Блок 3 строго для этой папки
            extractor = TopologicalFeatureExtractor(
                image_dir=tile_dir,
                labels_dir=self.labels_dir,
                output_dir=specific_output_dir,
                large_image_name=base_name  # Передаем имя для красивого названия Excel файла
            )

            extractor.execute()

        print("\n[SUCCESS] Feature Extraction Pipeline Finished!")