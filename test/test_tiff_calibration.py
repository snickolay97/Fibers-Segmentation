"""Calibration metadata distinguishes microscopy lengths from print resolution."""
from pathlib import Path
import tempfile
import unittest
import numpy as np
import tifffile

from src.image_io import inspect_tiff


class TiffCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def ome(self, x=.433578, y=.433578, **metadata):
        path = self.root/'source.ome.tif'
        tifffile.imwrite(path,np.zeros((32,40),np.uint8),ome=True,
            metadata=dict(axes='YX', PhysicalSizeX=x,PhysicalSizeY=y,**metadata))
        return inspect_tiff(path)

    def test_ome_default_micrometres_and_single_plane(self):
        info = self.ome()
        self.assertEqual(info['plane_count'],1)
        self.assertIsNone(info['plane_axis'])
        self.assertEqual(info['calibration']['status'],'valid')
        self.assertEqual(info['calibration']['pixel_size_um'],.433578)

    def test_ome_nanometres_are_converted(self):
        calibration = self.ome(400,400,PhysicalSizeXUnit='nm',PhysicalSizeYUnit='nm')['calibration']
        self.assertAlmostEqual(calibration['pixel_size_um'],.4)

    def test_unequal_axes_are_not_collapsed_into_one_scale(self):
        calibration = self.ome(.4,.5)['calibration']
        self.assertEqual(calibration['status'],'anisotropic')
        self.assertIsNone(calibration['pixel_size_um'])
        self.assertEqual((calibration['x_um'],calibration['y_um']),(.4,.5))

    def test_imagej_reciprocal_xy_resolution_not_z_spacing(self):
        path = self.root/'imagej.tif'
        tifffile.imwrite(path,np.zeros((32,40),np.uint8),imagej=True,
            resolution=(2,2),metadata=dict(unit='um',spacing=99))
        self.assertEqual(inspect_tiff(path)['calibration']['pixel_size_um'],.5)

    def test_generic_print_dpi_is_reported_without_automatic_calibration(self):
        path = self.root/'print.tif'
        tifffile.imwrite(path,np.zeros((32,40),np.uint8),resolution=(300,300),resolutionunit='INCH')
        calibration = inspect_tiff(path)['calibration']
        self.assertEqual(calibration['status'],'resolution_only')
        self.assertIsNone(calibration['pixel_size_um'])

    def test_plain_tiff_and_stack_axes(self):
        path = self.root/'stack.tif'
        tifffile.imwrite(path,np.zeros((3,32,40),np.uint8),metadata=dict(axes='ZYX'),photometric='minisblack')
        info = inspect_tiff(path)
        self.assertEqual((info['plane_axis'],info['plane_count']),('Z',3))
        self.assertIsNone(info['calibration']['pixel_size_um'])
