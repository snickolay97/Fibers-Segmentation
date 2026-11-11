"""Detailed overview requests reach their native image window on completion."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from src.desktop.qt import QtCore, QtWidgets, BINDING
if BINDING == 'PyQt6':
    from PyQt6 import QtTest
else:
    from PySide6 import QtTest
from src.desktop.project import Project
from src.desktop.main_window import MainWindow
from src.desktop.widgets import ImageViewer, image_pool


class DetailedMapUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        project = Project.create(self.root / 'project.json')
        preferences = QtCore.QSettings(str(self.root / 'preferences.ini'), QtCore.QSettings.Format.IniFormat)
        self.window = MainWindow(project, language='en', preferences=preferences)

    def tearDown(self):
        self.window.close()
        image_pool().waitForDone(5000)
        self.window.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.temporary.cleanup()

    def test_detailed_map_button_dispatches_full_resolution_request(self):
        with patch.object(self.window, '_require_dataset', return_value=dict(id='selected-dataset')), \
             patch.object(self.window, 'start_job', return_value=True) as start:
            self.window.detailed_map_button.click()
            start.assert_called_once_with('overview', dataset_id='selected-dataset', full_resolution=True)

    def test_automatic_interface_scale_enlarges_text_and_fixed_setting_overrides_it(self):
        self.window.resize(1300, 850)
        self.window._update_interface_scale()
        baseline = self.window.save_button.fontMetrics().height()
        self.window.resize(3000, 1800)
        self.window._update_interface_scale()
        self.assertGreater(self.window.save_button.fontMetrics().height(), baseline)
        self.assertEqual(self.window._ui_scale, 1.8)
        self.window.preferences.setValue('appearance/scale', '100')
        self.window._update_interface_scale()
        self.assertEqual(self.window.save_button.fontMetrics().height(), baseline)

    def test_preparation_composite_controls_update_and_export(self):
        import numpy as np
        import tifffile
        from src.desktop import service
        from src.desktop.channel_composite_dialog import ChannelCompositeDialog, _POOL

        filename = self.root / 'rgb.tif'
        pixels = np.full((12, 15, 3), 200, np.uint8)
        tifffile.imwrite(filename, pixels, photometric='rgb')
        service.add_sources(self.window.project, [filename])
        self.window.refresh_project()
        self.window.sidebar.setCurrentRow(1)
        self.window.combine_channels_button.click()
        dialog = self.window.findChild(ChannelCompositeDialog)
        self.assertIsNotNone(dialog)
        self.addCleanup(lambda: _POOL.waitForDone(5000))
        try:
            dialog._layers[0][2].setValue(50)
            dialog._layers[1][3].setValue(25)
            dialog._layers[2][0].setChecked(False)
            dialog._timer.stop()
            dialog._preview()
            self.assertTrue(_POOL.waitForDone(5000))
            self.app.processEvents()
            self.assertEqual(dialog.viewer.export_frame().pixelColor(3, 4).getRgb()[:3], (100, 50, 0))
            target = self.root / 'composite.tif'
            with patch.object(QtWidgets.QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
                dialog.save.click()
            self.assertTrue(_POOL.waitForDone(5000))
            self.app.processEvents()
            output = tifffile.imread(target)
            self.assertEqual(output.shape, pixels.shape)
            self.assertEqual(tuple(output[4, 3]), (100, 50, 0))
        finally:
            dialog.close()

    def test_filtering_resolution_requests_worker_and_opens_native_region(self):
        import numpy as np
        import tifffile
        from src.desktop import service
        from src.desktop.source_viewer import SourceViewer

        filename = self.root / 'gray.tif'
        tifffile.imwrite(filename, np.full((25, 2510), 140, np.uint8))
        service.add_sources(self.window.project, [filename])
        self.window.refresh_project()
        self.window.sidebar.setCurrentRow(1)
        self.window.preview_tabs.setCurrentIndex(1)
        self.window.preparation_resolution.click()
        self.assertIsNotNone(self.window.process)
        deadline = time.monotonic() + 15
        dialog = None
        while time.monotonic() < deadline:
            self.app.processEvents()
            dialog = self.window.findChild(SourceViewer)
            if dialog and dialog._patch_image is not None:
                break
            time.sleep(.01)
        self.assertIsNone(self.window._job_error)
        self.assertIsNotNone(dialog)
        try:
            self.assertEqual(dialog.detail.original_size, (2510, 25))
            self.assertFalse(dialog.detail._pixmap_item.isVisible())
            view = dialog.detail.view
            device_transform = dialog._patch.deviceTransform(view.viewportTransform())
            self.assertAlmostEqual(device_transform.m11() * view.devicePixelRatioF(), 1)
            self.assertAlmostEqual(device_transform.m22() * view.devicePixelRatioF(), 1)
            self.assertEqual(tifffile.imread(dialog.filename).shape, (25, 2510))
            sx, sy = dialog._source_factors()
            dialog._select_region(2509 / sx, 12 / sy)
            until = time.monotonic() + 5
            while dialog._patch_bounds[2] != 2510 and time.monotonic() < until:
                self.app.processEvents()
                time.sleep(.01)
            self.assertEqual(dialog._patch_bounds[2], 2510)
            x0, y0, x1, y1 = dialog._export_bounds
            exported = dialog.detail.export_frame()
            self.assertEqual((exported.width(), exported.height()), (x1-x0, y1-y0))
        finally:
            dialog.close()

    def test_vertical_divider_gives_image_more_height_and_survives_language_change(self):
        self.window.resize(1250, 900)
        self.window.show_log.setChecked(False)
        self.window.show()
        self.window.sidebar.setCurrentRow(2)
        self.app.processEvents()
        splitter = self.window.tile_splitter
        splitter.setSizes([450, 220])
        self.app.processEvents()
        before = splitter.sizes()[0]
        handle = splitter.handle(1)
        point = handle.rect().center()
        QtTest.QTest.mousePress(handle, QtCore.Qt.MouseButton.LeftButton, pos=point)
        QtTest.QTest.mouseMove(handle, point + QtCore.QPoint(0, 55), 30)
        QtTest.QTest.mouseRelease(handle, QtCore.Qt.MouseButton.LeftButton, pos=point + QtCore.QPoint(0, 55))
        self.app.processEvents()
        self.assertGreater(splitter.sizes()[0], before)
        height = splitter.sizes()[0]
        self.window.set_language('ru')
        self.app.processEvents()
        self.assertAlmostEqual(self.window.tile_splitter.sizes()[0], height, delta=25)

    def test_numeric_plus_minus_buttons_preserve_steps_and_limits(self):
        self.window.calibration_mode_combo.setCurrentIndex(self.window.calibration_mode_combo.findData('manual'))
        self.window.show()
        self.window.sidebar.setCurrentRow(1)
        self.app.processEvents()
        scroll = self.window._workspaces['preparation'].panels['settings'].widget()
        for key in ('target_size', 'gamma', 'bridge_kernel_size', 'pixel_size_um'):
            field = self.window._settings_fields[key]
            self.assertEqual(field.buttonSymbols(), QtWidgets.QAbstractSpinBox.ButtonSymbols.PlusMinus)
            scroll.ensureWidgetVisible(field)
            self.app.processEvents()
            before = field.value()
            option = QtWidgets.QStyleOptionSpinBox()
            field.initStyleOption(option)
            for control, expected in ((QtWidgets.QStyle.SubControl.SC_SpinBoxUp, before + field.singleStep()),
                                      (QtWidgets.QStyle.SubControl.SC_SpinBoxDown, before)):
                rect = field.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_SpinBox, option, control, field)
                QtTest.QTest.mouseClick(field, QtCore.Qt.MouseButton.LeftButton, pos=rect.center())
                self.assertAlmostEqual(field.value(), expected, places=6, msg=key)

    def test_new_project_creates_an_independent_named_folder(self):
        original = Path(self.window.project.path)
        with patch.object(QtWidgets.QInputDialog, 'getText', return_value=('Study A', True)), \
             patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=str(self.root)):
            self.window.new_project()
        self.assertEqual(Path(self.window.project.path), self.root / 'Study A' / 'project.json')
        self.assertEqual(Path(self.window.project.workspace), self.root / 'Study A')
        self.assertTrue(original.is_file())
        self.assertEqual(self.window.project.sources, [])
        self.assertEqual(self.window.project.datasets, [])

    def test_new_project_never_claims_an_existing_folder(self):
        existing = self.root / 'Existing'
        existing.mkdir()
        sentinel = existing / 'unrelated.txt'
        sentinel.write_bytes(b'owner data')
        original = self.window.project.path
        with patch.object(QtWidgets.QInputDialog, 'getText', return_value=('Existing', True)), \
             patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=str(self.root)), \
             patch.object(self.window, '_error') as error:
            self.window.new_project()
        error.assert_called_once()
        self.assertEqual(self.window.project.path, original)
        self.assertEqual(sentinel.read_bytes(), b'owner data')
        self.assertFalse((existing / 'project.json').exists())

    def test_completed_detailed_map_opens_saved_image_at_original_resolution(self):
        filename = str(self.root / 'native_map.png')
        self.window.process = QtCore.QProcess(self.window)
        self.window._job_action = 'overview'
        self.window._job_result = dict(type='result', status='completed',
                                      summary=dict(full_resolution=True, path=filename))
        with patch.object(ImageViewer, 'open_image_window', return_value=None) as opened:
            self.window._process_finished(0, QtCore.QProcess.ExitStatus.NormalExit)
        self.assertIsNone(self.window.process)
        self.assertEqual(self.window.sidebar.currentRow(), 2)
        self.assertEqual(opened.call_args.args[0], filename)
        self.assertTrue(opened.call_args.kwargs['original'])

    def test_regular_map_refresh_keeps_working_in_tiles_without_an_extra_window(self):
        self.window.process = QtCore.QProcess(self.window)
        self.window._job_action = 'overview'
        self.window._job_result = dict(type='result', status='completed',
                                      summary=dict(full_resolution=False, path='preview_map.png'))
        with patch.object(ImageViewer, 'open_image_window') as opened:
            self.window._process_finished(0, QtCore.QProcess.ExitStatus.NormalExit)
        self.assertEqual(self.window.sidebar.currentRow(), 2)
        opened.assert_not_called()


if __name__ == '__main__':
    unittest.main()
