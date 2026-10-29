import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pandas as pd
import tifffile

from src.app_settings import PipelineSettings, PipelineCancelled
from src.image_io import inspect_tiff, load_tiff_channel, preview_tiff
from src.pipeline_manager import BiomedicalPipelineManager


class ImageIOTests(unittest.TestCase):
    def test_planar_stack_channel_and_plane_keep_native_uint16(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'stack.tif'
            pixels = np.arange(2*3*7*9, dtype=np.uint16).reshape(2,3,7,9)*100
            tifffile.imwrite(path, pixels, photometric='minisblack', metadata={'axes':'ZCYX'})
            info = inspect_tiff(path)
            self.assertEqual((info['width'], info['height'], info['channels'], info['plane_count']), (9,7,3,2))
            raw, processing = load_tiff_channel(path, channel=2, plane=1)
            np.testing.assert_array_equal(raw, pixels[1,2])
            self.assertEqual(raw.dtype, np.uint16)
            np.testing.assert_array_equal(processing, (pixels[1,2]>>8).astype(np.uint8))
            self.assertEqual(preview_tiff(path, 2, 1, max_size=4).dtype, np.uint8)
            self.assertLessEqual(max(preview_tiff(path, 2, 1, max_size=4).shape),4)
            with self.assertRaises(ValueError): load_tiff_channel(path, 3, 0)
            with self.assertRaises(ValueError): load_tiff_channel(path, 0, 2)

    def test_interleaved_rgb_channel_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'rgb.tif'
            image = np.zeros((11,13,3), np.uint8); image[:,:,2] = 137
            tifffile.imwrite(path, image, photometric='rgb')
            self.assertEqual(inspect_tiff(path)['channels'],3)
            raw, processing = load_tiff_channel(path, 2)
            np.testing.assert_array_equal(raw, image[:,:,2])
            np.testing.assert_array_equal(processing, raw)

    def test_ambiguous_multiple_plane_axes_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'ambiguous.tif'
            tifffile.imwrite(path, np.zeros((2,3,7,9),np.uint8),
                             photometric='minisblack', metadata={'axes':'TZYX'})
            with self.assertRaisesRegex(ValueError,'Ambiguous'): inspect_tiff(path)

    def test_xy_order_is_transposed_to_yx(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'xy.tif'
            pixels=np.arange(13*11,dtype=np.uint8).reshape(13,11)
            tifffile.imwrite(path,pixels,photometric='minisblack',metadata={'axes':'XY'})
            info=inspect_tiff(path)
            self.assertEqual((info['width'],info['height']),(13,11))
            raw,_=load_tiff_channel(path)
            np.testing.assert_array_equal(raw,pixels.T)


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root/'input'; self.input.mkdir()
        self.settings = PipelineSettings(target_size=64, overview_size=96, bilateral_d=3,
                                         tophat_radius=3, bridge_kernel_size=3,
                                         buffer_kernel_size=1, min_corridor_width=3)

    def tearDown(self):
        self.temp.cleanup()

    def source(self, name='sample', dtype=np.uint8):
        image = np.zeros((48,48),dtype); image[20:23,8:38] = 200 if dtype==np.uint8 else 50000
        path = self.input/(name+'.tif')
        tifffile.imwrite(path,image,photometric='minisblack',metadata={'axes':'YX'})
        return path, image

    def manager(self, **kwargs):
        return BiomedicalPipelineManager(input_dir=self.input, output_dir=self.root/'tiles',
                                          raw_output_dir=self.root/'raw', labels_dir=self.root/'labels',
                                          features_dir=self.root/'features', settings=self.settings,
                                          **kwargs)

    def test_fresh_labeled_end_to_end_and_complete_reuse(self):
        source, _ = self.source()
        labels = self.root/'labels'; labels.mkdir()
        (labels/'sample_tile_0001.txt').write_text('1 0 0 0.75 0 0.75 0.75 0 0.75\n')
        events=[]
        first = self.manager(progress=events.append).run('end_to_end',labels_mode='require_annotations')
        self.assertEqual((first['processed'],first['failed']), (1,0))
        table = pd.read_csv(self.root/'features/sample/sample_features.csv')
        self.assertGreater(len(table),0)
        self.assertTrue((table.Class_ID==1).all())
        self.assertTrue((table.Measurement_Space=='source_pixels').all())
        manifest = json.loads((self.root/'tiles/sample/overview/sample_tiles_coords.json').read_text())
        self.assertEqual(manifest['run_info']['settings']['target_size'],64)
        self.assertEqual(manifest['run_info']['source']['path'],str(source.resolve()))
        self.assertTrue(any(event['stage']=='filter' for event in events))
        second = self.manager().run('filter_and_slice')
        self.assertEqual((second['skipped'],second['failed']), (1,0))

    def test_existing_partial_is_failed_and_never_extracted(self):
        self.source()
        dataset = self.root/'tiles/sample'; dataset.mkdir(parents=True)
        cv2.imwrite(str(dataset/'sample_tile_0001.png'), np.full((64,64),200,np.uint8))
        summary = self.manager().run('end_to_end')
        self.assertEqual((summary['processed'],summary['skipped'],summary['failed']), (0,0,1))
        self.assertFalse((self.root/'features/sample/sample_features.csv').exists())
        self.assertTrue((dataset/'sample_tile_0001.png').exists())

    def test_failed_source_does_not_block_next_valid_source(self):
        broken = self.input/'a_bad.tif'; broken.write_text('not TIFF')
        self.source('b_good')
        summary = self.manager().run('end_to_end')
        self.assertEqual((summary['processed'],summary['failed']), (1,1))
        self.assertFalse((self.root/'tiles/a_bad').exists())
        self.assertTrue((self.root/'features/b_good/b_good_features.csv').exists())

    def test_native_raw_uint16_is_preserved(self):
        _, raw = self.source(dtype=np.uint16)
        self.settings.save_raw_tiles=True
        summary=self.manager().run('filter_and_slice')
        self.assertEqual(summary['failed'],0)
        native=cv2.imread(str(self.root/'raw/sample/native/native_0001.png'),cv2.IMREAD_UNCHANGED)
        self.assertEqual(native.dtype,np.uint16)
        np.testing.assert_array_equal(native,raw)

    def test_cancel_during_export_does_not_publish_partial_folder(self):
        self.source()
        stop={'value':False}
        def progress(event):
            if event.get('message')=='Saving native pixels and model tiles': stop['value']=True
        result=self.manager(progress=progress,cancelled=lambda:stop['value']).run('filter_and_slice')
        self.assertTrue(result['cancelled'])
        self.assertFalse((self.root/'tiles/sample').exists())
        self.assertEqual(list((self.root/'tiles').iterdir()),[])

    def test_existing_dataset_with_changed_settings_is_not_reused(self):
        self.source()
        self.assertEqual(self.manager().run()['processed'],1)
        self.settings.gamma=1.4
        summary=self.manager().run('end_to_end')
        self.assertEqual(summary['failed'],1)
        self.assertIn('different settings',summary['datasets'][0]['error'])

    def test_exclusion_uses_manager_output_paths(self):
        self.source()
        self.assertEqual(self.manager().run()['processed'],1)
        summary=self.manager().run('manage_tiles',dataset_name='sample',exclude_specs=[1])
        self.assertEqual(summary['processed'],1)
        self.assertFalse((self.root/'tiles/sample/sample_tile_0001.png').exists())
        self.assertTrue((self.root/'tiles/sample/excluded_tiles/sample_tile_0001.png').exists())
        self.assertTrue((self.root/'tiles/sample/native/native_0001.png').exists())

    def test_empty_batch_has_no_phantom_dataset_or_features(self):
        summary=self.manager().run('end_to_end')
        self.assertEqual(summary,dict(processed=0,skipped=0,failed=0,cancelled=False,datasets=[]))
        self.assertFalse((self.root/'features').exists())

    def test_invalid_annotation_fails_one_dataset_and_continues_batch(self):
        self.source('a_bad_label'); self.source('b_good')
        self.assertEqual(self.manager().run()['processed'],2)
        labels=self.root/'labels'; labels.mkdir()
        (labels/'a_bad_label_tile_0001.txt').write_text('0 0.5 0.5 0.2 0.3\n')
        summary=self.manager().run('extract_features')
        self.assertEqual((summary['processed'],summary['failed']),(1,1))
        self.assertTrue((self.root/'features/b_good/b_good_features.csv').exists())
        self.assertFalse((self.root/'features/a_bad_label/a_bad_label_features.csv').exists())

    def test_explicit_sources_ignore_unselected_broken_tiff(self):
        path,_=self.source('chosen')
        (self.input/'not_selected.tif').write_text('not TIFF')
        summary=self.manager(input_files=[path]).run()
        self.assertEqual((summary['processed'],summary['failed']),(1,0))
        self.assertEqual([record['name'] for record in summary['datasets']],['chosen'])

    def test_failed_filtered_publication_rolls_back_raw_dataset(self):
        self.source(dtype=np.uint16)
        self.settings.save_raw_tiles=True
        manager=self.manager()
        original=manager._publish
        def publish(stage,destination,root):
            if Path(root)==Path(manager.output_dir): raise OSError('Injected publication failure')
            return original(stage,destination,root)
        with patch.object(manager,'_publish',side_effect=publish): result=manager.run()
        self.assertEqual(result['failed'],1)
        self.assertFalse((self.root/'raw/sample').exists())
        self.assertFalse((self.root/'tiles/sample').exists())
        self.assertEqual(list((self.root/'raw').iterdir()),[])

    def test_missing_explicit_dataset_reports_failure(self):
        summary=self.manager().run('extract_features',dataset_names=['missing'])
        self.assertEqual(summary['failed'],1)
        self.assertEqual(summary['processed'],0)


if __name__=='__main__': unittest.main()
