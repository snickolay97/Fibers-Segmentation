"""Typing a class changes one target without reopening or rebuilding tables."""
import importlib
import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from src.desktop.qt import QtCore, QtWidgets
from src.desktop.main_window import MainWindow
from src.desktop import service
from src.desktop.i18n import get_language, set_language
from src.desktop.help_center import HelpCenter


class IncrementalLabelUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.fixture=importlib.import_module('test_project_service').ProjectServiceTests()
        self.fixture.setUp(); self.addCleanup(self.fixture.tearDown)
        self.project=self.fixture.project; self.dataset=self.fixture.prepared()
        service.extract(self.project,self.dataset['id'],labels_mode='auto')
        self.addCleanup(set_language,get_language())
        preferences=QtCore.QSettings(str(self.fixture.root/'label_ui.ini'),QtCore.QSettings.Format.IniFormat)
        self.window=MainWindow(self.project,language='en',preferences=preferences)
        self.window.sidebar.setCurrentRow(4)
        self.window.results_table.table.selectRow(0)
        self.addCleanup(self.dispose,self.window)

    def dispose(self,widget):
        widget.close(); widget.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(widget,QtCore.QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_assignment_has_no_full_csv_reload_or_view_reset(self):
        window=self.window; row=window.results_table.selected_row(); self.assertIsNotNone(row)
        # Warm the database as the first conversion necessarily imports objects.
        window.assign_manual_class('particle')
        key=str(row['Tile_Name'])+'/'+str(row['Object_ID'])
        before=Path(self.project.path).read_bytes()
        with (patch.object(window.results_table,'set_manual_labels',side_effect=AssertionError('full table')),
              patch.object(window.results_table,'apply_filter',side_effect=AssertionError('table reset')),
              patch.object(window.object_gallery,'set_manual_labels',side_effect=AssertionError('full gallery')),
              patch.object(window.object_gallery,'apply_filter',side_effect=AssertionError('gallery reset')),
              patch.object(window.analytics,'set_data',side_effect=AssertionError('CSV reload')),
              patch.object(window,'_error',side_effect=AssertionError('save failed'))):
            window.assign_manual_class('fiber')
        self.assertEqual(window.results_table.selected_row()['Manual_Class'],'fiber')
        self.assertEqual(window._manual_report['labels'][key]['Manual_Class'],'fiber')
        self.assertEqual(window.object_gallery._labels[key]['Manual_Class'],'fiber')
        self.assertEqual(Path(self.project.path).read_bytes(),before)
        self.assertEqual(window.analytics.table._manual_rows_by_key[key]['Manual_Class'],'fiber')
        from src.desktop.database_dialog import DatabaseDialog
        dialog=DatabaseDialog(self.project,window)
        try:
            dialog.kind.setCurrentIndex(dialog.kind.findData('history'))
            self.assertEqual(dialog.report['counts']['history'],len(self.project.history))
            self.assertEqual(dialog.table.item(dialog.table.rowCount()-1,1).text(),'assign_object_class')
        finally:
            self.dispose(dialog)

    def test_snapshot_button_exports_latest_targets(self):
        window=self.window; window.assign_manual_class('fiber')
        target=self.fixture.root/'exports'/'manual_object_labels.json'
        with patch.object(QtWidgets.QFileDialog,'getSaveFileName',return_value=(str(target),'JSON (*.json)')):
            window.classifier.snapshot_export_button.click()
        import json
        self.assertEqual(len(json.loads(target.read_bytes())['labels']),1)

    def test_help_explains_authority_migration_and_restore(self):
        helper=HelpCenter(); self.addCleanup(self.dispose,helper)
        for language in ('en','ru','he'):
            helper.retranslate(language); helper.open_topic('manual_types')
            text=helper.browser.toPlainText()
            self.assertIn('manual_object_labels.sqlite3',text)
            self.assertIn('manual_object_labels_storage.json',text)
            self.assertIn('JSON',text)


if __name__=='__main__': unittest.main()
