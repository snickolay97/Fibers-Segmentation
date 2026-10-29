"""Complete the user's manual-target workflow through actual Qt controls."""
import csv
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from src.desktop.qt import QtCore, QtWidgets
from src.desktop.main_window import MainWindow
from src.desktop.project import Project
from src.desktop.widgets import image_pool
from src.desktop import service
from src.desktop.object_labels import CANONICAL_MANUAL_CLASSES


class ManualWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def pump(self, predicate, timeout=30):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(.01)
        self.fail('Timed out waiting for the desktop worker')

    def run_job(self, window, action, **kwargs):
        self.assertTrue(window.start_job(action, **kwargs))
        self.pump(lambda: window.process is None)
        self.assertIsNone(window._job_error, window.log.toPlainText())
        self.assertEqual(window._job_result['status'], 'completed', window.log.toPlainText())

    def test_prepare_assign_six_classes_export_and_reopen_in_three_languages(self):
        import cv2
        import numpy as np
        import tifffile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = Project.create(root / 'project.json', 'Object review')
            pixels = np.zeros((220, 260, 3), dtype=np.uint8)
            for y in (40, 110, 180):
                for x in (40, 120, 200):
                    cv2.circle(pixels, (x, y), 8, (230, 0, 0), -1)
            source = root / 'objects.tif'
            tifffile.imwrite(source, pixels, photometric='rgb', metadata={'axes': 'YXS'})
            service.add_sources(project, [source])
            preferences = QtCore.QSettings(str(root / 'preferences.ini'), QtCore.QSettings.Format.IniFormat)
            window = MainWindow(project, preferences=preferences)
            try:
                self.assertEqual(window.language, 'en')
                self.assertFalse(window.dataset_combo.isEnabled())
                settings = window.collect_settings()
                settings.update(target_size=128, overview_size=300, tophat_radius=8,
                                bilateral_d=3, bridge_kernel_size=3, buffer_kernel_size=3,
                                pixel_size_um=.42)
                window.set_language('he')
                self.run_job(window, 'prepare', source_ids=[project.sources[0]['id']], settings=settings)
                self.assertEqual(window.build_request('preview')['language'], 'he')
                dataset = window.selected_dataset()
                self.assertTrue(window.dataset_combo.isEnabled())
                first_dataset_id = dataset['id']
                self.run_job(window, 'extract', dataset_id=dataset['id'], labels_mode='auto', settings=settings)
                window.set_language('en')
                dataset = window.selected_dataset()
                source_csv = Path(dataset['last_csv'])
                before = source_csv.read_bytes()
                self.assertGreaterEqual(len(window.results_table.rows), 6)
                window.results_table.table.selectRow(0)
                for expected, definition in enumerate(CANONICAL_MANUAL_CLASSES, 1):
                    combo = window.classifier.class_combo
                    combo.setCurrentIndex(combo.findData(definition['key']))
                    window.classifier.save_next_button.click()
                    self.assertEqual(service.get_object_labels(window.selected_dataset())['assigned'], expected)
                self.assertEqual(source_csv.read_bytes(), before)

                destination = root / 'training.csv'
                with patch.object(QtWidgets.QFileDialog, 'getSaveFileName', return_value=(str(destination), 'CSV (*.csv)')):
                    window.classifier.export_button.click()
                self.assertTrue(destination.is_file())
                with destination.open(encoding='utf-8', newline='') as handle:
                    reader = csv.DictReader(handle)
                    rows = list(reader)
                    self.assertIn('Class_ID', reader.fieldnames)
                    self.assertIn('Class_Name', reader.fieldnames)
                self.assertEqual(len(rows), 6)
                self.assertEqual({row['Manual_Class'] for row in rows}, {item['key'] for item in CANONICAL_MANUAL_CLASSES})
                self.assertEqual({row['Manual_Class_ID'] for row in rows}, set(map(str, range(6))))
                self.assertEqual({row['Class_ID'] for row in rows}, {'-1'})
                self.assertEqual({row['Class_Name'] for row in rows}, {'Unknown'})
                self.assertEqual({row['Class_Catalog_Version'] for row in rows}, {'2'})
                expected_ids = {item['key']: str(item['id']) for item in CANONICAL_MANUAL_CLASSES}
                for row in rows:
                    self.assertEqual(row['Manual_Class_ID'], expected_ids[row['Manual_Class']])

                chosen = window.results_table.selected_row()
                window.set_language('ru')
                self.assertEqual(window.page_title.text(), 'Результаты')
                self.assertEqual(window.results_table.selected_row()['Object_ID'], chosen['Object_ID'])
                self.assertEqual(service.get_object_labels(window.selected_dataset())['assigned'], 6)
                self.assertEqual(preferences.value('language'), 'ru')
                window.set_language('en')
                self.assertEqual(window.page_title.text(), 'Results')

                # A second preparation version must be selectable and distinguishable.
                settings['gamma'] = 1.3
                self.run_job(window, 'prepare', source_ids=[project.sources[0]['id']], settings=settings)
                self.assertEqual(window.dataset_combo.count(), 2)
                self.assertNotEqual(window.dataset_combo.itemText(0), window.dataset_combo.itemText(1))
                window.dataset_combo.setCurrentIndex(window.dataset_combo.findData(first_dataset_id))
                self.assertEqual(window.project.active_dataset_id, first_dataset_id)
                self.assertEqual(service.get_object_labels(window.selected_dataset())['assigned'], 6)
                window.set_language('ru')
            finally:
                if window.process is not None:
                    window.process.kill()
                    window.process.waitForFinished(5000)
                    self.app.processEvents()
                window.close()
                image_pool().waitForDone(5000)
                self.app.processEvents()

            reopened = MainWindow(Project.load(project.path), preferences=preferences)
            try:
                self.assertEqual(reopened.language, 'ru')
                self.assertEqual(reopened.selected_dataset()['id'], first_dataset_id)
                self.assertEqual(service.get_object_labels(reopened.selected_dataset())['assigned'], 6)
                self.assertEqual(source_csv.read_bytes(), before)
            finally:
                reopened.close()
                image_pool().waitForDone(5000)
                self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
