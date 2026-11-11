"""Startup remembers usable projects and keeps the default fallback safe."""
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from app import _open_startup_window
from src.desktop import branding
from src.desktop.i18n import get_language, set_language
from src.desktop.project import LAST_PROJECT_KEY, Project
from src.desktop.qt import QtCore, QtWidgets


class DesktopStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='desktop_startup_')
        self.addCleanup(temp.cleanup)
        self.addCleanup(set_language, get_language())
        self.root = Path(temp.name)
        self.preferences = QtCore.QSettings(str(self.root / 'preferences.ini'), QtCore.QSettings.Format.IniFormat)
        self.default = self.root / 'default' / 'project.json'
        self.study = Project.create(self.root / 'study' / 'project.json', name='Study')

    @contextmanager
    def open_window(self, **options):
        window = _open_startup_window(self.default, self.preferences, language='en', **options)
        try:
            yield window
        finally:
            window.close()
            window.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(window, QtCore.QEvent.Type.DeferredDelete)

    def test_explicit_project_takes_precedence_then_last_selection_is_restored(self):
        other = Project.create(self.root / 'other' / 'project.json', name='Other')
        self.preferences.setValue(LAST_PROJECT_KEY, other.path)
        with self.open_window(explicit_path=self.study.path) as window:
            self.assertEqual(window.project.path, self.study.path)
        with self.open_window() as window:
            self.assertEqual(window.project.path, self.study.path)
            window._switch_project(other)
            self.assertEqual(self.preferences.value(LAST_PROJECT_KEY), other.path)
        with self.open_window() as window:
            self.assertEqual(window.project.path, other.path)
        self.assertFalse(self.default.exists())

    def test_missing_corrupt_and_locked_projects_fall_back_without_forgetting_them(self):
        missing = self.root / 'missing' / 'project.json'
        corrupt = self.root / 'corrupt.json'
        corrupt.write_text('[]', encoding='utf-8')
        lock = QtCore.QLockFile(self.study.path + '.lock')
        self.assertTrue(lock.tryLock(0))
        try:
            for path in (missing, corrupt, Path(self.study.path)):
                with self.subTest(path=path):
                    self.preferences.setValue(LAST_PROJECT_KEY, str(path))
                    with self.open_window() as window:
                        self.assertEqual(Path(window.project.path), self.default)
                        self.assertIn('Opened the default project', window.statusBar().currentMessage())
                    self.assertEqual(self.preferences.value(LAST_PROJECT_KEY), str(path))
        finally:
            lock.unlock()
        self.assertFalse(missing.exists())
        self.assertEqual(corrupt.read_text(encoding='utf-8'), '[]')

    def test_smoke_test_uses_default_and_preserves_the_remembered_project(self):
        self.preferences.setValue(LAST_PROJECT_KEY, self.study.path)
        with self.open_window(smoke_test=True) as window:
            self.assertEqual(Path(window.project.path), self.default)
        self.assertEqual(self.preferences.value(LAST_PROJECT_KEY), self.study.path)

    def test_png_renders_if_the_ico_cannot_be_decoded(self):
        shutil.copyfile(branding.ASSET_DIRECTORY / 'solodata.png', self.root / 'solodata.png')
        (self.root / 'solodata.ico').write_bytes(b'invalid icon')
        with patch.object(branding, 'ASSET_DIRECTORY', self.root):
            self.assertFalse(branding.app_icon().pixmap(32, 32).isNull())


if __name__ == '__main__':
    unittest.main()
