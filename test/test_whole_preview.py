"""Whole-image comparisons use native filtering before display reduction."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
import cv2
import numpy as np
import tifffile
from src.desktop.project import Project
from src.desktop import service
from src.desktop.source_options import source_options


class WholePreviewTests(unittest.TestCase):
    def test_interactive_view_keeps_channel_plane_and_native_region_coordinates(self):
        from src.image_io import read_tiff_view

        path = Path(self.project.workspace) / 'view.tif'
        stack = np.arange(2 * 2 * 19 * 23, dtype=np.uint16).reshape(2, 2, 19, 23) << 4
        tifffile.imwrite(path, stack, metadata={'axes': 'ZCYX'}, photometric='minisblack')
        expected = (stack[1, 0] >> 8).astype(np.uint8)
        overview, dimensions, step = read_tiff_view(path, 0, 1, 10)
        self.assertEqual(dimensions, (23, 19))
        np.testing.assert_array_equal(overview, expected[::step, ::step])
        pixels, origin, step = read_tiff_view(path, 0, 1, 10, (22, 18))
        self.assertEqual((origin, step), ((13, 9), 1))
        np.testing.assert_array_equal(pixels, expected[9:19, 13:23])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = Project.create(self.root/'project.json')
        for key in ('enable_bilateral','enable_tophat','enable_gamma','enable_closing','enable_dilation'):
            self.project.settings[key] = False
        self.project.save()

    def tearDown(self):
        self.temp.cleanup()

    def source(self,name='sample',size=.4,shape=(1300,1600)):
        path=self.root/(name+'.ome.tif')
        image=np.zeros(shape,np.uint8)
        image[5:20,5:20]=201
        image[-20:-5,-20:-5]=199
        tifffile.imwrite(path,image,ome=True,metadata=dict(axes='YX',PhysicalSizeX=size,PhysicalSizeY=size))
        return service.add_sources(self.project,[path])[0],image

    def test_preview_contains_both_far_corners_has_readable_names_and_reuses_cache(self):
        source,image=self.source()
        result=service.preview(self.project,source_id=source['id'])
        before=cv2.imread(result['input_path'],cv2.IMREAD_GRAYSCALE)
        np.testing.assert_array_equal(before,image)
        self.assertEqual(result['source_shape'],[1300,1600])
        self.assertFalse(result['approximate'])
        self.assertIn('Preview_001',result['input_path'])
        with patch('src.block1_preprocessor.GlobalPreprocessor.process',side_effect=AssertionError('Cache must avoid processing')):
            again=service.preview(self.project,source_id=source['id'])
        self.assertTrue(again['reused'])
        self.assertEqual(again['input_path'],result['input_path'])

    def test_native_processing_precedes_display_resize(self):
        source,_image=self.source(shape=(2500,2700))
        with patch('src.block1_preprocessor.GlobalPreprocessor.process',side_effect=lambda a:(a,a)) as process:
            result=service.preview(self.project,source_id=source['id'])
        self.assertEqual(process.call_args.args[0].shape,(2500,2700))
        self.assertEqual(max(result['display_shape']),2400)
        self.assertEqual(result['calibration']['pixel_size_um'],.4)

    def test_native_artifacts_preserve_pixels_and_upgrade_the_preview_cache(self):
        from src.image_io import read_tiff_view

        source, image = self.source(shape=(25, 2510))
        mask = (image > 200).astype(np.uint8) * 255
        with patch('src.block1_preprocessor.GlobalPreprocessor.process', return_value=(image, mask)) as process:
            small = service.preview(self.project, source_id=source['id'])
            native = service.preview(self.project, source_id=source['id'], native_resolution=True)
            cached = service.preview(self.project, source_id=source['id'], native_resolution=True)
        self.assertNotIn('native_filtered_path', small)
        self.assertEqual(process.call_count, 2)
        self.assertTrue(cached['reused'])
        for key, expected in (('native_filtered_path', image), ('native_mask_path', mask)):
            np.testing.assert_array_equal(tifffile.imread(native[key]), expected)
            pixels, (x, y), step = read_tiff_view(native[key], 0, 0, 20, center=(15, 12))
            self.assertEqual(step, 1)
            np.testing.assert_array_equal(pixels, expected[y:y+20, x:x+20])

    def test_per_source_scales_and_explicit_manual_override(self):
        first,_=self.source('first',.4)
        second,_=self.source('second',.7)
        a,_=source_options(self.project,self.project.settings,source=first)
        b,_=source_options(self.project,self.project.settings,source=second)
        self.assertEqual((a.pixel_size_um,b.pixel_size_um),(.4,.7))
        self.assertIsNone(self.project.settings['pixel_size_um'])
        self.project._extra_fields['calibration_mode']='manual'
        settings=dict(self.project.settings,pixel_size_um=.25)
        for source in (first,second):
            options,_=source_options(self.project,settings,source=source)
            self.assertEqual(options.pixel_size_um,.25)

    def test_automatic_scale_reaches_preparation_measurements_and_provenance(self):
        source,_=self.source(shape=(160,192))
        self.project.settings['target_size']=128
        self.project.settings['overview_size']=200
        prepared=service.prepare(self.project,[source['id']])
        self.assertEqual(prepared['processed'],1,prepared)
        dataset=self.project.get_dataset(prepared['datasets'][0])
        self.assertEqual(dataset['settings']['pixel_size_um'],.4)
        manifest=service.dataset_manifest(dataset)
        self.assertEqual(manifest['run_info']['source_image']['calibration']['pixel_size_um'],.4)
        self.assertEqual(manifest['run_info']['settings']['pixel_size_um'],.4)
        extracted=service.extract(self.project,dataset['id'],labels_mode='auto')
        self.assertGreater(extracted['objects'],0)
        columns,rows=service.read_results(dataset)
        self.assertIn('Area_um2',columns)
        for row in rows:
            self.assertAlmostEqual(float(row['Area_um2']),float(row['Area'])*.4*.4,places=5)
        provenance=json.loads((Path(dataset['results_dir'])/'measurement_run.json').read_text(encoding='utf-8'))
        self.assertEqual(provenance['calibration']['source'],'OME PhysicalSizeX/Y')
        self.assertEqual(provenance['calibration']['mode'],'auto')
        self.assertIsNone(self.project.settings['pixel_size_um'])
