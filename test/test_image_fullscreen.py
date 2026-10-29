"""Real Qt image controls share one scene across embedded/full-screen views."""

import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

try:
    from src.desktop.qt import QtCore, QtGui, QtWidgets, BINDING, configure_font
    from src.desktop.widgets import ImageViewer, image_pool
    from src.desktop.i18n import get_language, set_language, tr
    from src.desktop.help import help_text
    if BINDING == 'PySide6':
        from PySide6 import QtTest
    else:
        from PyQt6 import QtTest
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


@unittest.skipUnless(QT_AVAILABLE, 'Qt binding is not installed')
class ImageFullscreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        configure_font()

    def setUp(self):
        from PIL import Image
        self.language = get_language()
        set_language('en')
        self.click_interval = self.app.doubleClickInterval()
        self.app.setDoubleClickInterval(60)
        self.temporary = tempfile.TemporaryDirectory(prefix='solodata_fullscreen_')
        self.folder = Path(self.temporary.name)
        self.filename = self.folder / 'native.png'
        Image.new('L', (3200, 1600), 100).save(self.filename)
        self.viewer = ImageViewer()
        self.viewer.resize(640, 440)
        self.viewer.show()
        self.viewer.activateWindow()
        self.app.processEvents()

    def tearDown(self):
        if self.viewer is not None:
            self.viewer.close()
            self.viewer.deleteLater()
        image_pool().waitForDone(5000)
        self.flush_deletes()
        self.temporary.cleanup()
        self.app.setDoubleClickInterval(self.click_interval)
        set_language(self.language)

    def flush_deletes(self):
        self.app.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def pump_until(self, condition, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if condition():
                return
            time.sleep(.005)
        self.fail('Timed out waiting for an image or window event')

    def load_image(self):
        self.viewer.set_image(self.filename, 'Native crop · source pixels')
        self.pump_until(lambda: self.viewer.original_size == (3200, 1600))
        self.assertEqual(self.viewer._pixmap_item.pixmap().width(), 2400)

    def test_empty_or_loading_image_cannot_open_fullscreen(self):
        self.assertFalse(self.viewer.fullscreen_button.isEnabled())
        self.assertIsNone(self.viewer.open_fullscreen())
        QtTest.QTest.mouseDClick(self.viewer.view.viewport(), QtCore.Qt.MouseButton.LeftButton)
        self.assertIsNone(self.viewer._fullscreen_dialog)
        self.viewer.set_image(self.filename)
        self.assertFalse(self.viewer.fullscreen_button.isEnabled())
        self.assertIsNone(self.viewer.open_fullscreen())
        self.pump_until(lambda: self.viewer.fullscreen_button.isEnabled())
        self.viewer.clear()
        self.assertFalse(self.viewer.fullscreen_button.isEnabled())

    def test_button_opens_second_view_without_decode_or_reparenting(self):
        self.load_image()
        original_scene = self.viewer.scene
        original_item = self.viewer._pixmap_item
        original_transform = QtGui.QTransform(self.viewer.view.transform())
        with patch('src.desktop.widgets._ImageTask', side_effect=AssertionError('Fullscreen must not decode again')):
            self.viewer.fullscreen_button.click()
            self.app.processEvents()
            dialog = self.viewer._fullscreen_dialog
            self.assertIsNotNone(dialog)
            self.assertTrue(dialog.isFullScreen())
            self.assertIs(dialog.view.scene(), original_scene)
            self.assertIs(self.viewer.view.scene(), original_scene)
            self.assertIs(self.viewer._pixmap_item, original_item)
            self.assertIs(self.viewer.view.parentWidget(), self.viewer)
            self.assertEqual(dialog.caption.text(), self.viewer.caption.text())
            self.assertEqual(self.viewer.view.transform(), original_transform)
            dialog.exit_button.click()
            self.app.processEvents()
        self.assertIsNone(self.viewer._fullscreen_dialog)
        self.assertIs(self.viewer.view.scene(), original_scene)
        self.assertIs(self.viewer._pixmap_item, original_item)
        self.assertEqual(self.viewer.view.transform(), original_transform)

    def test_f11_opens_and_escape_and_f11_close(self):
        self.load_image()
        self.viewer.view.setFocus()
        self.app.processEvents()
        QtTest.QTest.keyClick(self.viewer.view, QtCore.Qt.Key.Key_F11)
        self.pump_until(lambda: self.viewer._fullscreen_dialog is not None)
        dialog = self.viewer._fullscreen_dialog
        dialog.activateWindow()
        dialog.view.setFocus()
        self.app.processEvents()
        QtTest.QTest.keyClick(dialog.view, QtCore.Qt.Key.Key_Escape)
        self.pump_until(lambda: self.viewer._fullscreen_dialog is None)
        self.viewer.activateWindow()
        self.viewer.view.setFocus()
        self.app.processEvents()
        QtTest.QTest.keyClick(self.viewer.view, QtCore.Qt.Key.Key_F11)
        self.pump_until(lambda: self.viewer._fullscreen_dialog is not None)
        dialog = self.viewer._fullscreen_dialog
        dialog.activateWindow()
        dialog.view.setFocus()
        self.app.processEvents()
        QtTest.QTest.keyClick(dialog.view, QtCore.Qt.Key.Key_F11)
        self.pump_until(lambda: self.viewer._fullscreen_dialog is None)

    def test_double_click_cancels_the_first_selection_click(self):
        self.load_image()
        clicks = []
        self.viewer.clicked.connect(lambda x, y: clicks.append((x, y)))
        point = self.viewer.view.mapFromScene(QtCore.QPointF(1000, 500))
        QtTest.QTest.mouseClick(self.viewer.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
        QtTest.QTest.mouseDClick(self.viewer.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
        self.pump_until(lambda: self.viewer._fullscreen_dialog is not None)
        QtTest.QTest.qWait(self.app.doubleClickInterval() + 20)
        self.assertEqual(clicks, [])
        self.viewer.close_fullscreen()

    def test_zoom_wheel_pan_and_fit_do_not_change_embedded_view(self):
        self.load_image()
        original_transform = QtGui.QTransform(self.viewer.view.transform())
        dialog = self.viewer.open_fullscreen()
        self.app.processEvents()
        QtTest.QTest.qWait(20)
        baseline = dialog.view.transform().m11()
        dialog.zoom_in_button.click()
        self.assertAlmostEqual(dialog.view.transform().m11(), baseline * 1.3)
        dialog.zoom_out_button.click()
        self.assertAlmostEqual(dialog.view.transform().m11(), baseline)
        point = QtCore.QPointF(dialog.view.viewport().rect().center())
        wheel = QtGui.QWheelEvent(point, point, QtCore.QPoint(), QtCore.QPoint(0, 120),
            QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier,
            QtCore.Qt.ScrollPhase.ScrollUpdate, False)
        QtCore.QCoreApplication.sendEvent(dialog.view.viewport(), wheel)
        self.assertAlmostEqual(dialog.view.transform().m11(), baseline * 1.18)
        dialog.zoom_in_button.click()
        dialog.zoom_in_button.click()
        before = dialog.view.horizontalScrollBar().value()
        point = dialog.view.viewport().rect().center()
        QtTest.QTest.mousePress(dialog.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
        QtTest.QTest.mouseMove(dialog.view.viewport(), point + QtCore.QPoint(50, 20), 20)
        QtTest.QTest.mouseRelease(dialog.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point + QtCore.QPoint(50, 20))
        self.assertNotEqual(dialog.view.horizontalScrollBar().value(), before)
        dialog.fit_button.click()
        self.assertAlmostEqual(dialog.view.transform().m11(), baseline)
        self.assertEqual(self.viewer.view.transform(), original_transform)

    def test_polygons_and_click_coordinates_share_native_mapping(self):
        self.load_image()
        self.viewer.set_polygons([{'class_id': 2, 'points': [(.1, .1), (.9, .1), (.9, .9)]}])
        original_polygon = self.viewer._overlay_items[0]
        dialog = self.viewer.open_fullscreen()
        self.app.processEvents()
        self.assertIn(original_polygon, dialog.view.scene().items())
        clicks = []
        self.viewer.clicked.connect(lambda x, y: clicks.append((x, y)))
        position = dialog.view.mapFromScene(QtCore.QPointF(1200, 500))
        scene_point = dialog.view.mapToScene(position)
        QtTest.QTest.mouseClick(dialog.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=position)
        self.pump_until(lambda: len(clicks) == 1)
        self.assertAlmostEqual(clicks[0][0], scene_point.x() * 3200 / 2400)
        self.assertAlmostEqual(clicks[0][1], scene_point.y() * 1600 / 1200)
        self.viewer.set_polygons([{'class_id': 5, 'points': [(.2, .2), (.8, .2), (.8, .8)]}])
        self.assertNotIn(original_polygon, dialog.view.scene().items())
        self.assertIn(self.viewer._overlay_items[0], dialog.view.scene().items())
        dialog.close()
        self.assertIs(self.viewer._overlay_items[0].scene(), self.viewer.scene)

    def test_change_clear_hide_and_retranslate_close_stale_dialogs(self):
        self.load_image()
        self.viewer.open_fullscreen()
        self.viewer.set_image(self.filename)
        self.assertIsNone(self.viewer._fullscreen_dialog)
        self.pump_until(lambda: self.viewer.fullscreen_button.isEnabled())
        self.viewer.open_fullscreen()
        self.viewer.retranslate('ru')
        self.assertIsNone(self.viewer._fullscreen_dialog)
        self.assertEqual(self.viewer.fullscreen_button.accessibleName(), 'Во весь экран')
        self.assertEqual(self.viewer.open_fullscreen().exit_button.text(), 'Выйти из полного экрана · Esc')
        self.viewer.hide()
        self.assertIsNone(self.viewer._fullscreen_dialog)
        self.viewer.show()
        self.viewer.open_fullscreen()
        self.viewer.clear()
        self.assertIsNone(self.viewer._fullscreen_dialog)
        self.assertEqual(self.viewer.scene.items(), [])

    def test_disposal_destroys_child_dialog_and_does_not_keep_scene_alive(self):
        self.load_image()
        dialog = self.viewer.open_fullscreen()
        destroyed = []
        dialog.destroyed.connect(lambda: destroyed.append(True))
        self.viewer.deleteLater()
        self.viewer = None
        self.flush_deletes()
        self.assertTrue(destroyed)

    def test_toggle_help_and_fullscreen_translations_are_bilingual(self):
        for key in ('enable_bilateral', 'enable_tophat', 'enable_gamma', 'enable_closing', 'enable_dilation', 'image_fullscreen'):
            self.assertNotEqual(help_text(key, 'en'), help_text(key, 'ru'))
            self.assertGreater(len(help_text(key, 'en')), 60)
        self.assertIn('normalization', help_text('enable_tophat', 'en'))
        self.assertIn('background as well as faint signal', help_text('enable_gamma', 'en'))
        self.assertEqual(tr('Segmentation', language='ru'), 'Сегментация')
        self.assertEqual(tr('Skipping protective closing', language='ru'), 'Замыкание защитной маски пропущено')

    def test_repeated_construction_and_deferred_disposal_keep_qt_callbacks_safe(self):
        # Do not replace sys.excepthook: a callback exception must fail this
        # process as it would a real PyQt application.
        for _ in range(30):
            parent = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(parent)
            viewer = ImageViewer(parent)
            layout.addWidget(viewer)
            parent.show()
            self.app.processEvents()
            viewer.retranslate('ru')
            self.app.processEvents()
            parent.deleteLater()
            self.flush_deletes()

    def test_pending_selection_is_cancelled_when_image_changes(self):
        self.load_image()
        clicks = []
        self.viewer.clicked.connect(lambda x, y: clicks.append((x, y)))
        point = self.viewer.view.mapFromScene(QtCore.QPointF(1000, 500))
        QtTest.QTest.mouseClick(self.viewer.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
        self.viewer.clear()
        QtTest.QTest.qWait(self.app.doubleClickInterval() + 20)
        self.assertEqual(clicks, [])

    def test_image_loaded_on_hidden_tab_fits_when_shown_and_resized(self):
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(QtWidgets.QWidget(), 'Other')
        preview = ImageViewer()
        tabs.addTab(preview, 'Filtered')
        tabs.resize(920, 700)
        tabs.show()
        self.app.processEvents()
        try:
            preview.set_image(self.filename)
            self.pump_until(lambda: preview.original_size == (3200, 1600))
            self.assertFalse(preview.view.isVisible())
            tabs.setCurrentIndex(1)
            self.app.processEvents()
            QtTest.QTest.qWait(30)
            viewport = preview.view.viewport()
            fitted_width = 2400 * preview.view.transform().m11()
            self.assertGreater(fitted_width, viewport.width() * .9)
            self.assertLessEqual(fitted_width, viewport.width())
            initial_scale = preview.view.transform().m11()
            tabs.resize(700, 530)
            self.app.processEvents()
            QtTest.QTest.qWait(30)
            self.assertLess(preview.view.transform().m11(), initial_scale)
            self.assertGreater(2400 * preview.view.transform().m11(), preview.view.viewport().width() * .9)
        finally:
            tabs.close()
            tabs.deleteLater()
            self.flush_deletes()

    def test_manual_zoom_survives_resize_until_fit_is_requested(self):
        self.load_image()
        self.app.processEvents()
        self.viewer.zoom(1.3)
        manual = self.viewer.view.transform().m11()
        self.viewer.resize(920, 680)
        self.app.processEvents()
        QtTest.QTest.qWait(30)
        self.assertAlmostEqual(self.viewer.view.transform().m11(), manual)
        self.assertFalse(self.viewer._auto_fit)
        self.viewer.fit_button.click()
        self.app.processEvents()
        QtTest.QTest.qWait(30)
        fitted = self.viewer.view.transform().m11()
        self.assertTrue(self.viewer._auto_fit)
        self.viewer.resize(720, 500)
        self.app.processEvents()
        QtTest.QTest.qWait(30)
        self.assertLess(self.viewer.view.transform().m11(), fitted)

    def test_manual_pan_disables_auto_fit_and_fullscreen_zoom_keeps_it_separate(self):
        self.load_image()
        self.app.processEvents()
        dialog = self.viewer.open_fullscreen()
        self.app.processEvents()
        dialog.zoom_in_button.click()
        self.assertTrue(self.viewer._auto_fit)
        dialog.close()
        self.viewer.fit()
        self.app.processEvents()
        point = self.viewer.view.viewport().rect().center()
        QtTest.QTest.mousePress(self.viewer.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
        QtTest.QTest.mouseMove(self.viewer.view.viewport(), point + QtCore.QPoint(25, 15), 20)
        QtTest.QTest.mouseRelease(self.viewer.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point + QtCore.QPoint(25, 15))
        self.assertFalse(self.viewer._auto_fit)


if __name__ == '__main__':
    unittest.main()
