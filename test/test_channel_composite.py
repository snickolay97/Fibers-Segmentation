"""Check channel selection, rendered pixels, and native-size exports."""

from pathlib import Path
import tempfile
import unittest

import numpy as np
import tifffile

from src.channel_composite import composite
from src.image_io import inspect_tiff


class ChannelCompositeTests(unittest.TestCase):
    def test_uint16_channels_and_plane_render_at_original_size(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'multichannel.ome.tif'
            data = np.zeros((2, 2, 9, 1603), np.uint16)
            data[1, 0, :, :] = 32768
            data[1, 1, :, :] = 65535
            data[1, 1, -1, -1] = 0
            tifffile.imwrite(source, data, ome=True, photometric='minisblack',
                             metadata={'axes': 'ZCYX', 'PhysicalSizeX': .4, 'PhysicalSizeY': .4})
            layers = [(0, (255, 0, 0), 1.0, 1.0), (1, (255, 255, 0), 1.0, .5)]
            before = source.read_bytes()
            preview, step = composite(source, 1, layers)
            self.assertEqual(step, 2)
            self.assertEqual(preview.shape, (5, 802, 3))
            self.assertEqual(tuple(preview[0, 0]), (255, 128, 0))
            export = Path(folder) / 'result.tif'
            self.assertEqual(composite(source, 1, layers, destination=export), export)
            result = tifffile.imread(export)
            self.assertEqual(result.shape, (9, 1603, 3))
            self.assertEqual(tuple(result[-1, -1]), (128, 0, 0))
            self.assertEqual(inspect_tiff(export)['calibration']['pixel_size_um'], .4)
            with self.assertRaises(ValueError):
                composite(source, 1, layers, destination=source)
            self.assertEqual(source.read_bytes(), before)

    def test_cancel_preserves_previous_export(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'rgb.tif'
            tifffile.imwrite(source, np.zeros((16, 20, 3), np.uint8), photometric='rgb')
            target = Path(folder) / 'existing.tiff'
            target.write_bytes(b'previous')
            layers = [(1, (0, 255, 0), 1, 1)]
            self.assertIsNone(composite(source, 0, layers, destination=target, cancelled=lambda: True))
            self.assertEqual(target.read_bytes(), b'previous')
