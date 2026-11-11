"""Checks for coordinate-scale measurement and validated personal defaults."""

import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PIL import Image

from src.default_settings import FACTORY_DEFAULTS
from src.desktop.editor_preferences import read_profile, write_profile
from src.desktop.i18n import set_language
from src.desktop.image_ruler import measurement_ruler_scale
from src.desktop.project import atomic_json
from src.desktop.qt import QtCore, QtWidgets
from src.desktop.settings_dialog import SettingsDialog
from src.desktop.widgets import ImageViewer, image_pool

try:
    from PyQt6.QtTest import QTest
except ImportError:
    from PySide6.QtTest import QTest


class RulerSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        set_language('en')
        self.temp = tempfile.TemporaryDirectory(prefix='ruler_settings_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _close_widget(self, widget):
        widget.close()
        widget.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_calibrated_ruler_survives_zoom_and_clears_with_escape(self):
        path = self.root / 'sample.png'
        Image.new('L', (120, 100), 64).save(path)
        viewer = ImageViewer()
        viewer.resize(480, 380)
        viewer.show()
        self.addCleanup(self._close_widget, viewer)
        viewer.set_image(path, ruler_scale=(2, 2, .4))
        self.assertTrue(image_pool().waitForDone(5000))
        self.app.processEvents()
        self.assertTrue(viewer.ruler_button.isEnabled())
        viewer.actual_size()
        viewer.ruler_button.click()
        start = viewer.view.mapFromScene(QtCore.QPointF(20, 20))
        end = viewer.view.mapFromScene(QtCore.QPointF(35, 40))
        left = QtCore.Qt.MouseButton.LeftButton
        QTest.mousePress(viewer.view.viewport(), left, pos=start)
        QTest.mouseMove(viewer.view.viewport(), end)
        QTest.mouseRelease(viewer.view.viewport(), left, pos=end)
        self.assertEqual(viewer.ruler.text(), '50.00 source px · 20 µm')
        viewer.zoom(1.3)
        self.assertEqual(viewer.ruler.text(), '50.00 source px · 20 µm')
        QTest.keyClick(viewer.view, QtCore.Qt.Key.Key_Escape)
        self.assertIsNone(viewer.ruler.line)
        fullscreen = viewer.open_fullscreen()
        fullscreen.close()
        self.app.processEvents()
        viewer.clear()
        self.assertFalse(viewer.ruler_button.isEnabled())

    def test_original_object_window_uses_frozen_measurement_calibration(self):
        path = self.root / 'object.png'
        Image.new('L', (120, 100), 64).save(path)
        atomic_json(self.root / 'measurement_run.json', dict(
            calibration={'pixel_size_um': .4}, summary={'measurement_space': 'source_pixels'}))
        self.assertIsNone(measurement_ruler_scale(self.root, 'tile_pixels'))
        scale = measurement_ruler_scale(self.root)
        dialog = ImageViewer.open_image_window(path, original=True, ruler_scale=scale)
        self.addCleanup(self._close_widget, dialog)
        self.assertTrue(image_pool().waitForDone(5000))
        self.app.processEvents()
        viewer = dialog.viewer
        viewer.actual_size()
        viewer.ruler_button.click()
        start, end = [viewer.view.mapFromScene(QtCore.QPointF(x, y)) for x, y in ((10, 10), (40, 50))]
        left = QtCore.Qt.MouseButton.LeftButton
        QTest.mousePress(viewer.view.viewport(), left, pos=start)
        QTest.mouseMove(viewer.view.viewport(), end)
        QTest.mouseRelease(viewer.view.viewport(), left, pos=end)
        self.assertEqual(viewer.ruler.text(), '50.00 source px · 20 µm')

    def test_settings_validate_hidden_pipeline_keys_and_keep_factory_immutable(self):
        prefs = QtCore.QSettings(str(self.root / 'settings.ini'), QtCore.QSettings.Format.IniFormat)
        profile = read_profile(prefs)
        dialog = SettingsDialog(None, dict(FACTORY_DEFAULTS), 'auto', profile)
        self.addCleanup(self._close_widget, dialog)
        self.assertTrue(dialog.ok.isEnabled())
        self.assertEqual(set(dialog.result_values['processing']), set(FACTORY_DEFAULTS))
        dialog._rows['processing']['bilateral_sigma_color'][-1].setText('25,5')
        dialog._rows['processing']['animation_max_trial_frames'][-1].setText('0')
        self.assertFalse(dialog.ok.isEnabled())
        dialog._rows['processing']['animation_max_trial_frames'][-1].setText('30')
        dialog._rows['mask']['brush_width'][-1].setText('8')
        self.assertFalse(dialog.ok.isEnabled())
        dialog._rows['mask']['brush_width'][-1].setText('9')
        self.assertTrue(dialog.ok.isEnabled())
        write_profile(prefs, dialog.result_values)
        self.assertEqual(read_profile(prefs)['processing']['bilateral_sigma_color'], 25.5)
        self.assertEqual(read_profile(prefs)['mask']['brush_width'], 9)
        self.assertEqual(FACTORY_DEFAULTS['bilateral_sigma_color'], 45)
