"""The measured object's exact tile remains reachable during manual review."""
import csv
import json
import cv2
import numpy as np
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from src.desktop.qt import QtCore, QtGui, QtWidgets
from src.desktop.project import Project
from src.desktop.main_window import MainWindow
from src.desktop.result_tile import resolve_result_tile, resolve_object_highlight
from src.desktop.widgets import ImageViewer, image_pool


class ResultTileResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.dataset = dict(path=str(self.root))
        self.record = dict(id=4, filename='sample_tile_0004.png', native_filename='native/sample_tile_0004.png')
        self.row = dict(Tile_Name='sample_tile_0004', Object_ID='12')

    def tearDown(self):
        self.temporary.cleanup()

    def file(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'unchanged')
        return path

    def test_native_is_preferred_without_scaling_or_changing_files(self):
        native = self.file(self.record['native_filename'])
        self.file(self.record['filename'])
        self.record['transform'] = dict(source_pixels_per_output_pixel=2.5)
        path, space = resolve_result_tile(self.dataset, self.row, [self.record])
        self.assertEqual(path, native)
        self.assertEqual(space, 'native')
        self.assertEqual(native.read_bytes(), b'unchanged')

    def test_missing_native_uses_labeled_model_including_excluded_tile(self):
        path = self.file('excluded_tiles/' + self.record['filename'])
        self.assertEqual(resolve_result_tile(self.dataset, self.row, [self.record]), (path, 'model'))

    def test_missing_images_raise_and_do_not_open_a_different_tile(self):
        self.file('sample_tile_0003.png')
        with self.assertRaises(FileNotFoundError):
            resolve_result_tile(self.dataset, self.row, [self.record])
        with self.assertRaises(ValueError):
            resolve_result_tile(self.dataset, dict(Tile_Name='sample_tile_0003'), [self.record])

    def test_ambiguous_manifest_and_escaping_native_paths_are_rejected(self):
        with self.assertRaises(ValueError):
            resolve_result_tile(self.dataset, self.row, [self.record, dict(self.record)])
        self.record['native_filename'] = '../outside.png'
        with self.assertRaises(ValueError):
            resolve_result_tile(self.dataset, self.row, [self.record])

    def test_old_crop_requires_a_unique_exact_foreground_match(self):
        self.dataset['results_dir'] = str(self.root/'results')
        image = np.zeros((80, 100), np.uint8)
        template = np.array([[0, 41, 62], [81, 99, 123], [0, 158, 0]], np.uint8)
        image[20:23, 35:38] = template
        native = self.root/self.record['native_filename']
        crop = self.root/'results/verification_masks/sample_tile_0004/obj_012_Unknown.png'
        for path, pixels in [(native, image), (crop, np.pad(template, 2))]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(cv2.imencode('.png', pixels)[1].tobytes())
        found = resolve_object_highlight(self.dataset, self.row, self.record, 'native')
        self.assertEqual(found['origin'], (35, 20))
        self.assertTrue(found['recovered'])
        image[40:43, 65:68] = template
        native.write_bytes(cv2.imencode('.png', image)[1].tobytes())
        self.assertIsNone(resolve_object_highlight(self.dataset, self.row, self.record, 'native'))


class ResultTileUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        project = Project.create(self.root / 'project.json')
        preferences = QtCore.QSettings(str(self.root / 'preferences.ini'), QtCore.QSettings.Format.IniFormat)
        self.window = MainWindow(project, language='en', preferences=preferences)
        self.dataset = dict(path=str(self.root), results_dir=str(self.root / 'results'))
        self.records = [dict(id=i, filename=f'sample_tile_{i:04d}.png',
                             native_filename=f'native/sample_tile_{i:04d}.png') for i in (1, 2)]
        self.rows = [dict(Tile_Name=f'sample_tile_{i:04d}', Object_ID=str(10 + i), Class_Name='Unknown') for i in (1, 2)]
        csv_path = self.root / 'features.csv'
        with csv_path.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(self.rows[0]))
            writer.writeheader()
            writer.writerows(self.rows)
        for record in self.records:
            path = self.root / record['native_filename']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'unchanged')
        self.window.results_table.load_csv(csv_path)

    def tearDown(self):
        self.window.close()
        image_pool().waitForDone(5000)
        self.app.processEvents()
        self.temporary.cleanup()

    def test_open_selected_tile_preserves_current_object_and_labels(self):
        dialog = QtWidgets.QDialog(self.window)
        with patch.object(self.window, 'selected_dataset', return_value=self.dataset), \
             patch.object(self.window.service, 'tile_records', return_value=self.records), \
             patch.object(ImageViewer, 'open_image_window', return_value=dialog) as opened:
            self.window.object_gallery.set_rows(self.rows, self.dataset)
            self.window._gallery_selected(self.rows[1])
            self.assertTrue(self.window.open_object_tile_button.isEnabled())
            selected = dict(self.window.results_table.selected_row())
            self.window.open_object_tile_button.click()
            self.assertEqual(opened.call_args.args[0], self.root / self.records[1]['native_filename'])
            self.assertIn('12', opened.call_args.kwargs['caption'])
            self.assertEqual(self.window.results_table.selected_row(), selected)
            self.assertIs(self.window._result_tile_dialog, dialog)
            self.window.results_table.table.clearSelection()
            self.assertFalse(self.window.open_object_tile_button.isEnabled())

    def test_missing_tile_shows_error_without_changing_selected_object(self):
        with patch.object(self.window, 'selected_dataset', return_value=self.dataset), \
             patch.object(self.window.service, 'tile_records', return_value=self.records), \
             patch.object(self.window, '_error') as error:
            self.window.results_table.select_object(self.rows[0]['Tile_Name'], self.rows[0]['Object_ID'])
            selected = dict(self.window.results_table.selected_row())
            (self.root / self.records[0]['native_filename']).unlink()
            self.assertIsNone(self.window.open_result_tile())
            self.assertIsInstance(error.call_args.args[0], FileNotFoundError)
            self.assertEqual(self.window.results_table.selected_row(), selected)

    def test_real_tile_dialog_decodes_saved_native_pixels_and_refresh_closes_it(self):
        path = self.root / self.records[0]['native_filename']
        image = QtGui.QImage(2501, 32, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtGui.QColor('#138675'))
        self.assertTrue(image.save(str(path)))
        with patch.object(self.window, 'selected_dataset', return_value=self.dataset), \
             patch.object(self.window.service, 'tile_records', return_value=self.records):
            self.window.results_table.select_object(self.rows[0]['Tile_Name'], self.rows[0]['Object_ID'])
            dialog = self.window.open_result_tile()
            self.assertIsNotNone(dialog)
            until = time.monotonic() + 5
            while dialog.viewer._loading and time.monotonic() < until:
                self.app.processEvents()
                time.sleep(.01)
            self.assertEqual(dialog.viewer.original_size, (2501, 32))
            self.assertEqual(dialog.viewer._pixmap_item.pixmap().width(), 2501)
            self.window.refresh_results(quiet=True)
            self.assertIsNone(self.window._result_tile_dialog)


if __name__ == '__main__':
    unittest.main()
