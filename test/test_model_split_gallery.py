"""Visual inspection uses saved membership, class labels and measurement versions."""

from importlib import import_module
import os
from pathlib import Path
import tempfile
import unittest

from PIL import Image

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from src.desktop.model_evaluation_ui import ModelEvaluationPage, _class_name
from src.desktop.evaluation_crops import EvaluationCrops
from src.desktop.i18n import get_language, set_language
from src.desktop.model_split_gallery import ModelSplitGallery
from src.desktop.project import atomic_json
from src.desktop.qt import BINDING, QtCore, QtWidgets
from src.desktop.service import fingerprint
from src.desktop.widgets import image_pool


QTest = import_module(f'{BINDING}.QtTest').QTest


class ModelSplitGalleryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.addCleanup(set_language, get_language())
        set_language('en')

    def tearDown(self):
        image_pool().waitForDone(5000)
        self.app.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        self.app.processEvents()

    @staticmethod
    def payload(results_dir=None):
        rows = [dict(dataset_id='dataset', tile_name='tile', object_id=index,
                     target=index % 2, values=[index * 1.0]) for index in (1, 2, 3)]
        dataset = dict(dataset_id='dataset', name='Data', results_dir=results_dir)
        return dict(snapshot=dict(rows=rows, datasets=[dataset], features=['Area']),
                    plan=dict(train=[0, 1], test=[2], folds=[dict(train=[0], test=[1])]),
                    report=dict(models={'tree': {}}, predictions=[dict(rows[2], predicted={'tree': 0})]))

    def test_gallery_shows_frozen_masks_and_separates_test_truth_from_prediction(self):
        with tempfile.TemporaryDirectory(prefix='model_gallery_') as folder:
            root = Path(folder)
            base = root / 'measurements/Measurement_001/verification_masks'
            base.mkdir(parents=True)
            mask = base / 'mask.png'
            Image.new('L', (8, 8), 255).save(mask)
            entries = [dict(tile_name='tile', object_id=i, mask='mask.png') for i in (1, 2, 3)]
            atomic_json(base / 'object_locations.json', dict(schema_version=1, objects=entries))
            dialog = ModelSplitGallery(None, root, self.payload('measurements/Measurement_001'), _class_name)
            try:
                self.assertEqual(Path(dialog.image.filename), mask)
                self.assertIn('Reviewed class — Fiber', dialog.detail.text())
                self.assertEqual(len(dialog.cards.rows), 2)
                dialog.part.setCurrentIndex(dialog.part.findData('test'))
                self.assertEqual(len(dialog.cards.rows), 1)
                self.assertIn('Prediction — Particle', dialog.detail.text())
                self.assertNotIn('Reviewed class', dialog.detail.text())
                dialog.reveal.setChecked(True)
                self.assertIn('Reviewed class — Fiber', dialog.detail.text())
                dialog.part.setCurrentIndex(dialog.part.findData(1))
                self.assertIn('fold', dialog.info.text())
                self.assertFalse(dialog.reveal.isChecked())
                self.assertNotIn('Prediction', dialog.detail.text())
                self.assertEqual(dialog.cards.rows[0]['Object_ID'], 2)
            finally:
                dialog.close()
                self.app.processEvents()

    def test_table_input_without_project_identifiers_has_no_mask_lookup(self):
        data = self.payload()
        row = data['snapshot']['rows'][0]
        row.update(tile_name='', object_id=-1)
        dialog = ModelSplitGallery(None, '.', data, _class_name)
        try:
            self.assertTrue(dialog.table_only)
            self.assertIn('No verified project measurement', dialog.image.caption.text())
            self.assertIn('without images', dialog.info.text())
            self.assertIn('Area = 1', dialog.detail.text())
        finally:
            dialog.close()
            self.app.processEvents()

    def test_arrow_buttons_and_keys_navigate_the_visible_list(self):
        dialog = ModelSplitGallery(None, '.', self.payload(), _class_name)
        try:
            dialog.show()
            dialog.activateWindow()
            self.app.processEvents()
            self.assertTrue(dialog.cards.view.hasFocus())
            self.assertEqual(dialog.position.text(), '1 / 2')
            QTest.keyClick(dialog.cards.view, QtCore.Qt.Key.Key_Right)
            self.assertEqual(dialog.position.text(), '2 / 2')
            self.assertFalse(dialog.next_button.isEnabled())
            dialog.previous_button.click()
            self.assertEqual(dialog.position.text(), '1 / 2')
            dialog.image.view.setFocus()
            QTest.keyClick(dialog.image.view, QtCore.Qt.Key.Key_Right)
            self.assertEqual(dialog.position.text(), '2 / 2')
            dialog.previous_button.click()
            search = dialog.cards.search
            search.setText('tile')
            search.setFocus()
            search.setCursorPosition(0)
            QTest.keyClick(search, QtCore.Qt.Key.Key_Right)
            self.assertEqual(search.cursorPosition(), 1)
            self.assertEqual(dialog.position.text(), '1 / 2')
            search.setText('particle')
            self.assertEqual(dialog.position.text(), '1 / 1')
            self.assertIn('Reviewed class — Particle', dialog.detail.text())
        finally:
            dialog.close()
            self.app.processEvents()

    def test_comparison_windows_share_data_and_keep_separate_column_widths(self):
        parent = QtWidgets.QWidget()
        page = ModelEvaluationPage(parent)
        prediction = dict(group='source', tile_name='tile', object_id=1, target=0,
                          predicted={'tree': 1, 'forest': 0})
        page.current_result = dict(report=dict(
            classes=[0, 1], predictions=[prediction], tree='', models={
                'tree': dict(parameters={}, tuning=[], confusion=[[0, 1], [0, 0]]),
                'forest': dict(parameters={}, tuning=[], confusion=[[1, 0], [0, 0]]),
            }))
        page.report_group_names = {}
        try:
            page.show_comparison()
            page.open_table_button.menu().actions()[1].trigger()
            dialog = page._table_windows['confusion']
            self.assertIs(dialog.table.model(), page.confusion.model())
            self.assertFalse(dialog.isModal())
            self.assertEqual(dialog.windowType(), QtCore.Qt.WindowType.Window)
            self.assertTrue(dialog.windowFlags() & QtCore.Qt.WindowType.WindowTitleHint)
            expected = parent.screen().availableGeometry().center()
            self.assertLessEqual((dialog.frameGeometry().center() - expected).manhattanLength(), 4)
            embedded_width = page.confusion.columnWidth(0)
            dialog.table.setColumnWidth(0, embedded_width + 50)
            self.assertEqual(page.confusion.columnWidth(0), embedded_width)
            dialog.percent.setChecked(True)
            self.assertEqual(page.confusion.item(0, 2).text(), '100.0%')
            dialog.table.clicked.emit(dialog.table.model().index(0, 2))
            self.assertEqual(page._table_windows['errors'].table.model().rowCount(), 1)
            page.models.setCurrentIndex(page.models.findData('forest'))
            self.assertEqual(dialog.table.model().index(0, 1).data(), '100.0%')
        finally:
            for dialog in list(page._table_windows.values()):
                dialog.close()
            parent.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)

    def test_exported_rows_recover_the_historical_masks_only_when_values_agree(self):
        with tempfile.TemporaryDirectory(prefix='model_table_masks_') as folder:
            root = Path(folder)
            output = root / 'measurements/Data/Measurement_001'
            base = output / 'verification_masks'
            base.mkdir(parents=True)
            mask = base / 'mask.png'
            Image.new('L', (8, 8), 255).save(mask)
            entries = [dict(tile_name='tile', object_id=i, mask='mask.png') for i in (1, 2, 3)]
            atomic_json(base / 'object_locations.json', dict(schema_version=1, objects=entries))
            (output / 'features.csv').write_text(
                'Tile_Name,Object_ID,Area\ntile,1,1\ntile,2,20\ntile,3,3\n', encoding='utf-8')
            run = dict(dataset_id='id', summary={'csv_path': 'features.csv'})
            atomic_json(output / 'measurement_run.json', run)
            payload = self.payload()
            payload['snapshot']['datasets'][0]['measurement_reference'] = 'id:' + fingerprint(run)
            dialog = ModelSplitGallery(None, root, payload, _class_name)
            try:
                self.assertFalse(dialog.table_only)
                self.assertEqual(Path(dialog.image.filename), mask)
                self.assertEqual(set(dialog._table_paths), {0, 2})
                dialog.cards.navigate('next')
                self.assertFalse(dialog.image.filename)
                self.assertIn('No verified project measurement', dialog.image.caption.text())
            finally:
                dialog.close()
                self.app.processEvents()

    def test_crop_resolver_rejects_escaping_paths_and_ambiguous_legacy_names(self):
        with tempfile.TemporaryDirectory(prefix='model_gallery_paths_') as folder:
            root = Path(folder)
            base = root / 'saved/verification_masks'
            (base / 'tile').mkdir(parents=True)
            outside = root / 'another.png'
            Image.new('L', (8, 8), 255).save(outside)
            for name in ('obj_001_a.png', 'obj_001_b.png', 'obj_002_a.png'):
                Image.new('L', (8, 8), 64).save(base / 'tile' / name)
            atomic_json(base / 'object_locations.json', dict(schema_version=1, objects=[
                dict(tile_name='tile', object_id=1, mask='../../another.png')]))
            resolver = EvaluationCrops(root)
            self.assertEqual(resolver.resolve('saved', 'tile', 1), (None, None))
            self.assertEqual(resolver.resolve('saved', 'tile', 2), (base / 'tile' / 'obj_002_a.png', 'legacy'))
            self.assertEqual(resolver.resolve('saved', '../tile', 2), (None, None))

    def test_criterion_summary_uses_winner_and_each_criteria_best_score(self):
        result = dict(parameters=dict(criterion='entropy', max_depth=5),
                      tuning=[dict(parameters=dict(criterion=criterion), macro_f1=score)
                              for criterion, score in [('gini', .7), ('gini', .4), ('entropy', .8)]])
        summary = '\n'.join(ModelEvaluationPage._fit_summary('tree', result))
        self.assertIn('Split criterion — Entropy', summary)
        self.assertIn('Gini — 0.700000', summary)
        self.assertIn('Entropy — 0.800000', summary)
