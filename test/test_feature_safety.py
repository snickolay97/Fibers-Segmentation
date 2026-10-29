import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pandas as pd

from src.app_settings import PipelineCancelled
from src.block3_feature_extractor import TopologicalFeatureExtractor, inspect_labels
from src.overview_reconstructor import HighResOverviewReconstructor
from src.partition_geometry import validate_dataset
from src.tile_manager import TileManager
from src.tile_scale import fixed_canvas, scale_metadata


class FeatureSafetyTests(unittest.TestCase):
    def make_dataset(self, root):
        dataset, labels, output = root/'tiles'/'sample', root/'labels', root/'results'
        for path in (dataset/'native', dataset/'valid_masks', dataset/'overview', labels):
            path.mkdir(parents=True, exist_ok=True)
        native = np.zeros((64,64), np.uint8)
        native[20:44,20:44] = 100
        transform = scale_metadata(64,64,32)
        record = dict(id=1, x1=0, y1=0, x2=64, y2=64,
                      filename='sample_tile_0001.png', native_filename='native/native_0001.png',
                      valid_mask='valid_masks/valid_0001.png', valid_pixels=4096,
                      transform=transform, canvas_shape=[32,32])
        cv2.imwrite(str(dataset/record['native_filename']), native)
        cv2.imwrite(str(dataset/record['filename']), fixed_canvas(native, transform))
        cv2.imwrite(str(dataset/record['valid_mask']), np.full((64,64),255,np.uint8))
        manifest = dict(schema_version=3, source_name='sample', image_shape=[64,64], tiles=[record])
        (dataset/'overview/sample_tiles_coords.json').write_text(json.dumps(manifest))
        label = labels/'sample_tile_0001.txt'
        label.write_text('0 0.25 0.25 0.75 0.25 0.75 0.75 0.25 0.75\n')
        return dataset, labels, output, manifest

    def extractor(self, dataset, labels, output, **options):
        return TopologicalFeatureExtractor(str(dataset), str(labels), str(output), 'sample', **options)

    def test_minimum_area_handles_zero_one_and_many_components(self):
        extractor = TopologicalFeatureExtractor('.', '.', '.')
        for mode, expected_areas in [('empty', []), ('tiny', []), ('one', [40]), ('two', [40,40])]:
            mask = np.zeros((30,30),np.uint8)
            if mode != 'empty': mask[1:2,1:4]=255
            if mode in ('one','two'): mask[4:9,4:12]=255
            if mode == 'two': mask[16:21,16:24]=255
            pieces = extractor._decompose_sub_objects(mask, mask, min_area=30)
            self.assertEqual(sorted(int(np.count_nonzero(piece[0])) for piece in pieces), expected_areas)

    def test_scaled_native_features_and_physical_area(self):
        with tempfile.TemporaryDirectory() as work:
            dataset, labels, output, _ = self.make_dataset(Path(work))
            settings = SimpleNamespace(pixel_size_um=.4)
            result = self.extractor(dataset, labels, output, settings=settings, allow_legacy=False).execute()
            row = pd.read_csv(result['csv_path']).iloc[0]
            self.assertEqual(result['objects'], 1)
            self.assertEqual(row['Area'], 576)
            self.assertAlmostEqual(row['Area_um2'], 92.16)
            self.assertEqual(row['Aspect_Ratio'], 1)
            self.assertEqual(row['Source_Pixels_Per_Output_Pixel'], 2)
            self.assertEqual(row['Measurement_Space'], 'source_pixels')

    def test_empty_rerun_clears_stale_csv_and_verification_masks(self):
        with tempfile.TemporaryDirectory() as work:
            dataset, labels, output, _ = self.make_dataset(Path(work))
            first = self.extractor(dataset, labels, output).execute()
            self.assertEqual(first['objects'], 1)
            self.assertEqual(len(list((output/'verification_masks').rglob('*.png'))),1)
            (labels/'sample_tile_0001.txt').write_text('')
            second = self.extractor(dataset, labels, output, labels_mode='require_annotations').execute()
            self.assertEqual(second['objects'], 0)
            self.assertEqual(len(pd.read_csv(second['csv_path'])),0)
            self.assertEqual(list((output/'verification_masks').rglob('*')),[])

    def test_annotations_only_skips_missing_and_require_rejects(self):
        with tempfile.TemporaryDirectory() as work:
            dataset, labels, output, _ = self.make_dataset(Path(work))
            (labels/'sample_tile_0001.txt').unlink()
            result = self.extractor(dataset, labels, output, labels_mode='annotations_only').execute()
            self.assertEqual(result['skipped_unlabeled'],1)
            self.assertEqual(result['objects'],0)
            with self.assertRaises(ValueError):
                self.extractor(dataset, labels, output, labels_mode='require_annotations').execute()

    def test_malformed_annotations_do_not_replace_previous_results(self):
        with tempfile.TemporaryDirectory() as work:
            dataset, labels, output, _ = self.make_dataset(Path(work))
            result = self.extractor(dataset, labels, output).execute()
            previous = Path(result['csv_path']).read_bytes()
            mask_files = list((output/'verification_masks').rglob('*.png'))
            mask_bytes = [p.read_bytes() for p in mask_files]
            for content in ('0 nan .2 .3 .2 .3 .4', '0 1.1 .2 .3 .2 .3 .4',
                            '7 .1 .2 .3 .2 .3 .4', '0 .1 .2 .3 .4'):
                (labels/'sample_tile_0001.txt').write_text(content)
                with self.assertRaises(ValueError):
                    self.extractor(dataset, labels, output).execute()
                self.assertEqual(Path(result['csv_path']).read_bytes(),previous)
                self.assertEqual([p.read_bytes() for p in mask_files],mask_bytes)

    def test_cancel_before_publish_preserves_previous_results(self):
        with tempfile.TemporaryDirectory() as work:
            dataset, labels, output, _ = self.make_dataset(Path(work))
            result = self.extractor(dataset, labels, output).execute()
            previous = Path(result['csv_path']).read_bytes()
            (labels/'sample_tile_0001.txt').write_text('')
            stop = [False]
            def progress(event): stop[0] = True
            with self.assertRaises(PipelineCancelled):
                self.extractor(dataset, labels, output, progress=progress, cancelled=lambda:stop[0]).execute()
            self.assertEqual(Path(result['csv_path']).read_bytes(), previous)
            self.assertEqual(len(list((output/'verification_masks').rglob('*.png'))),1)
            self.assertEqual(list(output.glob('.features_*')),[])

    def test_missing_manifest_native_dataset_is_never_legacy(self):
        with tempfile.TemporaryDirectory() as work:
            dataset, labels, output, _ = self.make_dataset(Path(work))
            (dataset/'overview/sample_tiles_coords.json').unlink()
            with self.assertRaises(ValueError):self.extractor(dataset, labels, output).execute()

    def test_dataset_validation_checks_excluded_and_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as work:
            dataset, labels, output, manifest = self.make_dataset(Path(work))
            self.assertEqual(validate_dataset(dataset, check_pixels=True)['image_shape'], [64,64])
            (dataset/'excluded_tiles').mkdir()
            (dataset/'sample_tile_0001.png').rename(dataset/'excluded_tiles/sample_tile_0001.png')
            validate_dataset(dataset, check_pixels=True)
            manifest['tiles'][0]['native_filename'] = '../../outside.png'
            with self.assertRaises(ValueError):validate_dataset(dataset,manifest)

    def test_custom_paths_exclude_restore_preserves_native_and_masks(self):
        with tempfile.TemporaryDirectory() as work:
            dataset, labels, output, _ = self.make_dataset(Path(work))
            manager = TileManager(output_dir=dataset.parent)
            native = (dataset/'native/native_0001.png').read_bytes()
            valid = (dataset/'valid_masks/valid_0001.png').read_bytes()
            self.assertEqual(manager.exclude('sample','1'),1)
            self.assertEqual(manager.list_excluded('sample'),[1])
            self.assertEqual(manager.restore('sample',[1]),1)
            self.assertEqual(manager.list_excluded('sample'),[])
            self.assertEqual((dataset/'native/native_0001.png').read_bytes(),native)
            self.assertEqual((dataset/'valid_masks/valid_0001.png').read_bytes(),valid)
            with self.assertRaises(ValueError):manager.exclude('../other',[1])
            (dataset/'excluded_tiles/sample_tile_0001.png').write_bytes((dataset/'sample_tile_0001.png').read_bytes())
            with self.assertRaises(FileExistsError):manager.exclude('sample',[1])
            self.assertTrue((dataset/'sample_tile_0001.png').exists())

    def test_label_preflight_and_direct_overview(self):
        with tempfile.TemporaryDirectory() as work:
            dataset, labels, output, _ = self.make_dataset(Path(work))
            (labels/'other.txt').write_text('')
            info = inspect_labels(dataset,labels)
            self.assertEqual(info['annotated'],1)
            self.assertEqual(info['orphan_names'],['other.txt'])
            TileManager(output_dir=dataset.parent).exclude('sample',[1])
            path = HighResOverviewReconstructor().reconstruct_dataset(dataset,64)
            self.assertTrue(Path(path).is_file())

    def test_renamed_dataset_uses_manifest_filenames(self):
        with tempfile.TemporaryDirectory() as work:
            dataset, labels, output, _ = self.make_dataset(Path(work))
            renamed = dataset.with_name('renamed_folder')
            dataset.rename(renamed)
            manager = TileManager(output_dir=renamed.parent)
            self.assertEqual(manager.exclude('renamed_folder',[1]),1)
            self.assertTrue((renamed/'excluded_tiles/sample_tile_0001.png').is_file())
            self.assertEqual(manager.list_excluded('renamed_folder'),[1])
            self.assertEqual(manager.restore('renamed_folder',[1]),1)


if __name__ == '__main__': unittest.main()
