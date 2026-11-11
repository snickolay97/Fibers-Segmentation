"""Verify half-plane cuts and gamma adjustment on saved tile copies."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import cv2
import numpy as np

from src.desktop.tile_edit import TileEdit, TileEditContext


class TileEditOperationTests(unittest.TestCase):
    def make_edit(self, pixels, valid):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        dataset = root / 'dataset'
        dataset.mkdir()
        for name, image in (('tile.png', pixels), ('mask.png', valid.astype(np.uint8) * 255)):
            ok, encoded = cv2.imencode('.png', image)
            self.assertTrue(ok)
            (dataset / name).write_bytes(encoded.tobytes())
        context = TileEditContext(str(root), 'prepared', str(dataset),
                                  dict(id=1, filename='tile.png', valid_mask='mask.png'), 'native')
        return TileEdit(dataset / 'tile.png', context)

    def test_cut_extends_across_tile_and_retains_pixels_on_line(self):
        valid = np.ones((7, 7), dtype=bool)
        valid[:, 0] = False
        pixels = np.where(valid, 80, 0).astype(np.uint8)
        edit = self.make_edit(pixels, valid)
        first, last = (2, 2), (4, 4)
        expected_valid = valid & (np.arange(7)[:, None] <= np.arange(7)[None, :])
        self.assertTrue(edit.cut_side(first, last, 1))
        np.testing.assert_array_equal(edit.valid, expected_valid)
        np.testing.assert_array_equal(edit.pixels, np.where(expected_valid, 80, 0))
        self.assertFalse(edit.cut_side(first, last, 1))
        edit.undo()
        np.testing.assert_array_equal(edit.valid, valid)
        np.testing.assert_array_equal(edit.pixels, pixels)
        self.assertTrue(edit.cut_side(last, first, -1))
        np.testing.assert_array_equal(edit.valid, expected_valid)

    def test_smaller_side_uses_valid_pixels_and_leaves_ties_for_manual_choice(self):
        valid = np.ones((5, 8), dtype=bool)
        valid[:, :3] = False
        edit = self.make_edit(np.where(valid, 80, 0).astype(np.uint8), valid)
        self.assertEqual(edit.smaller_cut_side((4, 1), (4, 3)), 1)
        self.assertIsNone(edit.smaller_cut_side((5, 1), (5, 3)))
        self.assertIsNone(edit.smaller_cut_side((3, 1), (3, 3)))
        self.assertIsNone(edit.smaller_cut_side((4, 1), (4, 1)))
        self.assertFalse(edit.cut_side((4, 1), (4, 1), 1))
        self.assertFalse(edit.cut_side((4, 1), (4, 3), 0))
        self.assertEqual(edit.operations, [])

    def test_gamma_preview_commit_and_undo_preserve_depth_and_mask(self):
        pixels = np.array([[0, 16384, 65535, 101], [10, 16384, 0, 40000]], dtype=np.uint16)
        valid = np.array([[True, True, True, False], [False, True, True, True]])
        edit = self.make_edit(pixels, valid)
        box = (0, 0, 4, 1)
        preview = edit.gamma_preview(2.0, box)
        self.assertEqual(preview.dtype, np.uint16)
        np.testing.assert_array_equal(preview, [[0, 32767, 65535, 101], [10, 16384, 0, 40000]])
        np.testing.assert_array_equal(edit.pixels, pixels)
        self.assertFalse(edit.apply_gamma(1.0))
        self.assertEqual(edit.operations, [])
        self.assertTrue(edit.apply_gamma(2.0, box))
        np.testing.assert_array_equal(edit.pixels, preview)
        np.testing.assert_array_equal(edit.valid, valid)
        edit.undo()
        np.testing.assert_array_equal(edit.pixels, pixels)
        self.assertTrue(edit.apply_gamma(0.5))
        self.assertLess(edit.pixels[1, 1], pixels[1, 1])
        with self.assertRaises(ValueError):
            edit.gamma_preview(float('nan'))

    def test_save_records_cut_side_and_gamma_bounds(self):
        valid = np.ones((5, 7), dtype=bool)
        edit = self.make_edit(np.full(valid.shape, 80, dtype=np.uint8), valid)
        source = edit.source.read_bytes()
        edit.cut_side((1, 2), (3, 2), 1)
        edit.apply_gamma(2.0)
        result = edit.save()
        self.assertEqual(edit.source.read_bytes(), source)
        journal = json.loads((result / 'edit.json').read_text(encoding='utf-8'))
        self.assertEqual(journal['operations'], [
            dict(tool='cut_side', points=[[1, 2], [3, 2]], side=1),
            dict(tool='gamma', bounds_ltrb=[0, 0, 7, 5], gamma=2.0),
        ])


if __name__ == '__main__':
    unittest.main()
