"""Source selection, automatic calibration and manual intent survive UI changes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import time
import unittest
import numpy as np
import tifffile
from src.default_settings import FACTORY_DEFAULTS
from src.desktop.qt import QtCore,QtWidgets
from src.desktop.project import Project
from src.desktop.main_window import MainWindow
from src.desktop.widgets import image_pool
from src.desktop import service


class SourceContextUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.project=Project.create(self.root/'project.json')
        for name,scale,shape,axes in [('first',.433578,(48,60),'YX'),('second',.7,(48,60),'YX'),('stack',.4,(3,48,60),'ZYX')]:
            path=self.root/(name+'.ome.tif')
            tifffile.imwrite(path,np.zeros(shape,np.uint8),ome=True,photometric='minisblack',
                metadata=dict(axes=axes,PhysicalSizeX=scale,PhysicalSizeY=scale))
            service.add_sources(self.project,[path])
        self.preferences=QtCore.QSettings(str(self.root/'ui.ini'),QtCore.QSettings.Format.IniFormat)
        self.window=MainWindow(self.project,language='en',preferences=self.preferences)

    def tearDown(self):
        self.window.close()
        image_pool().waitForDone(5000)
        self.window.deleteLater()
        self.app.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def test_selected_tiff_shows_its_own_scale_without_turning_it_into_a_batch_override(self):
        field=self.window._settings_fields['pixel_size_um']
        self.assertAlmostEqual(field.value(),.433578)
        self.assertTrue(field.isReadOnly())
        self.assertIsNone(self.window.collect_settings()['pixel_size_um'])
        self.window.preview_source_combo.setCurrentIndex(1)
        self.assertEqual(field.value(),.7)
        self.assertEqual(self.window.source_table.currentRow(),1)
        self.assertTrue(self.window._settings_fields['plane'].isReadOnly())
        self.window.preview_source_combo.setCurrentIndex(2)
        self.assertFalse(self.window._settings_fields['plane'].isReadOnly())
        self.assertIsNone(FACTORY_DEFAULTS['pixel_size_um'])

    def test_manual_override_and_language_changes_preserve_the_selected_source(self):
        self.window.preview_source_combo.setCurrentIndex(1)
        self.window.calibration_mode_combo.setCurrentIndex(self.window.calibration_mode_combo.findData('manual'))
        self.window._settings_fields['pixel_size_um'].setValue(.25)
        for language in ('ru','he','en'):
            self.window.set_language(language)
            self.assertEqual(self.window.preview_source_combo.currentData(),self.project.sources[1]['id'])
            self.assertEqual(self.window.collect_settings()['pixel_size_um'],.25)
            self.assertFalse(self.window._settings_fields['pixel_size_um'].isReadOnly())
        self.window.save_project()
        saved=Project.load(self.project.path)
        self.assertEqual(saved.settings['pixel_size_um'],.25)
        self.assertEqual(saved._extra_fields['calibration_mode'],'manual')

    def test_reference_shows_effective_tiff_value_and_factory_unset_separately(self):
        self.window.show_help('pixel_size_um')
        self.assertEqual(self.window._help_center.current_settings['pixel_size_um'],.433578)
        self.assertIsNone(self.window.collect_settings()['pixel_size_um'])

    def test_changing_tiff_clears_previews_of_the_previous_source(self):
        source=self.project.sources[0]
        for viewer in (self.window.input_preview,self.window.filtered_preview,self.window.protective_preview):
            viewer.set_image(source['path'])
        self.window.show()
        self.window.sidebar.setCurrentRow(1)
        for index, viewer in enumerate((self.window.input_preview, self.window.filtered_preview,
                                        self.window.protective_preview)):
            self.window.preview_tabs.setCurrentIndex(index)
            self.app.processEvents()
            self.assertTrue(viewer.isVisible())
        self.window.preview_tabs.setCurrentIndex(self.window.preview_tabs.count() - 1)
        self.app.processEvents()
        comparison = self.window.preview_comparison
        self.assertTrue(comparison.widget(0).isAncestorOf(self.window.input_preview))
        self.assertTrue(comparison.widget(1).isAncestorOf(self.window.filtered_preview))
        self.assertTrue(self.window.input_preview.isVisible())
        self.assertTrue(self.window.filtered_preview.isVisible())
        self.window.preview_source_combo.setCurrentIndex(1)
        for viewer in (self.window.input_preview,self.window.filtered_preview,self.window.protective_preview):
            self.assertEqual(viewer.filename,'')
        comparison.setSizes([450, 220])
        self.window.set_language('he')
        self.app.processEvents()
        comparison = self.window.preview_comparison
        self.assertEqual(self.window.preview_tabs.currentWidget(), comparison)
        self.assertTrue(comparison.widget(0).isAncestorOf(self.window.input_preview))
        self.assertGreater(comparison.sizes()[0], comparison.sizes()[1])

    def test_quick_source_and_saved_previews_follow_the_selected_tiff(self):
        self.window.show()
        self.window.sidebar.setCurrentRow(1)
        deadline = time.monotonic() + 5
        while self.window.input_preview.original_size == (0, 0) and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertEqual(self.window.input_preview.original_size, (60, 48))
        self.assertEqual(self.window.input_preview.ruler.scale, (1, 1, .433578))
        self.assertIn('Calculate the preview', self.window.preparation_preview_note.text())
        self.assertFalse(self.window.filtered_preview.filename)

        saved = service.preview(self.project, source_id=self.project.sources[0]['id'])
        self.window.refresh_project()
        viewers = (self.window.input_preview, self.window.filtered_preview, self.window.protective_preview)
        paths = [saved[key] for key in ('input_path', 'filtered_path', 'mask_path')]
        self.assertEqual([viewer.filename for viewer in viewers], paths)
        self.window.preview_source_combo.setCurrentIndex(1)
        self.assertTrue(all(not viewer.filename for viewer in viewers))
        self.window.preview_source_combo.setCurrentIndex(0)
        self.assertEqual([viewer.filename for viewer in viewers], paths)
        self.window.close()
        image_pool().waitForDone(5000)
        self.window.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        self.window = MainWindow(Project.load(self.project.path), language='en', preferences=self.preferences)
        viewers = (self.window.input_preview, self.window.filtered_preview, self.window.protective_preview)
        self.assertEqual([viewer.filename for viewer in viewers], paths)
