"""Pixel models use reviewed native masks and publish independent class maps."""

import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from src.desktop import service
from src.desktop.i18n import get_language, set_language
from src.desktop.object_labels import save_object_class
from src.desktop.pixel_segmentation import _features
from src.desktop.project import Project, atomic_json
from src.desktop.tile_edit import _read_png, _write_png


class PixelSegmentationTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(set_language, get_language())
        set_language('en')
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.project = Project.create(self.root / 'project.json')
        self.tiles = self.root / 'tiles'
        self.results = self.root / 'measurements' / 'one'
        self.tiles.mkdir()
        masks = self.results / 'verification_masks'
        masks.mkdir(parents=True)

        shape = (90, 110)
        valid = np.ones(shape, np.uint8) * 255
        valid[:2] = valid[:, :2] = 0
        image = np.full(shape, 5 << 8, np.uint16)
        entries = []
        with (self.results / 'features.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(('Tile_Name', 'Object_ID', 'Area', 'Measurement_Space'))
            for obj, (x, y, intensity) in enumerate(((15, 15, 80), (65, 15, 210), (65, 65, 140)), 1):
                image[y:y + 8, x:x + 8] = intensity << 8
                name = f'mask_{obj}.png'
                _write_png(masks / name, np.full((8, 8), 255, np.uint8))
                entries.append(dict(tile_name='tile', object_id=obj, tile_shape=shape,
                                    measurement_space='source_pixels', origin_xy=(x, y), mask=name))
                writer.writerow(('tile', obj, 64, 'source_pixels'))
        added = np.zeros((8, 8), np.uint8)
        added[0, 0] = 255
        _write_png(masks / 'manual_added.png', added)
        entries[0]['manual_added_mask'] = 'manual_added.png'
        atomic_json(masks / 'object_locations.json', dict(schema_version=1, objects=entries))
        _write_png(self.tiles / 'native.png', image)
        _write_png(self.tiles / 'tile.png', (image >> 8).astype(np.uint8))
        _write_png(self.tiles / 'valid.png', valid)
        record = dict(id=1, filename='tile.png', native_filename='native.png', valid_mask='valid.png',
                      transform=dict(native_crop_shape=shape))
        manifest = dict(schema_version=3, source_name='one', image_shape=shape, tiles=[record])
        atomic_json(self.tiles / 'overview' / 'one_tiles_coords.json', manifest)
        run = dict(manifest_signature=service.fingerprint(manifest), active_tile_ids=[1],
                   annotation_signature=service.content_signature(None))
        atomic_json(self.results / 'measurement_run.json', run)
        dataset = dict(id='one', name='one', path=str(self.tiles), results_current=True,
                       results_dir=str(self.results), last_csv=str(self.results / 'features.csv'),
                       measurement_signature=service.fingerprint(run))
        self.project.datasets.append(dataset)
        save_object_class(dataset, 'tile', 1, 'particle')
        save_object_class(dataset, 'tile', 2, 'fiber')
        save_object_class(dataset, 'tile', 3, 'agglomeration')

    def test_worker_fits_selected_foreground_and_writes_valid_native_map(self):
        def science_bytes():
            return {path: path.read_bytes() for root in (self.tiles, self.results)
                    for path in root.rglob('*') if path.is_file()}

        before = science_bytes()
        trained = service.execute_action(self.project, dict(action='train_pixel_segmentation',
            dataset_ids=['one'], class_ids=[0, 1], forest_tree_count=9, seed=42))
        metadata = json.loads(Path(trained['metadata']).read_text(encoding='utf-8'))
        self.assertEqual(metadata['class_ids'], [0, 1])
        self.assertEqual(metadata['label_codes'], {'0': 'background', '1': 'particle',
                                                  '2': 'fiber', '255': 'outside_ownership'})
        self.assertEqual(metadata['available_pixels']['1'], 63)
        self.assertEqual(metadata['available_pixels']['2'], 64)
        self.assertEqual(metadata['samples_per_label'], 63)
        self.assertEqual(metadata['datasets'][0]['tiles'][0]['native_bit_depth'], 16)
        request = dict(action='apply_pixel_segmentation', dataset_id='one', tile_id=1, model_path=trained['path'])
        result = service.execute_action(self.project, request)
        prediction = json.loads(Path(result['metadata']).read_text(encoding='utf-8'))
        self.assertEqual(prediction['overlay_colors_rgb'], result['overlay_colors_rgb'])
        self.assertEqual(set(prediction['overlay_colors_rgb']), {'0', '1'})
        codes, _ = _read_png(Path(result['path']))
        overlay, _ = _read_png(Path(result['overlay']))
        self.assertEqual(codes.shape, (90, 110))
        self.assertEqual(overlay.shape, (90, 110, 3))
        self.assertTrue(np.all(codes[:2] == 255))
        self.assertTrue(np.all(codes[:, :2] == 255))
        self.assertEqual(set(np.unique(codes[2:, 2:])), {0, 1, 2})
        self.assertEqual((codes[19, 19], codes[19, 69], codes[85, 100]), (1, 2, 0))
        self.assertEqual(science_bytes(), before)
        with Path(trained['path']).open('ab') as stream:
            stream.write(b'edited')
        with self.assertRaisesRegex(ValueError, 'changed or is incompatible'):
            service.execute_action(self.project, request)

    def test_local_features_do_not_change_at_patch_edges(self):
        rng = np.random.default_rng(42)
        gray = rng.integers(0, 256, (40, 60), dtype=np.uint8)
        valid = rng.random(gray.shape) > .2
        whole = _features(gray, valid, (0, 40, 0, 60))
        np.testing.assert_array_equal(whole[8:23, 11:29], _features(gray, valid, (8, 23, 11, 29)))
