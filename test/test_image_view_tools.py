"""Regression checks for viewing levels, overlays, exports and measuring paths."""

from io import BytesIO
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from src.desktop.i18n import set_language
from src.desktop.image_comparison import ImageComparisonWindow, add_comparison
from src.desktop.image_export import write_image_copy
from src.desktop.image_levels import image_samples
from src.desktop.qt import BINDING, QtCore, QtGui, QtWidgets
from src.desktop.widgets import ImageViewer, image_pool

if BINDING == 'PySide6':
    from PySide6.QtTest import QTest
else:
    from PyQt6.QtTest import QTest


class ImageViewToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        set_language('en')
        self.viewer = ImageViewer(maximum=None)
        self.viewer.resize(640, 480)
        self.viewer.show()

    def tearDown(self):
        self.viewer.close()
        self.viewer.deleteLater()
        image_pool().waitForDone(5000)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_display_window_uses_low_bits_and_resets_to_original(self):
        raw = np.array([[400, 450, 500], [0, 2048, 65535]], dtype=np.uint16)
        self.viewer.set_grayscale_pixels(raw, '16-bit fixture')
        self.assertEqual(self.viewer.export_frame().pixelColor(1, 0).red(), 1)
        self.viewer.levels_button.click()
        dialog = self.viewer._levels_dialog
        self.assertEqual(dialog.maximum, 65535)
        dialog.black.setValue(400)
        dialog.white.setValue(500)
        QTest.qWait(80)
        self.assertEqual([self.viewer.export_frame().pixelColor(x, 0).red() for x in range(3)], [0, 128, 255])
        np.testing.assert_array_equal(image_samples(self.viewer._base_image), raw)
        dialog.reset.click()
        QTest.qWait(80)
        self.assertEqual(self.viewer.export_frame().pixelColor(1, 0).red(), 1)
        dialog.close()

    def test_overlay_blends_same_grid_and_releases_embedded_views(self):
        tabs = QtWidgets.QTabWidget(self.viewer)
        first, second = ImageViewer(), ImageViewer()
        tabs.addTab(first, 'First')
        tabs.addTab(second, 'Second')
        splitter = add_comparison(tabs, 0, 1, 'image_comparison')
        tabs.setCurrentIndex(2)
        first.set_grayscale_pixels(np.full((20, 22), 40, np.uint8), 'first')
        second.set_grayscale_pixels(np.full((20, 22), 200, np.uint8), 'second')
        tabs.cornerWidget().click()
        dialog = tabs.findChild(ImageComparisonWindow)
        self.assertIsNotNone(dialog)
        self.assertTrue(dialog.isAncestorOf(first))
        self.assertTrue(dialog.overlay_button.isEnabled())
        dialog.overlay_button.click()
        for opacity, expected in ((0, 40), (50, 120), (100, 200)):
            dialog.opacity.setValue(opacity)
            self.assertLessEqual(abs(dialog.overlay_view.export_frame().pixelColor(9, 9).red() - expected), 1)
        second.set_grayscale_pixels(np.zeros((20, 24), np.uint8), 'different grid')
        self.assertFalse(dialog.overlay_button.isEnabled())
        self.assertFalse(dialog.overlay_button.isChecked())
        tabs.setCurrentIndex(1)
        self.assertTrue(tabs.widget(1).isAncestorOf(second))
        self.assertIsNone(second._host_window)
        tabs.setCurrentIndex(2)
        self.assertTrue(splitter.isAncestorOf(first))
        self.assertTrue(splitter.isAncestorOf(second))

    def test_polyline_tracks_pointer_measures_committed_segments_and_styles_individually(self):
        self.viewer.set_grayscale_pixels(np.zeros((180, 220), np.uint8), 'ruler',
                                         ruler_scale=(2, 1, .5))
        self.viewer.actual_size()
        self.app.processEvents()
        self.viewer.ruler_button.actions_by_key['Polyline ruler'].trigger()
        view = self.viewer.view
        viewport = view.viewport()
        left = QtCore.Qt.MouseButton.LeftButton
        pos = lambda x, y: view.mapFromScene(QtCore.QPointF(x, y))
        ruler = self.viewer.ruler
        QTest.mouseClick(viewport, left, pos=pos(20, 20))
        QTest.mouseMove(viewport, pos(60, 20))
        self.assertEqual(ruler._preview.line().p2(), QtCore.QPointF(60, 20))
        self.assertEqual(ruler.segments, [])
        QTest.mouseClick(viewport, left, pos=pos(60, 20))
        QTest.mouseDClick(viewport, left, pos=pos(60, 60))
        self.assertFalse(ruler.building)
        self.assertEqual(len(ruler.segments), 2)
        self.assertIn('120.00 source px · 60 µm', ruler.text())
        with patch('src.desktop.image_ruler.choose_line_color', return_value=QtGui.QColor('#32aadd')):
            ruler.change_color(self.viewer, ruler.segments[1])
        with patch('src.desktop.image_ruler.choose_line_width', return_value=6):
            ruler.change_width(self.viewer)
        self.assertEqual([item.pen().color().name() for item in ruler.segments], ['#ffce55', '#32aadd'])
        self.assertTrue(all(item.pen().width() == 6 and item.pen().isCosmetic() for item in ruler.segments))
        QTest.keyClick(view, QtCore.Qt.Key.Key_Escape)
        self.assertFalse(ruler.segments)

    def test_contour_hover_and_resize_keep_buttons_and_icons_available(self):
        self.viewer.set_grayscale_pixels(np.zeros((180, 220), np.uint8), 'polygon')
        self.viewer.actual_size()
        self.app.processEvents()
        small_height = self.viewer.fit_button.height()
        self.viewer.resize(1220, 760)
        self.app.processEvents()
        self.assertGreater(self.viewer.fit_button.height(), small_height)
        self.assertFalse(self.viewer.polygon_button.icon().isNull())
        self.viewer.polygon_button.click()
        view = self.viewer.view
        pos = lambda x, y: view.mapFromScene(QtCore.QPointF(x, y))
        viewport = view.viewport()
        left = QtCore.Qt.MouseButton.LeftButton
        QTest.mouseClick(viewport, left, pos=pos(20, 20))
        QTest.mouseMove(viewport, pos(80, 20))
        contour = self.viewer.polygon
        self.assertEqual(contour._hover_line.line().p2(), QtCore.QPointF(80, 20))
        self.assertEqual(len(contour.points), 1)
        QTest.mouseClick(viewport, left, pos=pos(80, 20))
        QTest.mouseDClick(viewport, left, pos=pos(80, 85))
        self.assertTrue(contour.closed)
        self.assertIsNone(contour._hover_line)
        with patch('src.desktop.image_polygon.choose_line_width', return_value=7):
            contour.change_width(self.viewer)
        self.assertEqual(contour._outline.pen().width(), 7)

    def test_export_formats_keep_saved_grayscale_depth_and_refuse_source_replacement(self):
        raw = np.array([[1, 256, 4000], [50, 500, 65535]], dtype=np.uint16)
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source, png, copy = (base / name for name in ('source.tiff', 'out.png', 'copy.tif'))
            Image.fromarray(raw).save(source)
            write_image_copy(png, source=source)
            write_image_copy(copy, source=source)
            self.assertEqual(copy.read_bytes(), source.read_bytes())
            with Image.open(png) as image:
                np.testing.assert_array_equal(np.asarray(image), raw)
            with self.assertRaises(ValueError):
                write_image_copy(source, source=source)
            self.viewer.set_grayscale_pixels(raw, 'fixture')
            self.viewer.set_display_levels((0, 4000))
            for extension, name in (('tif', 'TIFF'), ('png', 'PNG'), ('jpg', 'JPEG')):
                destination = base / f'visible.{extension}'
                write_image_copy(destination, frame=self.viewer.export_frame())
                with Image.open(destination) as image:
                    self.assertEqual(image.format, name)
                    self.assertEqual(image.size, (3, 2))

    def test_compare_with_file_and_export_overlay_from_toolbar(self):
        self.viewer.set_grayscale_pixels(np.full((15, 18), 40, np.uint8), 'Current view')
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'compare.png'
            Image.new('L', (18, 15), 200).save(source)
            with patch.object(QtWidgets.QFileDialog, 'getOpenFileName', return_value=(str(source), '')):
                self.viewer.compare_file_button.click()
            dialog = self.viewer._comparison_window
            try:
                self.assertTrue(image_pool().waitForDone(5000))
                self.app.processEvents()
                self.assertTrue(dialog.overlay_button.isEnabled())
                dialog.overlay_button.click()
                dialog.opacity.setValue(25)
                destination = Path(folder) / 'blend'
                with patch.object(QtWidgets.QFileDialog, 'getSaveFileName',
                                  return_value=(str(destination), 'TIFF (*.tif *.tiff)')):
                    dialog.overlay_view.save_displayed_action.trigger()
                self.assertTrue(image_pool().waitForDone(5000))
                self.app.processEvents()
                with Image.open(BytesIO(destination.with_suffix('.tif').read_bytes())) as image:
                    self.assertEqual(image.size, (18, 15))
                    self.assertLessEqual(abs(image.convert('RGB').getpixel((9, 7))[0] - 80), 1)
                dialog.overlay_view.levels_button.click()
                self.assertIsNotNone(dialog.overlay_view._levels_dialog)
            finally:
                dialog.close()
            self.assertIsNone(self.viewer._comparison_window)


if __name__ == '__main__':
    unittest.main()
