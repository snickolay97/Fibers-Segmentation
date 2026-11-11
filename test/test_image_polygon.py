"""Check contour measurements and their use in the image viewer."""

import math
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np

from src.desktop.i18n import set_language
from src.desktop.image_polygon import contour_geometry
from src.desktop.qt import QtCore, QtWidgets
from src.desktop.widgets import ImageViewer

try:
    from PyQt6.QtTest import QTest
except ImportError:
    from PySide6.QtTest import QTest


class ImagePolygonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        set_language('en')
        self.viewer = ImageViewer()
        self.viewer.resize(640, 520)
        self.viewer.show()
        self.viewer.set_grayscale_pixels(np.zeros((100, 120), dtype=np.uint8), 'fixture',
                                         ruler_scale=(2, 1, .4))
        self.viewer.actual_size()
        self.app.processEvents()

    def tearDown(self):
        self.viewer.close()
        self.viewer.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def position(self, x, y):
        return self.viewer.view.mapFromScene(QtCore.QPointF(x, y))

    def click(self, x, y, modifier=QtCore.Qt.KeyboardModifier.NoModifier):
        QTest.mouseClick(self.viewer.view.viewport(), QtCore.Qt.MouseButton.LeftButton, modifier,
                         pos=self.position(x, y))

    def drag(self, a, b, modifier=QtCore.Qt.KeyboardModifier.NoModifier):
        viewport = self.viewer.view.viewport()
        button = QtCore.Qt.MouseButton.LeftButton
        QTest.mousePress(viewport, button, modifier, pos=self.position(*a))
        QTest.mouseMove(viewport, self.position(*b))
        QTest.mouseRelease(viewport, button, modifier, pos=self.position(*b))

    def test_perimeter_and_equivalent_diameter_require_a_simple_closed_contour(self):
        self.assertEqual(contour_geometry([(1, 1), (4, 5)]), (5.0, None, None))
        length, area, diameter = contour_geometry([(0, 0), (4, 0), (4, 3), (0, 3)], closed=True)
        self.assertEqual((length, area), (14.0, 12.0))
        self.assertAlmostEqual(diameter, 2 * math.sqrt(12 / math.pi))
        crossing = [(0, 0), (4, 3), (0, 4), (3, 0)]
        self.assertEqual(contour_geometry(crossing, closed=True)[1:], (None, None))
        doubling_back = [(0, 0), (4, 0), (2, 0), (2, 3), (0, 3)]
        self.assertEqual(contour_geometry(doubling_back, closed=True)[1:], (None, None))

    def test_manual_path_move_close_and_convert_to_physical_units(self):
        contour = self.viewer.polygon
        self.viewer.polygon_button.click()
        for point in [(10, 10), (60, 10), (60, 50), (10, 50)]:
            self.click(*point)
        self.assertFalse(contour.closed)
        self.drag((10, 10), (20, 10))
        self.assertFalse(contour.closed)
        self.assertEqual(contour.points[0], QtCore.QPointF(20, 10))
        self.drag((20, 10), (10, 10))
        QTest.keyClick(self.viewer.view, QtCore.Qt.Key.Key_Return)
        self.assertTrue(contour.closed)
        self.assertIn('Perimeter 280.00 source px · 112 µm', contour.text())
        self.assertIn('Enclosed area 4000.00 source px² · 640 µm²', contour.text())
        self.assertIn('Equivalent diameter 71.36 source px · 28.5 µm', contour.text())
        self.click(35, 10)
        self.assertEqual(len(contour.points), 5)
        self.assertIn('280.00 source px', contour.text())
        QTest.keyClick(self.viewer.view, QtCore.Qt.Key.Key_Escape)
        self.assertFalse(contour.points)

    def test_shape_preset_and_outline_copy_have_editable_vertices(self):
        contour = self.viewer.polygon
        actions = self.viewer.polygon_button.actions_by_key
        actions['Draw a rectangle'].trigger()
        self.drag((10, 10), (60, 50))
        self.assertTrue(contour.closed)
        self.assertEqual(len(contour.points), 4)
        self.assertIn('280.00 source px', contour.text())
        actions['Draw an ellipse'].trigger()
        self.drag((10, 10), (60, 50))
        self.assertTrue(contour.closed)
        self.assertEqual(len(contour.points), 32)
        self.assertIn('Equivalent diameter', contour.text())
        source = {'class_id': 0, 'points': [(0.25, .2), (.75, .2), (.75, .8), (.25, .8)]}
        self.viewer.set_polygons([source])
        self.assertTrue(actions['Copy a displayed outline'].isEnabled())
        actions['Copy a displayed outline'].trigger()
        self.click(60, 50)
        self.assertTrue(contour.closed)
        self.drag((30, 20), (20, 20))
        self.assertEqual(contour.points[0], QtCore.QPointF(20, 20))
        self.assertEqual(source['points'][0], (.25, .2))
        self.viewer.ruler_button.click()
        self.assertFalse(contour.active)
        self.assertTrue(self.viewer.ruler.active)

    def test_enlarged_view_edits_the_same_contour_in_scene_coordinates(self):
        contour = self.viewer.polygon
        self.viewer.polygon_button.click()
        self.click(10, 10)
        self.click(60, 10)
        dialog = self.viewer.open_enlarged()
        try:
            self.app.processEvents()
            view = dialog.view
            pos = view.mapFromScene(QtCore.QPointF(60, 50))
            QTest.mouseClick(view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=pos)
            QTest.keyClick(view, QtCore.Qt.Key.Key_Return)
            self.assertTrue(contour.closed)
            self.assertEqual(len(contour.points), 3)
            self.assertIs(view.scene(), self.viewer.scene)
            self.assertIn('µm', contour.text())
            QTest.keyClick(view, QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
            self.assertFalse(contour.closed)
            self.assertEqual(len(contour.points), 3)
            QTest.keyClick(view, QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
            self.assertEqual(len(contour.points), 2)
        finally:
            dialog.close()
            self.app.processEvents()

    def test_shift_aligns_segments_and_constrains_shapes_on_the_measurement_grid(self):
        contour = self.viewer.polygon
        actions = self.viewer.polygon_button.actions_by_key
        self.assertTrue(all(not action.icon().isNull() for action in actions.values()))
        shift = QtCore.Qt.KeyboardModifier.ShiftModifier
        actions['Draw a path'].trigger()
        self.click(10, 10)
        self.click(45, 22, shift)
        self.click(50, 65, shift)
        self.assertEqual(contour.points, [QtCore.QPointF(10, 10), QtCore.QPointF(45, 10),
                                          QtCore.QPointF(45, 65)])
        for action, count in [('Draw a rectangle', 4), ('Draw an ellipse', 32)]:
            actions[action].trigger()
            self.drag((65, 70), (15, 20), shift)
            self.assertTrue(contour.closed)
            self.assertEqual(len(contour.points), count)
            x, y = zip(*contour._scaled_points())
            self.assertAlmostEqual(max(x) - min(x), max(y) - min(y))
            self.assertAlmostEqual(max(x) - min(x), 50)

    def test_undo_restores_the_previous_contour_one_edit_at_a_time(self):
        contour = self.viewer.polygon
        actions = self.viewer.polygon_button.actions_by_key
        self.viewer.polygon_button.click()
        for point in [(10, 10), (60, 10), (60, 50)]:
            self.click(*point)
        original = contour.points[:]
        undo = actions['Undo contour edit']
        QTest.keyClick(self.viewer.view, QtCore.Qt.Key.Key_Return)
        self.click(35, 10)
        self.assertEqual(len(contour.points), 4)
        undo.trigger()
        self.assertEqual(contour.points, original)
        self.assertTrue(contour.closed)

        viewport = self.viewer.view.viewport()
        left = QtCore.Qt.MouseButton.LeftButton
        QTest.mousePress(viewport, left, pos=self.position(10, 10))
        for x in (20, 24, 29):
            QTest.mouseMove(viewport, self.position(x, 10))
        QTest.mouseRelease(viewport, left, pos=self.position(29, 10))
        self.assertEqual(contour.points[0], QtCore.QPointF(29, 10))
        undo.trigger()
        self.assertEqual(contour.points, original)
        actions['Draw a rectangle'].trigger()
        self.drag((15, 15), (65, 60))
        undo.trigger()
        self.assertEqual(contour.points, original)
        actions['Clear contour'].trigger()
        self.assertFalse(contour.points)
        QTest.keyClick(self.viewer.view, QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(contour.points, original)
        self.assertTrue(contour.closed)
        undo.trigger()
        self.assertFalse(contour.closed)
        undo.trigger()
        self.assertEqual(contour.points, original[:2])

        self.viewer.set_grayscale_pixels(np.zeros((100, 120), dtype=np.uint8), 'next image')
        self.viewer.polygon_button.click()
        self.assertFalse(undo.isEnabled())


if __name__ == '__main__':
    unittest.main()
