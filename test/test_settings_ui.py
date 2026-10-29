"""Invalid user edits must remain recoverable without damaging a project."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from src.default_settings import FACTORY_DEFAULTS
from src.desktop.qt import QtCore, QtWidgets, BINDING
from src.desktop.project import Project, atomic_json
from src.desktop.main_window import MainWindow
from src.desktop.widgets import image_pool

if BINDING == 'PySide6':
    from PySide6 import QtTest
else:
    from PyQt6 import QtTest


class SettingsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.project = Project.create(self.root/'project.json')
        self.preferences = QtCore.QSettings(str(self.root/'preferences.ini'), QtCore.QSettings.Format.IniFormat)
        self.windows = []

    def window(self, project=None, language='en'):
        window = MainWindow(project or self.project, preferences=self.preferences, language=language)
        self.windows.append(window)
        window.show()
        self.app.processEvents()
        return window

    def tearDown(self):
        for window in self.windows:
            window.close()
            window.deleteLater()
        image_pool().waitForDone(5000)
        self.app.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        self.temporary.cleanup()

    def test_actual_even_kernel_reopens_with_exact_backup_and_other_values_preserved(self):
        original = self.project.to_dict()
        original['settings'].update(buffer_kernel_size=6, gamma=1.6)
        atomic_json(self.project.path, original)
        before = Path(self.project.path).read_bytes()
        window = self.window(Project.load(self.project.path))
        self.assertTrue(window._recovery_report['changed'])
        self.assertEqual(Path(window._recovery_report['backup_path']).read_bytes(), before)
        self.assertEqual(window._settings_fields['buffer_kernel_size'].value(), 5)
        self.assertEqual(window._settings_fields['gamma'].value(), 1.6)
        self.assertFalse(window.settings_feedback.isHidden())
        recovered = Project.load(self.project.path)
        self.assertEqual(recovered.settings['gamma'], 1.6)
        self.assertEqual(recovered.sources, original['sources'])
        self.assertEqual(recovered.datasets, original['datasets'])

    def test_invalid_draft_is_explained_and_cannot_be_saved_or_started(self):
        window = self.window()
        before = Path(self.project.path).read_bytes()
        field = window._settings_fields['buffer_kernel_size']
        field.stepUp()
        self.assertEqual(field.value(), 7)
        field.setValue(6)
        self.assertTrue(field.property('invalidSetting'))
        self.assertFalse(window.save_button.isEnabled())
        self.assertIn('odd', window.settings_feedback_text.text())
        with patch.object(QtWidgets.QMessageBox, 'warning') as warning:
            window.save_project()
            self.assertFalse(window.start_job('preview', settings=window.collect_settings()))
        warning.assert_not_called()
        self.assertIsNone(window.process)
        self.assertFalse((self.root/'jobs').exists())
        self.assertEqual(Path(self.project.path).read_bytes(), before)
        window.close()
        self.assertEqual(Path(self.project.path).read_bytes(), before)
        reopened = self.window(Project.load(self.project.path))
        self.assertEqual(reopened._settings_fields['buffer_kernel_size'].value(), 5)

    def test_restore_saved_and_factory_settings_are_separate_from_the_reference(self):
        self.project.settings['gamma'] = 1.6
        self.project.settings.update(oversized_policy='error', seam_repulsion_power=2.5, animation_max_trial_frames=40)
        self.project.save()
        window = self.window()
        window._settings_fields['gamma'].setValue(2.0)
        window.show_help('gamma')
        guide = window._help_center
        self.assertEqual(guide.current_settings['gamma'], 2.0)
        self.assertEqual(FACTORY_DEFAULTS['gamma'], 1.2)
        window.restore_factory_settings()
        self.assertEqual(window.collect_settings()['gamma'], 1.2)
        self.assertEqual(window.collect_settings()['oversized_policy'], 'preserve')
        self.assertEqual(window.collect_settings()['seam_repulsion_power'], 1.5)
        self.assertEqual(window.collect_settings()['animation_max_trial_frames'], 24)
        self.assertEqual(Project.load(self.project.path).settings['gamma'], 1.6)
        window.restore_saved_settings()
        self.assertEqual(window.collect_settings()['gamma'], 1.6)
        self.assertEqual(window.collect_settings()['oversized_policy'], 'error')
        self.assertEqual(FACTORY_DEFAULTS['gamma'], 1.2)

    def test_valid_saved_values_are_not_silently_clamped_or_rounded(self):
        self.project.settings.update(gamma=12.123456789, target_size=16, buffer_kernel_size=151)
        self.project.save()
        window = self.window()
        self.assertEqual(window.collect_settings()['gamma'], 12.123456789)
        self.assertEqual(window._settings_fields['target_size'].value(), 16)
        self.assertEqual(window._settings_fields['buffer_kernel_size'].value(), 151)
        window.close()
        saved = Project.load(self.project.path).settings
        self.assertEqual(saved['gamma'], 12.123456789)
        self.assertEqual(saved['target_size'], 16)
        self.assertEqual(saved['buffer_kernel_size'], 151)

    def test_adding_a_source_keeps_unsaved_draft_but_saves_only_valid_settings(self):
        import numpy as np
        import tifffile
        source = self.root/'source.tif'
        tifffile.imwrite(source, np.zeros((32, 40), dtype=np.uint8), metadata={'axes':'YX'})
        window = self.window()
        window._settings_fields['gamma'].setValue(1.8)
        window._settings_fields['buffer_kernel_size'].setValue(6)
        with patch.object(QtWidgets.QFileDialog, 'getOpenFileNames', return_value=([str(source)], 'TIFF')):
            window.add_sources()
        self.assertEqual(window.collect_settings()['gamma'], 1.8)
        self.assertEqual(window.collect_settings()['buffer_kernel_size'], 6)
        saved = Project.load(self.project.path)
        self.assertEqual(saved.settings['gamma'], 1.2)
        self.assertEqual(saved.settings['buffer_kernel_size'], 5)
        self.assertEqual(len(saved.sources), 1)

    def test_badge_and_f1_open_the_relevant_parameter_without_hover(self):
        window = self.window()
        window.sidebar.setCurrentRow(1)
        dock = window._workspaces['preparation'].panels['settings']
        dock.widget().ensureWidgetVisible(window._settings_fields['gamma'])
        badge = next(label for label in window.findChildren(QtWidgets.QLabel, 'helpBadge')
                     if label.property('helpKey') == 'gamma')
        QtTest.QTest.mouseClick(badge, QtCore.Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(window._help_center._current_parameter, 'gamma')
        window._help_center.close()
        window.activateWindow()
        self.app.processEvents()
        window._settings_fields['gamma'].setFocus()
        QtTest.QTest.keyClick(window._settings_fields['gamma'], QtCore.Qt.Key.Key_F1)
        self.app.processEvents()
        self.assertTrue(window._help_center.isVisible())
        self.assertEqual(window._help_center._current_parameter, 'gamma')
        window._help_center.close()
        dock.setFloating(True)
        dock.activateWindow()
        dock.widget().ensureWidgetVisible(window._settings_fields['gamma'])
        QtTest.QTest.qWait(40)
        window._settings_fields['gamma'].setFocus()
        self.app.processEvents()
        QtTest.QTest.keyClick(window._settings_fields['gamma'], QtCore.Qt.Key.Key_F1)
        self.app.processEvents()
        self.assertTrue(window._help_center.isVisible())
        self.assertEqual(window._help_center._current_parameter, 'gamma')

    def test_hebrew_keeps_bad_draft_safe_and_numbers_and_images_left_to_right(self):
        window = self.window()
        window._settings_fields['buffer_kernel_size'].setValue(6)
        window.set_language('he')
        self.app.processEvents()
        self.assertEqual(window.language, 'he')
        self.assertEqual(window.layoutDirection(), QtCore.Qt.LayoutDirection.RightToLeft)
        self.assertEqual(window._settings_fields['gamma'].layoutDirection(), QtCore.Qt.LayoutDirection.LeftToRight)
        self.assertEqual(window.object_view.view.layoutDirection(), QtCore.Qt.LayoutDirection.LeftToRight)
        self.assertEqual(window._settings_fields['gamma'].locale().name(), 'he_IL')
        self.assertEqual(window._settings_fields['buffer_kernel_size'].value(), 6)
        self.assertFalse(window.save_button.isEnabled())
        window.show_help('buffer_kernel_size')
        self.assertEqual(window._help_center.language, 'he')
        self.assertEqual(window._help_center.layoutDirection(), QtCore.Qt.LayoutDirection.RightToLeft)
        window.close()
        self.assertEqual(Project.load(self.project.path).settings['buffer_kernel_size'], 5)
        reopened = self.window(Project.load(self.project.path), language=None)
        self.assertEqual(reopened.language, 'he')


if __name__ == '__main__':
    unittest.main()
