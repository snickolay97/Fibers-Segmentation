"""Active tile edits must feed preview, source-scale measurement and new labels."""

import csv
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import cv2
import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from src.app_settings import PipelineSettings
from src.block2_slicer import SmartSlicer
from src.block3_feature_extractor import TopologicalFeatureExtractor
from src.desktop import service
from src.desktop.i18n import get_language, set_language
from src.desktop.main_window import MainWindow
from src.desktop.project import Project
from src.desktop.qt import QtCore, QtWidgets
from src.desktop.result_tile import resolve_result_tile
from src.desktop.tile_edit import TileEdit, TileEditContext, activate_tile_version, import_saved_tile_edit
from src.desktop.widgets import image_pool
from src.overview_reconstructor import HighResOverviewReconstructor
from src.tile_edits import active_edit_revision, file_sha256, tile_artifact_path, tile_edit_signature
from src.tile_scale import fixed_canvas


class ActiveTileEditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.language = get_language()
        set_language('en')
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.project = Project.create(self.root / 'project.json')
        self.project.settings = PipelineSettings(target_size=64, overview_size=100,
                                                  min_sub_object_area=1).to_dict()
        self.base = self.root / 'dataset'
        self.image = np.zeros((80, 100), dtype=np.uint8)
        self.image[20:40, 10:30] = 200
        self.image[20:40, 65:85] = 200
        SmartSlicer(settings=PipelineSettings.from_dict(self.project.settings)).slice(
            self.image, self.image, np.ones_like(self.image), 'sample', self.base)
        self.dataset = dict(id='dataset-one', name='sample', path=str(self.base),
                            labels_dir=None, reviewed=True, results_current=False,
                            settings=self.project.settings)
        self.project.datasets.append(self.dataset)
        self.project.active_dataset_id = self.dataset['id']
        self.project.save()
        self.record = service.tile_records(self.dataset)[0]

    def tearDown(self):
        if hasattr(self, 'window'):
            self.window.close()
        QtCore.QThreadPool.globalInstance().waitForDone(5000)
        image_pool().waitForDone(5000)
        self.app.processEvents()
        self.temporary.cleanup()
        set_language(self.language)

    def context(self, record=None):
        record = record or self.record
        return TileEditContext(str(self.root), self.dataset['id'], str(self.base), record, 'native',
                                expected_revision=record.get('edit_reference'))

    def edit(self, record=None):
        context = self.context(record)
        return TileEdit(tile_artifact_path(self.base, context.record, 'native_filename'), context)

    def save_cut(self):
        edit = self.edit()
        edit.cut_side((50, 0), (50, 79), 1)
        return edit.save()

    def test_active_bundle_reopens_with_effective_mask_and_preserves_originals(self):
        originals = {key: file_sha256(self.base / self.record[key])
                     for key in ('filename', 'native_filename', 'valid_mask')}
        stale = self.edit()
        directory = self.save_cut()
        effective = service.tile_records(self.dataset)[0]
        self.assertEqual(effective['filename'], self.record['filename'])
        self.assertEqual(effective['edit_reference'], directory.relative_to(self.base).as_posix())
        reopened = self.edit(effective)
        self.assertFalse(reopened.valid[:, :50].any())
        np.testing.assert_array_equal(reopened.pixels[:, 50:], self.image[:, 50:])
        model = cv2.imread(str(tile_artifact_path(self.base, effective, 'filename')), cv2.IMREAD_UNCHANGED)
        np.testing.assert_array_equal(model, fixed_canvas(reopened.pixels, self.record['transform']))
        for key, before in originals.items():
            self.assertEqual(file_sha256(self.base / self.record[key]), before)
        row = dict(Tile_Name=Path(self.record['filename']).stem)
        self.assertEqual(resolve_result_tile(self.dataset, row, [effective]),
                         (directory / 'native.png', 'native'))
        reopened.erase([(70, 25)], 2, 'line')
        next_version = reopened.save()
        reopened.erase([(75, 25)], 2, 'line')
        final_version = reopened.save()
        self.assertNotEqual(next_version, final_version)
        self.assertEqual(active_edit_revision(self.base, self.record['id']), final_version.relative_to(self.base).as_posix())
        stale.erase([(70, 25)], 2, 'line')
        with self.assertRaisesRegex(ValueError, 'another window'):
            stale.save()

    def test_save_invalidates_training_then_measurement_uses_active_source_pixels(self):
        from src.desktop.model_evaluation_data import assemble_snapshot
        initial = service.extract(self.project, self.dataset['id'], labels_mode='auto')
        self.assertEqual(initial['objects'], 2)
        rows = service.read_results(self.dataset)[1]
        service.assign_object_class(self.project, self.dataset['id'], rows[0]['Tile_Name'], 1, 'fiber')
        groups = {self.dataset['id']: 'experiment'}
        self.assertEqual(len(assemble_snapshot(self.project, [self.dataset['id']], groups, 'Area')['rows']), 1)
        old_csv = Path(self.dataset['last_csv'])
        old_labels = Path(service.get_object_labels(self.dataset)['path'])
        labels_bytes = old_labels.read_bytes()
        self.save_cut()
        self.assertFalse(service.results_are_current(self.dataset))
        with self.assertRaises(ValueError):
            service.export_training_csv(self.dataset, self.root / 'stale.csv')
        self.assertEqual(assemble_snapshot(self.project, [self.dataset['id']], groups, 'Area')['rows'], [])
        current = service.extract(self.project, self.dataset['id'], labels_mode='auto')
        self.assertEqual(current['objects'], 1)
        self.assertTrue(service.results_are_current(self.dataset))
        self.assertEqual(float(service.read_results(self.dataset)[1][0]['Area']), 400)
        self.assertTrue(old_csv.is_file())
        self.assertEqual(old_labels.read_bytes(), labels_bytes)
        self.assertFalse((Path(self.dataset['results_dir']) / 'manual_object_labels.json').exists())
        provenance = json.loads((Path(self.dataset['results_dir']) / 'measurement_run.json').read_text())
        self.assertEqual(provenance['tile_edit_signature'], tile_edit_signature(self.base))
        self.assertTrue(provenance['tile_edit_signature'])
        measured = service.read_results(self.dataset)[1][0]
        service.assign_object_class(self.project, self.dataset['id'], measured['Tile_Name'], 1, 'fiber')
        training = assemble_snapshot(self.project, [self.dataset['id']], groups, 'Area')
        self.assertEqual(training['rows'][0]['values'][0], 400)

    def test_measurement_mask_coordinates_align_with_native_and_model_canvas(self):
        from src.desktop.result_tile import resolve_object_highlight
        service.extract(self.project, self.dataset['id'], labels_mode='auto')
        for row in service.read_results(self.dataset)[1]:
            record = next(r for r in service.tile_records(self.dataset) if Path(r['filename']).stem == row['Tile_Name'])
            highlight = resolve_object_highlight(self.dataset, row, record, 'native')
            self.assertFalse(highlight['recovered'])
            self.assertEqual(np.count_nonzero(highlight['mask']), float(row['Area']))
            native = cv2.imread(str(tile_artifact_path(self.base, record, 'native_filename')), 0)
            ys, xs = np.nonzero(highlight['mask'])
            x, y = highlight['origin']
            self.assertTrue(np.all(native[y+ys, x+xs] == 200))
            model = resolve_object_highlight(self.dataset, row, record, 'model')
            self.assertEqual(model['coordinate_size'], tuple(record['transform']['padded_native_shape'][::-1]))

    def test_drawn_signal_flag_is_retained_when_the_next_version_only_changes_gamma(self):
        edit = self.edit()
        edit.paint([(15, 40), (15, 50)], 1, 180, [15, 25])
        first = edit.save()
        metadata = json.loads((first/'edit.json').read_text(encoding='utf8'))
        self.assertTrue(metadata['contains_synthetic_signal'])
        second = self.edit(service.tile_records(self.dataset)[0])
        second.apply_gamma(1.2)
        saved = second.save()
        self.assertTrue(json.loads((saved/'edit.json').read_text(encoding='utf8'))['contains_synthetic_signal'])
        context = self.context(service.tile_records(self.dataset)[0])
        activate_tile_version(context, None)
        context = self.context(service.tile_records(self.dataset)[0])
        imported = import_saved_tile_edit(context, saved/'edit.json')
        self.assertTrue(json.loads((imported/'edit.json').read_text(encoding='utf8'))['contains_synthetic_signal'])

    def test_direct_extractor_rejects_a_version_changed_during_measurement(self):
        def progress(event):
            if event.get('completed'):
                self.save_cut()
        out = self.root / 'race'
        extractor = TopologicalFeatureExtractor(str(self.base), str(self.root / 'missing'), str(out),
            settings=PipelineSettings.from_dict(self.project.settings), progress=progress, allow_legacy=False)
        with self.assertRaisesRegex(ValueError, 'changed during measurement'):
            extractor.execute()
        self.assertFalse((out / 'dataset_features.csv').exists())

    def test_import_distinguishes_changed_active_versions_at_the_same_source_path(self):
        imported_project = Project.create(self.root / 'imported_project' / 'project.json')
        first = service.connect_dataset(imported_project, str(self.base))
        same = service.connect_dataset(imported_project, str(self.base))
        self.assertTrue(same['reused'])
        self.assertEqual(first['dataset']['id'], same['dataset']['id'])
        self.save_cut()
        changed = service.connect_dataset(imported_project, str(self.base))
        self.assertNotEqual(changed['dataset']['id'], first['dataset']['id'])
        effective = service.tile_records(changed['dataset'])[0]
        self.assertTrue(effective.get('edit_reference'))
        self.assertEqual(changed['dataset']['imported_edit_signature'], tile_edit_signature(self.base))

    def test_local_histogram_and_mask_exclude_erased_pixels(self):
        image = np.full((12, 15), 180, np.uint8)
        valid = np.ones_like(image, bool)
        valid[:, :10] = False
        image[~valid] = 0
        contour = np.array([[[0, 0]], [[14, 0]], [[14, 11]], [[0, 11]]], np.int32)
        extractor = TopologicalFeatureExtractor(str(self.base), '', str(self.root / 'histogram'),
            settings=PipelineSettings.from_dict(self.project.settings))
        threshold = cv2.threshold
        with patch('src.block3_feature_extractor.cv2.threshold', wraps=threshold) as observed:
            binary, _ = extractor._create_local_mask(contour, image, valid_mask=valid)
        np.testing.assert_array_equal(observed.call_args_list[0].args[0], np.full(60, 180, np.uint8))
        self.assertEqual(np.count_nonzero(binary), 60)

    def test_restoration_keeps_history_and_overview_uses_active_pixels(self):
        directory = self.save_cut()
        overview = HighResOverviewReconstructor().reconstruct_dataset(self.base, target_dim=100)
        rendered = cv2.imread(overview, cv2.IMREAD_GRAYSCALE)
        self.assertEqual(rendered[25, 15], 0)
        self.assertEqual(service.hit_test_tile(self.dataset, 15, 25), self.record['id'])
        marker = json.loads(Path(overview).with_suffix('.edits.json').read_text())
        self.assertEqual(marker, tile_edit_signature(self.base))
        effective = service.tile_records(self.dataset)[0]
        activate_tile_version(self.context(effective), None)
        self.assertIsNone(active_edit_revision(self.base, self.record['id']))
        self.assertTrue((directory / 'native.png').is_file())
        self.assertFalse(service.tile_records(self.dataset)[0].get('edit_reference'))

    def test_model_legacy_upscale_is_rejected_and_native_copy_can_be_imported(self):
        legacy = self.root / 'legacy'
        legacy.mkdir()
        cv2.imwrite(str(legacy / 'tile.png'), fixed_canvas(self.image, self.record['transform']))
        cv2.imwrite(str(legacy / 'valid_mask.png'), np.ones((64, 64), np.uint8) * 255)
        metadata = dict(schema_version=1, dataset_id=self.dataset['id'], tile_id=self.record['id'],
            transform=self.record['transform'], space='model', source_image=self.record['filename'],
            source_sha256=file_sha256(self.base / self.record['filename']),
            source_mask_sha256=file_sha256(self.base / self.record['valid_mask']))
        (legacy / 'edit.json').write_text(json.dumps(metadata))
        with self.assertRaisesRegex(ValueError, 'Redo the edit on the native tile'):
            import_saved_tile_edit(self.context(), legacy / 'edit.json')
        copied = self.image.copy()
        copied[:, :50] = 0
        mask = np.ones_like(copied, np.uint8) * 255
        mask[:, :50] = 0
        cv2.imwrite(str(legacy / 'tile.png'), copied)
        cv2.imwrite(str(legacy / 'valid_mask.png'), mask)
        metadata.update(space='native', source_image=self.record['native_filename'],
                        source_sha256=file_sha256(self.base / self.record['native_filename']))
        (legacy / 'edit.json').write_text(json.dumps(metadata))
        path = import_saved_tile_edit(self.context(), legacy / 'edit.json')
        np.testing.assert_array_equal(cv2.imread(str(path / 'native.png'), cv2.IMREAD_UNCHANGED), copied)

    def test_model_window_routes_to_native_and_save_refreshes_tile_images(self):
        preferences = QtCore.QSettings(str(self.root / 'prefs.ini'), QtCore.QSettings.Format.IniFormat)
        window = MainWindow(self.project, language='en', preferences=preferences)
        self.window = window
        self.addCleanup(window.close)
        window.show()
        window.sidebar.setCurrentRow(2)
        window._select_tile_id(self.record['id'])
        deadline = time.monotonic() + 5
        while window.model_view._loading and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        deadline = time.monotonic() + 15
        while window.process is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertIsNone(window.process,window.log.toPlainText())
        window._select_tile_id(self.record['id'])
        while (window.model_view._loading or window.native_view._loading) and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        dialog = window.model_view.open_original()
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.viewer.filename, str(self.base / self.record['native_filename']))
        native_frame = window.native_view._pixmap_item
        self.assertIsNotNone(native_frame)
        directory = self.save_cut()
        dialog.viewer.tile_saved.emit(self.dataset['id'], self.record['id'], directory)
        self.assertIs(window.native_view._pixmap_item, native_frame)
        self.assertEqual(Path(window.model_view.filename), directory / 'model.png')
        self.assertEqual(Path(window.native_view.filename), directory / 'native.png')
        self.assertEqual(Path(window.ownership_view.filename), directory / 'valid_mask.png')
        self.assertFalse(self.dataset['results_current'])
        with patch.object(window, 'start_job') as start:
            window.restore_prepared_tile()
            start.assert_called_once_with('tile_edit', dataset_id=self.dataset['id'], tile_id=self.record['id'], restore=True)


if __name__ == '__main__':
    unittest.main()
