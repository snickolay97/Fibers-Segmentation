"""Verify edit coordinates, ownership, local filtering and versioned copies."""

import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

import cv2
import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from src.desktop.qt import BINDING, QtCore, QtWidgets
if BINDING == 'PyQt6':
    from PyQt6 import QtTest
else:
    from PySide6 import QtTest
from src.desktop.tile_edit import TileEdit, TileEditContext
from src.default_settings import EDITOR_DEFAULTS, EDITOR_DEFAULTS_VERSION
from src.desktop.widgets import ImageViewer, image_pool
from src.tile_scale import fixed_canvas, scale_metadata


class TileEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        self.dataset = self.workspace / 'dataset'
        self.dataset.mkdir()
        self.source = self.dataset / 'тайл_0001.png'
        self.mask_file = self.dataset / 'valid.png'
        self.record = dict(id=1, filename=self.source.name, valid_mask=self.mask_file.name)
        self.context = TileEditContext(str(self.workspace), 'prepared-1', str(self.dataset), self.record, 'native')
        self.pixels = np.full((40, 60), 18000, dtype=np.uint16)
        self.pixels[12:15, 20] = 40000
        self.mask = np.full(self.pixels.shape, 255, dtype=np.uint8)
        self.mask[:, :8] = 0
        self.pixels[self.mask == 0] = 0
        self._write_inputs()

    def tearDown(self):
        QtCore.QThreadPool.globalInstance().waitForDone(5000)
        image_pool().waitForDone(5000)
        self.app.processEvents()
        self.temporary.cleanup()

    def _write_inputs(self):
        for filename, pixels in ((self.source, self.pixels), (self.mask_file, self.mask)):
            ok, png = cv2.imencode('.png', pixels)
            self.assertTrue(ok)
            filename.write_bytes(png.tobytes())

    def test_stroke_adds_padding_only_where_owned_and_undo_restores_it(self):
        edit = TileEdit(self.source, self.context)
        self.assertFalse(edit.erase([(0, 2), (3, 3)], 0, 'line'))
        self.assertTrue(edit.erase([(1, 10), (14, 10)], 1, 'line'))
        self.assertFalse(edit.valid[9:12, 8:15].any())
        self.assertTrue(edit.valid[10, 15] == 0)
        self.assertTrue(edit.valid[9, 15])
        self.assertTrue(edit.erase([(20, 20), (24, 20), (24, 25)], 0, 'freehand'))
        self.assertEqual(edit.pixels[22, 24], 0)
        self.assertEqual(edit.pixels[22, 22], 18000)
        edit.undo()
        self.assertEqual(edit.pixels[22, 24], 18000)
        edit.undo()
        np.testing.assert_array_equal(edit.pixels, self.pixels)
        np.testing.assert_array_equal(edit.valid, self.mask > 0)

    def test_paint_records_synthetic_signal_and_restores_pixels_on_undo(self):
        edit = TileEdit(self.source, self.context)
        self.assertTrue(edit.paint([(3, 20), (25, 20)], 1, 40000, [20, 13]))
        self.assertEqual(edit.pixels[20, 7], 0)
        self.assertEqual(edit.pixels[20, 8], 40000)
        self.assertEqual(edit.pixels[22, 20], 18000)
        np.testing.assert_array_equal(edit.valid, self.mask > 0)
        self.assertTrue(edit.operations[-1]['synthetic_signal'])
        self.assertEqual(edit.operations[-1]['sampled_at'], [20, 13])
        edit.undo()
        np.testing.assert_array_equal(edit.pixels, self.pixels)

    def test_pipette_samples_native_depth_then_draws_without_brightening_background(self):
        dialog = self._open_editor('ru')
        editor, view = dialog.tile_editor, dialog.viewer.view
        editor.mode.setCurrentIndex(editor.mode.findData('paint'))
        self.assertTrue(editor.pick_button.isChecked())
        point = view.mapFromScene(QtCore.QPointF(20.5, 13.5))
        QtTest.QTest.mouseClick(view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(editor.paint_intensity.value(), 40000)
        self.assertEqual(editor._paint_sample, [20, 13])
        self.assertFalse(editor.edit.operations)
        editor.paint_radius.setValue(0)
        self._drag(view, (20, 15), (20, 23))
        self._wait(editor.undo_button.isEnabled)
        self.assertTrue(np.all(editor.edit.pixels[15:24, 20] == 40000))
        self.assertEqual(editor.edit.pixels[20, 21], 18000)
        editor.undo_button.click()
        np.testing.assert_array_equal(editor.edit.pixels, self.pixels)

    def test_local_filter_uses_context_and_ignores_padding(self):
        edit = TileEdit(self.source, self.context)
        self.assertTrue(edit.erase([(18, 12), (18, 15)], 0, 'line'))
        before = edit.pixels.copy()
        self.assertTrue(edit.remove_background((4, 12, 26, 15), 3))
        self.assertEqual(edit.pixels[13, 20], 22000)
        self.assertEqual(edit.pixels[13, 8], 0)
        self.assertEqual(edit.pixels[13, 18], 0)
        self.assertFalse(edit.valid[13, 18])
        self.assertTrue(edit.valid[13, 8])
        self.assertEqual(edit.pixels[15, 20], 18000)
        edit.undo()
        np.testing.assert_array_equal(edit.pixels, before)

    def test_save_versions_keep_native_bit_depth_and_provenance(self):
        original = self.source.read_bytes()
        edit = TileEdit(self.source, self.context)
        edit.erase([(15, 20), (25, 20)], 1, 'line')
        first = edit.save()
        edit.remove_background((4, 12, 26, 15), 3)
        second = edit.save()
        self.assertEqual((first.name, second.name), ('Edit_001', 'Edit_002'))
        self.assertEqual(self.source.read_bytes(), original)
        exported = cv2.imdecode(np.frombuffer((second / 'tile.png').read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)
        self.assertEqual(exported.dtype, np.uint16)
        np.testing.assert_array_equal(exported, edit.pixels)
        validity = cv2.imdecode(np.frombuffer((second / 'valid_mask.png').read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)
        np.testing.assert_array_equal(validity != 0, edit.valid)
        provenance = json.loads((second / 'edit.json').read_text(encoding='utf-8'))
        self.assertEqual(provenance['source_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual([op['tool'] for op in provenance['operations']], ['line', 'background'])
        self.assertEqual(provenance['space'], 'native')
        self.assertEqual(sorted(path.name for path in second.parent.iterdir()), ['Edit_001', 'Edit_002'])

    def test_model_uses_transformed_mask_for_resized_padded_canvas(self):
        transform = scale_metadata(*self.pixels.shape, target=30)
        model = self.dataset / 'model.png'
        ok, png = cv2.imencode('.png', fixed_canvas(self.pixels, transform))
        self.assertTrue(ok)
        model.write_bytes(png.tobytes())
        context = TileEditContext(str(self.workspace), 'prepared-1', str(self.dataset),
                                  dict(self.record, transform=transform), 'model')
        edit = TileEdit(model, context)
        self.assertEqual(edit.valid.shape, (30, 30))
        self.assertFalse(edit.valid[:, :4].any())
        self.assertFalse(edit.valid[20:, :].any())
        self.assertTrue(edit.valid[:20, 4:].all())

    def _wait(self, predicate):
        until = time.monotonic() + 5
        while not predicate() and time.monotonic() < until:
            self.app.processEvents()
            time.sleep(.01)
        self.assertTrue(predicate())

    def _open_editor(self, language='ru'):
        dialog = ImageViewer.open_image_window(self.source, original=True, language=language, tile_editor=self.context)
        self.addCleanup(dialog.close)
        self._wait(dialog.tile_editor.start.isEnabled)
        dialog.tile_editor.start.click()
        self._wait(lambda: dialog.tile_editor.edit is not None)
        return dialog

    def test_editor_factory_eraser_radius_is_shared_and_immutable(self):
        dialog = self._open_editor()
        self.assertEqual(EDITOR_DEFAULTS_VERSION, 3)
        self.assertEqual(dialog.tile_editor.erase_radius.value(), 60)
        self.assertEqual(dialog.tile_editor.erase_radius.value(), EDITOR_DEFAULTS['erase_radius'])
        with self.assertRaises(TypeError):
            EDITOR_DEFAULTS['erase_radius'] = 4

    def _drag(self, view, first, last):
        self.app.processEvents()
        mouse = QtCore.Qt.MouseButton.LeftButton
        start = view.mapFromScene(QtCore.QPointF(first[0] + .5, first[1] + .5))
        finish = view.mapFromScene(QtCore.QPointF(last[0] + .5, last[1] + .5))
        QtTest.QTest.mousePress(view.viewport(), mouse, pos=start)
        QtTest.QTest.mouseMove(view.viewport(), finish)
        QtTest.QTest.mouseRelease(view.viewport(), mouse, pos=finish)

    def test_cut_preview_choose_side_cancel_and_apply(self):
        dialog = self._open_editor()
        editor, view = dialog.tile_editor, dialog.viewer.view
        editor.mode.setCurrentIndex(editor.mode.findData('cut'))
        self._drag(view, (20, 8), (20, 25))
        self.assertFalse(editor.apply_button.isEnabled())
        editor.smaller_button.click()
        self._wait(editor.apply_button.isEnabled)
        self.assertEqual(editor._cut_side, 1)
        self.assertEqual(len(editor._guides), 2)
        right = view.mapFromScene(QtCore.QPointF(40.5, 20.5))
        QtTest.QTest.mouseClick(view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=right)
        self.assertEqual(editor._cut_side, -1)
        np.testing.assert_array_equal(editor.edit.pixels, self.pixels)
        dialog.activateWindow()
        self.app.processEvents()
        QtTest.QTest.keyClick(view, QtCore.Qt.Key.Key_Escape)
        self.assertTrue(dialog.isVisible())
        self.assertIsNone(editor._cut_line)
        self.assertFalse(editor.apply_button.isEnabled())
        self._drag(view, (20, 8), (20, 25))
        editor.smaller_button.click()
        self._wait(editor.apply_button.isEnabled)
        editor.apply_button.click()
        self._wait(editor.undo_button.isEnabled)
        self.assertFalse(editor.edit.valid[:, :20].any())
        np.testing.assert_array_equal(editor.edit.pixels[:, 20:], self.pixels[:, 20:])
        editor.undo_button.click()
        np.testing.assert_array_equal(editor.edit.valid, self.mask != 0)

    def test_gamma_previews_the_last_background_rectangle_then_applies(self):
        dialog = self._open_editor()
        editor, view = dialog.tile_editor, dialog.viewer.view
        editor.mode.setCurrentIndex(editor.mode.findData('background'))
        editor.background_radius.setValue(3)
        self._drag(view, (4, 12), (25, 14))
        self._wait(editor.undo_button.isEnabled)
        baseline = editor.edit.pixels.copy()
        self.assertEqual(baseline[13, 20], 22000)
        editor.mode.setCurrentIndex(editor.mode.findData('gamma'))
        self.assertEqual(tuple(editor.gamma_scope.currentData()), (4, 12, 26, 15))
        editor.gamma_slider.setValue(200)
        self._wait(editor.apply_button.isEnabled)
        np.testing.assert_array_equal(editor.edit.pixels, baseline)
        self.assertEqual(len(editor.edit.operations), 1)
        self.assertEqual(len(editor._guides), 1)
        preview = dialog.viewer._pixmap_item.pixmap().toImage()
        self.assertGreater(preview.pixelColor(20, 13).red(), 22000 >> 8)
        self.assertEqual(preview.pixelColor(20, 15).red(), 18000 >> 8)
        editor.original.click()
        self.assertFalse(editor.apply_button.isEnabled())
        self.assertEqual(editor._guides, [])
        self.assertEqual(dialog.viewer._pixmap_item.pixmap().toImage().pixelColor(20, 13).red(), 40000 >> 8)
        editor.original.click()
        self.assertTrue(editor.apply_button.isEnabled())
        self.assertEqual(len(editor._guides), 1)
        editor.apply_button.click()
        self._wait(editor.undo_button.isEnabled)
        self.assertGreater(editor.edit.pixels[13, 20], baseline[13, 20])
        self.assertEqual(editor.edit.pixels[15, 20], baseline[15, 20])
        np.testing.assert_array_equal(editor.edit.valid, self.mask != 0)
        self.assertEqual(editor.edit.operations[-1]['bounds_ltrb'], (4, 12, 26, 15))
        editor.gamma_scope.setCurrentIndex(0)
        editor.gamma_slider.setValue(200)
        editor.cancel_button.click()
        QtTest.QTest.qWait(140)
        self.assertEqual(len(editor.edit.operations), 2)
        self.assertFalse(editor.apply_button.isEnabled())

    def test_gamma_custom_rectangle_previews_only_selected_pixels_in_each_language(self):
        for language in ('en', 'ru', 'he'):
            with self.subTest(language=language):
                dialog = self._open_editor(language)
                editor, view = dialog.tile_editor, dialog.viewer.view
                editor.mode.setCurrentIndex(editor.mode.findData('gamma'))
                editor.gamma_scope.setCurrentIndex(editor.gamma_scope.findData('rectangle'))
                editor.gamma_slider.setValue(200)
                QtTest.QTest.qWait(150)
                self.assertIsNone(editor._gamma_preview_key)
                self.assertFalse(editor.apply_button.isEnabled())
                self.assertEqual(editor.edit.operations, [])
                self._drag(view, (24, 22), (10, 16))
                self._wait(editor.apply_button.isEnabled)
                self.assertEqual(editor._gamma_request(), (2.0, (10, 16, 25, 23)))
                preview = dialog.viewer._pixmap_item.pixmap().toImage()
                self.assertGreater(preview.pixelColor(10, 16).red(), 18000 >> 8)
                self.assertEqual(preview.pixelColor(25, 16).red(), 18000 >> 8)
                self.assertEqual(preview.pixelColor(10, 23).red(), 18000 >> 8)
                np.testing.assert_array_equal(editor.edit.pixels, self.pixels)
                editor.apply_button.click()
                self._wait(editor.undo_button.isEnabled)
                self.assertEqual(editor.edit.operations[-1]['bounds_ltrb'], (10, 16, 25, 23))
                outside = np.ones(self.pixels.shape, bool)
                outside[16:23, 10:25] = False
                np.testing.assert_array_equal(editor.edit.pixels[outside], self.pixels[outside])
                np.testing.assert_array_equal(editor.edit.valid, self.mask != 0)
                self._drag(view, (12, 18), (14, 20))
                self.assertEqual(editor.gamma_slider.value(), 100)
                dialog.activateWindow()
                self.app.processEvents()
                QtTest.QTest.keyClick(view, QtCore.Qt.Key.Key_Escape)
                self.assertTrue(dialog.isVisible())
                self.assertIsNone(editor._gamma_rectangle)
                self.assertEqual(len(editor.edit.operations), 1)

    def test_original_window_draws_at_saved_pixel_coordinates_and_compares(self):
        help_topics = []
        parent = QtWidgets.QWidget()
        parent.show_help = help_topics.append
        self.addCleanup(parent.deleteLater)
        dialog = ImageViewer.open_image_window(self.source, parent=parent, language='he', original=True,
                                               tile_editor=self.context)
        self.addCleanup(dialog.close)
        editor = dialog.tile_editor
        self._wait(editor.start.isEnabled)
        self.assertEqual(editor.help.accessibleName(), 'עזרה לעריכת אריחים')
        editor.help.click()
        dialog.activateWindow()
        self.app.processEvents()
        QtTest.QTest.keyClick(dialog.viewer.view, QtCore.Qt.Key.Key_F1)
        self.assertEqual(help_topics, ['tile_editor', 'tile_editor'])
        editor.start.click()
        self._wait(lambda: editor.edit is not None)
        self.assertEqual(editor.mode.currentData(), 'pan')
        editor.mode.setCurrentIndex(editor.mode.findData('line'))
        editor.cursor_choice.setCurrentIndex(editor.cursor_choice.findData('Arrow'))
        editor.erase_radius.setValue(0)
        view = dialog.viewer.view
        self.assertEqual(view.viewport().cursor().shape(), QtCore.Qt.CursorShape.ArrowCursor)
        first = view.mapFromScene(QtCore.QPointF(20.5, 14.5))
        last = view.mapFromScene(QtCore.QPointF(25.5, 14.5))
        mouse = QtCore.Qt.MouseButton.LeftButton
        QtTest.QTest.mousePress(view.viewport(), mouse, pos=first)
        QtTest.QTest.mouseMove(view.viewport(), last)
        QtTest.QTest.mouseRelease(view.viewport(), mouse, pos=last)
        self._wait(editor.undo_button.isEnabled)
        self.assertTrue(editor.save_button.isEnabled())
        self.assertEqual(editor.edit.operations[0]['points'], [(20, 14), (25, 14)])
        self.assertEqual(editor.edit.pixels[14, 20], 0)
        editor.compare_button.click()
        comparison = editor._comparison
        comparison.overlay_button.click()
        for opacity, expected in ((0, 40000 >> 8), (100, 0)):
            comparison.opacity.setValue(opacity)
            self.assertEqual(comparison.overlay_view.export_frame().pixelColor(20, 14).red(), expected)
        comparison.close()
        dialog.viewer.zoom(1.3)
        transform = view.transform()
        scroll = (view.horizontalScrollBar().value(), view.verticalScrollBar().value())
        self.assertEqual(dialog.viewer._pixmap_item.pixmap().toImage().pixelColor(20, 14).red(), 0)
        self.assertEqual(dialog.viewer._pixmap_item.pixmap().toImage().pixelColor(20, 13).red(), 40000 >> 8)
        editor.original.click()
        self.assertEqual(dialog.viewer._pixmap_item.pixmap().toImage().pixelColor(20, 14).red(), 40000 >> 8)
        self.assertEqual(view.transform(), transform)
        self.assertEqual((view.horizontalScrollBar().value(), view.verticalScrollBar().value()), scroll)
        editor.original.click()
        QtTest.QTest.keyClick(view, QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(editor.edit.pixels[14, 20], 40000)
        self.assertFalse(editor.save_button.isEnabled())


if __name__ == '__main__':
    unittest.main()
