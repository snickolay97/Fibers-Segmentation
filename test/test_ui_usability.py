"""Review real worker outputs through the movable desktop workspace."""
import os
from pathlib import Path
import tempfile
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from src.desktop.qt import QtCore, QtGui, QtWidgets
from src.desktop.main_window import MainWindow
from src.desktop.project import Project
from src.desktop.widgets import image_pool
from src.desktop import service


class UsabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.preferences = QtCore.QSettings(str(self.root / 'preferences.ini'), QtCore.QSettings.Format.IniFormat)
        self.project = Project.create(self.root / 'project.json', 'Synthetic UI verification')
        self.window = MainWindow(self.project, preferences=self.preferences)

    def tearDown(self):
        if self.window.process is not None:
            self.window.process.kill()
            self.window.process.waitForFinished(5000)
        self.window.close()
        image_pool().waitForDone(5000)
        self.app.processEvents()
        self.temporary.cleanup()

    def pump(self, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(.01)
        self.fail('Desktop verification timed out')

    def test_disabled_filter_parameters_keep_their_values_after_busy_and_language_change(self):
        self.window._settings_fields['gamma'].setValue(1.7)
        self.window._settings_fields['enable_gamma'].setChecked(False)
        self.assertFalse(self.window._settings_fields['gamma'].isEnabled())
        self.window._set_busy(True)
        self.window._set_busy(False)
        self.assertFalse(self.window._settings_fields['gamma'].isEnabled())
        self.assertEqual(self.window.collect_settings()['gamma'], 1.7)
        self.window.set_language('ru')
        self.assertFalse(self.window.collect_settings()['enable_gamma'])
        self.assertFalse(self.window._settings_fields['gamma'].isEnabled())
        self.window._settings_fields['enable_gamma'].setChecked(True)
        self.assertTrue(self.window._settings_fields['gamma'].isEnabled())
        self.assertEqual(self.window.collect_settings()['gamma'], 1.7)

    def test_old_project_without_filter_switches_uses_defaults_when_switched(self):
        for key in self.window._filter_parameter_groups:
            self.window._settings_fields[key].setChecked(False)
        legacy = Project.create(self.root / 'old' / 'project.json')
        legacy.settings = {key:value for key, value in legacy.settings.items() if not key.startswith('enable_') or key == 'enable_animations'}
        legacy.save()
        self.window._switch_project(legacy)
        for key in self.window._filter_parameter_groups:
            self.assertTrue(self.window.collect_settings()[key], key)

    def test_language_change_keeps_loaded_previews_and_active_preview_tab(self):
        filename = self.root / 'preview.png'
        image = QtGui.QImage(64, 48, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtGui.QColor('#667788'))
        self.assertTrue(image.save(str(filename)))
        self.window.input_preview.set_image(filename)
        self.window.filtered_preview.set_image(filename)
        self.pump(lambda: self.window.filtered_preview.original_size == (64, 48))
        self.window.preview_tabs.setCurrentIndex(1)
        self.window.set_language('ru')
        self.assertEqual(self.window.preview_tabs.currentIndex(), 1)
        self.assertEqual(self.window.input_preview.filename, str(filename))
        self.assertEqual(self.window.filtered_preview.filename, str(filename))
        self.pump(lambda: self.window.input_preview.original_size == (64, 48)
                  and self.window.filtered_preview.original_size == (64, 48))

    def test_detection_gallery_quick_classes_and_floating_panel_survive_reopen(self):
        import cv2
        import numpy as np
        import tifffile
        image = np.zeros((220, 260), np.uint8)
        for y in (40, 110, 180):
            for x in (40, 120, 200):
                cv2.circle(image, (x, y), 8, 230, -1)
        path = self.root / 'synthetic.tif'
        tifffile.imwrite(path, image, metadata={'axes':'YX'})
        original = path.read_bytes()
        service.add_sources(self.project, [path])
        self.window.refresh_project()
        self.window.show()
        self.window.show_log.setChecked(False)
        for key, value in dict(target_size=128, overview_size=300, tophat_radius=8,
                               bilateral_d=3, bridge_kernel_size=3, buffer_kernel_size=3).items():
            self.window._settings_fields[key].setValue(value)
        self.window._settings_fields['enable_gamma'].setChecked(False)
        self.assertTrue(self.window.start_job('prepare', source_ids=[self.project.sources[0]['id']],
                                             settings=self.window.collect_settings()))
        self.pump(lambda: self.window.process is None)
        self.assertIsNone(self.window._job_error)
        self.window.sidebar.setCurrentRow(3)
        self.window.detect_objects_button.click()
        self.pump(lambda: self.window.process is None)
        self.assertIsNone(self.window._job_error)
        self.assertEqual(self.window.sidebar.currentRow(), 4)
        self.assertEqual(self.window.labels_mode.currentData(), 'auto')
        gallery = self.window.object_gallery
        self.assertGreaterEqual(len(gallery.visible_rows), 6)
        target = gallery.visible_rows[-2]
        gallery.select_object(target['Tile_Name'], target['Object_ID'])
        self.assertEqual(self.window.results_table.selected_row()['Tile_Name'], target['Tile_Name'])
        science = Path(self.window.selected_dataset()['last_csv'])
        before = science.read_bytes()
        self.window.classifier.class_buttons['fiber'].click()
        report = service.get_object_labels(self.window.selected_dataset())
        key = target['Tile_Name'] + '/' + str(target['Object_ID'])
        self.assertEqual(report['labels'][key]['Manual_Class'], 'fiber')
        gallery.unclassified_only.setChecked(True)
        first = gallery.visible_rows[0]
        gallery.select_object(first['Tile_Name'], first['Object_ID'])
        self.window.classifier.class_buttons['particle'].click()
        self.assertEqual(len(service.get_object_labels(self.window.selected_dataset())['labels']), 2)
        selected = gallery.selected_row()
        self.assertNotEqual((selected['Tile_Name'], selected['Object_ID']),
                            (first['Tile_Name'], first['Object_ID']))
        self.assertEqual(science.read_bytes(), before)
        self.assertEqual(path.read_bytes(), original)
        self.window.review_tabs.setCurrentIndex(1)
        self.window.results_table.select_object(target['Tile_Name'], target['Object_ID'])
        self.window.review_tabs.setCurrentIndex(0)
        shown = gallery.selected_row()
        self.assertEqual(self.window.results_table.selected_row()['Object_ID'], shown['Object_ID'])
        self.assertEqual(self.window.results_table.selected_row()['Tile_Name'], shown['Tile_Name'])
        # Finishing the last unclassified object must clear the target so an
        # extra class key cannot accidentally change the previous object.
        total_objects = len(self.window.results_table.rows)
        for _ in range(total_objects):
            if not gallery.visible_rows:
                break
            self.window.classifier.class_buttons['particle'].click()
        self.assertEqual(gallery.visible_rows, [])
        self.assertIsNone(gallery.selected_row())
        self.assertIsNone(self.window.results_table.selected_row())
        self.assertTrue(all(not button.isEnabled() for button in self.window.classifier.class_buttons.values()))
        self.assertEqual(science.read_bytes(), before)
        dock = self.window._workspaces['results'].panels['preview']
        dock.setFloating(True)
        self.app.processEvents()
        self.assertTrue(dock.isVisible())
        self.window.sidebar.setCurrentRow(1)
        self.assertTrue(dock.isHidden())
        self.window.sidebar.setCurrentRow(4)
        self.assertTrue(dock.isVisible())
        self.window.set_language('ru')
        self.assertTrue(self.window.object_gallery.unclassified_only.isChecked())
        self.assertTrue(self.window._workspaces['results'].panels['preview'].isFloating())
        project_path = self.window.project.path
        self.window.close()
        image_pool().waitForDone(5000)
        self.app.processEvents()
        self.window = MainWindow(Project.load(project_path), preferences=self.preferences)
        self.window.show()
        self.window.sidebar.setCurrentRow(4)
        self.app.processEvents()
        self.assertTrue(self.window._workspaces['results'].panels['preview'].isFloating())
        self.assertEqual(service.get_object_labels(self.window.selected_dataset())['assigned'], total_objects)
        self.assertFalse(self.window.collect_settings()['enable_gamma'])


if __name__ == '__main__':
    unittest.main()
