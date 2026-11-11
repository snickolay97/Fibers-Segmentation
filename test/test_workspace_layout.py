"""User-visible panel detachment, stage switching and layout recovery."""
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from src.desktop.qt import QtCore, QtWidgets
from src.desktop.workspace import DockWorkspace


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.preferences = QtCore.QSettings(str(Path(self.temporary.name) / 'layout.ini'), QtCore.QSettings.Format.IniFormat)
        self.workspace = self.build_workspace()
        self.workspace.resize(900, 650)
        self.workspace.show()
        self.workspace.activate()
        self.app.processEvents()

    def build_workspace(self):
        workspace = DockWorkspace('test', self.preferences)
        workspace.add_panel('left', 'Processing settings', QtWidgets.QLabel('Settings'))
        workspace.add_panel('right', 'Image previews', QtWidgets.QLabel('Image'), QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        workspace.finish_layout()
        return workspace

    def tearDown(self):
        self.workspace.dispose()
        self.workspace.close()
        self.workspace.deleteLater()
        self.app.processEvents()
        self.temporary.cleanup()

    def test_detached_panel_hides_with_stage_and_returns_when_activated(self):
        dock = self.workspace.panels['right']
        dock.setFloating(True)
        self.app.processEvents()
        self.assertTrue(dock.isVisible())
        self.workspace.deactivate()
        self.assertTrue(dock.isHidden())
        self.workspace.activate()
        self.assertTrue(dock.isFloating())
        self.assertTrue(dock.isVisible())

    def test_layout_survives_reopen_even_if_floating_stage_is_inactive(self):
        dock = self.workspace.panels['right']
        dock.setFloating(True)
        dock.resize(480, 360)
        self.workspace.deactivate()
        self.workspace.save_layout()
        reopened = self.build_workspace()
        try:
            reopened.show()
            reopened.activate()
            self.app.processEvents()
            self.assertTrue(reopened.panels['right'].isFloating())
            self.assertTrue(reopened.panels['right'].isVisible())
            self.assertGreaterEqual(reopened.panels['right'].width(), 400)
        finally:
            reopened.dispose()
            reopened.close()
            reopened.deleteLater()

    def test_closed_panel_is_recoverable_from_menu_and_reset_redocks_it(self):
        dock = self.workspace.panels['right']
        dock.setFloating(True)
        dock.close()
        self.assertTrue(dock.isHidden())
        menu = QtWidgets.QMenu()
        self.workspace.populate_menu(menu)
        dock.toggleViewAction().trigger()
        self.assertTrue(dock.isVisible())
        menu.actions()[-1].trigger()
        self.assertFalse(dock.isFloating())
        self.assertTrue(dock.isVisible())

    def test_title_controls_maximize_restore_and_return_without_reset(self):
        dock = self.workspace.panels['right']
        title = dock.titleBarWidget()
        title.dock_button.click()
        self.app.processEvents()
        self.assertTrue(dock.isFloating())
        self.assertTrue(title.maximize_button.isVisible())
        title.maximize_button.click()
        self.app.processEvents()
        self.assertTrue(dock.isMaximized())
        title.maximize_button.click()
        self.app.processEvents()
        self.assertFalse(dock.isMaximized())
        title.maximize_button.click()
        title.dock_button.click()
        self.app.processEvents()
        self.assertFalse(dock.isFloating())
        self.assertFalse(dock.isMaximized())
        self.assertTrue(dock.isVisible())

    def test_drop_target_returns_floating_panel_and_keeps_other_panel(self):
        dock = self.workspace.panels['right']
        other = self.workspace.panels['left']
        dock.setFloating(True)
        self.app.processEvents()
        point = self.workspace.mapToGlobal(other.geometry().center())
        self.workspace.preview_drop(dock, point)
        self.assertTrue(self.workspace._drop_preview.isVisible())
        self.assertTrue(self.workspace.dock_from_drop(dock, point))
        self.app.processEvents()
        self.assertFalse(dock.isFloating())
        self.assertTrue(other.isVisible())
        self.assertTrue(dock.isVisible())

    def test_drop_outside_or_in_inactive_stage_keeps_panel_floating(self):
        dock = self.workspace.panels['right']
        dock.setFloating(True)
        self.app.processEvents()
        self.assertFalse(self.workspace.dock_from_drop(dock, QtCore.QPoint(-10000, -10000)))
        self.assertTrue(dock.isFloating())
        self.workspace.deactivate()
        point = self.workspace.mapToGlobal(self.workspace.rect().center())
        self.assertFalse(self.workspace.dock_from_drop(dock, point))
        self.assertTrue(dock.isFloating())


if __name__ == '__main__':
    unittest.main()
