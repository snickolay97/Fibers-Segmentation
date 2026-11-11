"""Wheel gestures scroll forms but never alter editable parameter values."""

import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from src.desktop.qt import QtCore, QtGui, QtWidgets, BINDING
from src.desktop.input_safety import install_parameter_wheel_guard

if BINDING == 'PySide6':
    from PySide6 import QtTest
else:
    from PyQt6 import QtTest


class ParameterWheelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.window = QtWidgets.QWidget()
        self.window.resize(400, 230)
        self.layout = QtWidgets.QVBoxLayout(self.window)
        self.guard = install_parameter_wheel_guard(self.window)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)

    def wheel(self, widget, delta=-120):
        point = QtCore.QPointF(widget.rect().center())
        global_point = QtCore.QPointF(widget.mapToGlobal(point.toPoint()))
        event = QtGui.QWheelEvent(point, global_point, QtCore.QPoint(), QtCore.QPoint(0, delta),
            QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier,
            QtCore.Qt.ScrollPhase.ScrollUpdate, False)
        self.app.sendEvent(widget, event)

    def test_focused_and_unfocused_parameters_ignore_wheel_but_accept_keyboard(self):
        spin = QtWidgets.QDoubleSpinBox()
        spin.setValue(5.5)
        combo = QtWidgets.QComboBox()
        combo.addItems(['a', 'b', 'c'])
        combo.setCurrentIndex(1)
        slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setValue(50)
        for control in (spin, combo, slider):
            self.layout.addWidget(control)
        self.window.show()
        self.app.processEvents()
        for focused in (False, True):
            for control in (spin, spin.lineEdit(), combo, slider):
                control.setFocus() if focused else control.clearFocus()
                self.wheel(control)
            self.assertEqual(spin.value(), 5.5)
            self.assertEqual(combo.currentIndex(), 1)
            self.assertEqual(slider.value(), 50)
        spin.setFocus()
        QtTest.QTest.keyClick(spin, QtCore.Qt.Key.Key_Up)
        combo.setFocus()
        QtTest.QTest.keyClick(combo, QtCore.Qt.Key.Key_Down)
        self.assertEqual(spin.value(), 6.5)
        self.assertEqual(combo.currentIndex(), 2)
        self.assertIs(install_parameter_wheel_guard(self.window), self.guard)

    def test_wheel_over_parameter_scrolls_surrounding_form(self):
        scroll = QtWidgets.QScrollArea()
        body = QtWidgets.QWidget()
        form = QtWidgets.QVBoxLayout(body)
        spin = QtWidgets.QSpinBox()
        spin.setValue(12)
        form.addWidget(spin)
        form.addWidget(QtWidgets.QLabel('Form'))
        body.setMinimumHeight(1200)
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        self.layout.addWidget(scroll)
        self.window.show()
        self.app.processEvents()
        self.assertEqual(scroll.verticalScrollBar().value(), 0)
        self.wheel(spin)
        self.assertGreater(scroll.verticalScrollBar().value(), 0)
        self.assertEqual(spin.value(), 12)

    def test_scope_leaves_other_windows_unaffected(self):
        external = QtWidgets.QSpinBox()
        external.setValue(12)
        external.show()
        try:
            self.wheel(external)
            self.assertEqual(external.value(), 11)
        finally:
            external.close()
            external.deleteLater()

    def test_real_application_protects_rebuilt_and_floating_controls(self):
        from src.desktop.main_window import MainWindow
        from src.desktop.project import Project
        from src.desktop.widgets import image_pool
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            preferences = QtCore.QSettings(str(root / 'ui.ini'), QtCore.QSettings.Format.IniFormat)
            project = Project.create(root / 'project.json')
            window = MainWindow(project, language='en', preferences=preferences)
            try:
                window.show()
                window.show_log.setChecked(False)
                guard = window._parameter_wheel_guard
                for language in ('en', 'ru', 'he'):
                    window.set_language(language)
                    window.sidebar.setCurrentRow(1)
                    dock = window._workspaces['preparation'].panels['settings']
                    dock.setFloating(True)
                    self.app.processEvents()
                    self.assertTrue(dock.isVisible())
                    spin = window._settings_fields['gamma']
                    spin.setValue(1.7)
                    spin.setFocus()
                    self.wheel(spin)
                    self.wheel(spin.lineEdit())
                    self.assertEqual(spin.value(), 1.7)
                    window.sidebar.setCurrentRow(3)
                    self.app.processEvents()
                    mode = window.labels_mode.currentIndex()
                    window.labels_mode.setFocus()
                    self.wheel(window.labels_mode)
                    self.assertEqual(window.labels_mode.currentIndex(), mode)
                    self.assertIs(window._parameter_wheel_guard, guard)
            finally:
                window.close()
                image_pool().waitForDone(5000)
                window.deleteLater()
                self.app.processEvents()
                QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)


if __name__ == '__main__':
    unittest.main()
