"""Owners can inspect and recover metadata without saving an unfinished draft."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from src.desktop.i18n import set_language, get_language
from src.desktop.project import Project
from src.desktop.qt import QtCore, QtWidgets
from src.desktop.database_dialog import DatabaseDialog
from src.desktop.help_center import HelpCenter


class DatabaseUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='database_ui_')
        self.addCleanup(self.temp.cleanup)
        self.project = Project.create(Path(self.temp.name) / 'project.json')
        self.language = get_language()
        self.addCleanup(set_language, self.language)
        set_language('en')

    def dispose(self, widget):
        # Destroy child widgets while QApplication still exists (as app.py does).
        widget.close()
        widget.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(widget, QtCore.QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_paged_browse_uses_saved_values_and_repairs_missing_catalog(self):
        self.project.datasets = [dict(id=str(i), name='Dataset ' + str(i), status='ready') for i in range(205)]
        self.project.save()
        self.project.datasets[0]['name'] = 'Unsaved draft'
        before = Path(self.project.path).read_bytes()
        dialog = DatabaseDialog(self.project)
        self.addCleanup(self.dispose, dialog)
        self.assertEqual(dialog.table.rowCount(), 100)
        self.assertEqual(dialog.table.item(0, 1).text(), 'Dataset 0')
        dialog.next.click()
        self.assertEqual(dialog.table.item(0, 0).text(), '100')
        dialog.next.click()
        self.assertEqual(dialog.table.rowCount(), 5)
        self.assertFalse(dialog.next.isEnabled())
        self.project.catalog().path.unlink()
        dialog.refresh()
        self.assertFalse(dialog.backup_button.isEnabled())
        dialog.sync_button.click()
        self.assertEqual(dialog.report['state'], 'current')
        self.assertEqual(Path(self.project.path).read_bytes(), before)
        dialog._show_help()
        self.assertIs(dialog._help_center.parentWidget(), dialog)
        self.assertIn('METADATA_ONLY', dialog._help_center.browser.toPlainText())

    def test_localized_help_explains_scope_and_actual_controls(self):
        help_window = HelpCenter()
        self.addCleanup(self.dispose, help_window)
        for language, words in (
            ('en', ('Refresh catalog', 'Rebuild catalog', 'METADATA_ONLY', '100', 'SHA-256')),
            ('ru', ('Обновить каталог', 'Пересоздать каталог', 'METADATA_ONLY', '100', 'SHA-256')),
            ('he', ('עדכון הקטלוג', 'בנייה מחדש', 'METADATA_ONLY', '100', 'SHA-256')),
        ):
            help_window.retranslate(language)
            help_window.open_topic('database')
            text = help_window.browser.toPlainText()
            for word in words:
                self.assertIn(word, text)
            set_language(language)
            dialog = DatabaseDialog(self.project)
            if language != 'en':
                self.assertNotEqual(dialog.sync_button.text(), 'Refresh catalog')
            self.dispose(dialog)

    def test_main_window_disables_maintenance_while_a_worker_is_busy(self):
        from src.desktop.main_window import MainWindow
        preferences = QtCore.QSettings(str(Path(self.temp.name) / 'ui.ini'), QtCore.QSettings.Format.IniFormat)
        preferences.setValue('language', 'en')
        window = MainWindow(self.project, preferences=preferences)
        self.addCleanup(self.dispose, window)
        window._set_busy(True)
        self.assertFalse(window.database_action.isEnabled())
        with patch('src.desktop.main_window.DatabaseDialog') as constructor:
            window.open_project_database()
            constructor.assert_not_called()
        window._set_busy(False)
        self.assertTrue(window.database_action.isEnabled())


if __name__ == '__main__':
    unittest.main()
