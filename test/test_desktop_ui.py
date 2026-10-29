"""Offscreen tests for UI state, the worker protocol and durable requests."""

import csv
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from src.desktop.qt import QtCore, QtWidgets
    from src.desktop.main_window import MainWindow
    from src.desktop.widgets import CsvTable, ImageViewer
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


@unittest.skipUnless(QT_AVAILABLE, "Qt binding is not installed")
class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        from src.desktop.project import Project
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name)
        self.project = Project.create(self.folder / "project.json", "Контрольный проект")
        self.preferences = QtCore.QSettings(str(self.folder / "preferences.ini"), QtCore.QSettings.Format.IniFormat)
        self.window = MainWindow(self.project, language="ru", preferences=self.preferences)

    def tearDown(self):
        if self.window.process is not None:
            # No production entry point is launched by these tests.
            self.window.process.kill()
            self.window.process.waitForFinished(5000)
            self.app.processEvents()
        self.window.close()
        QtCore.QThreadPool.globalInstance().waitForDone(5000)
        self.app.processEvents()
        self.temporary.cleanup()

    def pump_until(self, predicate, timeout=25):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(.01)
        self.fail("Timed out waiting for Qt worker/preview")

    def add_tiff(self):
        import numpy as np
        import tifffile
        from src.desktop import service
        path = self.folder / "small.tif"
        pixels = np.zeros((48, 64), np.uint8)
        pixels[16:31, 12:52] = 200
        tifffile.imwrite(path, pixels, metadata={"axes": "YX"})
        service.add_sources(self.project, [path])
        self.window.refresh_project()
        return self.project.sources[0]

    def test_empty_project_and_settings_are_valid_without_processing(self):
        from src.app_settings import PipelineSettings
        self.assertEqual(self.window.pages.count(), 5)
        self.assertEqual(self.window.source_table.rowCount(), 0)
        self.assertEqual(self.window.dataset_combo.count(), 0)
        self.assertIn("Выберите набор", self.window.results_summary.text())
        self.assertIsNone(self.window.process)
        values = self.window.collect_settings()
        self.assertIsNone(values["pixel_size_um"])
        self.assertEqual(PipelineSettings.from_dict(values).target_size, 1500)
        self.window._settings_fields["pixel_size_um"].setValue(.42)
        self.window.save_project()
        from src.desktop.project import Project
        self.assertAlmostEqual(Project.load(self.project.path).settings["pixel_size_um"], .42)

    def test_selected_sources_control_request_not_current_row(self):
        source = self.add_tiff()
        self.assertEqual(self.window.selected_source_ids(), [source["id"]])
        self.window.source_table.item(0, 0).setCheckState(QtCore.Qt.CheckState.Unchecked)
        self.assertEqual(self.window.selected_source_ids(), [])
        request = self.window.build_request("prepare", source_ids=[source["id"]], settings=self.window.collect_settings())
        self.assertEqual(request["project_path"], self.project.path)
        self.assertEqual(request["source_ids"], [source["id"]])
        self.assertEqual(request["settings"]["channel"], 0)
        self.assertEqual(request["settings"]["plane"], 0)

    def test_progress_error_and_no_result_do_not_report_success(self):
        self.window.handle_worker_event({"type": "progress", "stage": "features", "completed": 2, "total": 4})
        self.assertEqual(self.window.progress.value(), 50)
        self.assertIn("2 / 4", self.window.job_status.text())
        self.window.handle_worker_event({"type": "error", "message": "invalid annotation"})
        self.assertIn("Ошибка", self.window.job_status.text())
        self.window.handle_worker_event({"type": "result", "status": "completed", "summary": {"objects": 3}})
        # An error followed by a result is still an unsuccessful job.
        self.window.process = QtCore.QProcess(self.window)
        self.window._process_finished(0, QtCore.QProcess.ExitStatus.NormalExit)
        self.assertIn("Ошибка", self.window.job_status.text())
        self.assertEqual(self.window.progress.value(), 0)
        self.window._job_error = self.window._job_result = None
        self.window.process = QtCore.QProcess(self.window)
        self.window._process_finished(0, QtCore.QProcess.ExitStatus.NormalExit)
        self.assertIn("Ошибка", self.window.job_status.text())
        self.assertIn("не подтвердил", self.window.log.toPlainText())

    def test_cancel_flag_and_cancelled_exit_code_are_supported(self):
        self.window.process = QtCore.QProcess(self.window)
        self.window.request_path = self.folder / "request.json"
        self.window.cancel_job()
        self.assertTrue(Path(str(self.window.request_path) + ".cancel").is_file())
        self.assertIn("Останавливается", self.window.job_status.text())
        self.window._job_result = {"type": "result", "status": "cancelled"}
        self.window._process_finished(2, QtCore.QProcess.ExitStatus.NormalExit)
        self.assertIn("Остановлено", self.window.job_status.text())
        self.assertNotIn("Ошибка", self.window.job_status.text())
        self.assertEqual(self.window.progress.value(), 0)

    def test_process_preview_uses_real_request_and_returns_bounded_images(self):
        source = self.add_tiff()
        options = self.window.collect_settings()
        options["tophat_radius"] = 3
        options["bridge_kernel_size"] = 3
        options["buffer_kernel_size"] = 3
        self.assertTrue(self.window.start_job("preview", source_id=source["id"], settings=options))
        saved_request = json.loads(self.window.request_path.read_text(encoding="utf-8"))
        self.assertEqual(saved_request["action"], "preview")
        self.assertFalse(self.window.dataset_combo.isEnabled())
        self.pump_until(lambda: self.window.process is None)
        self.assertIn("завершено", self.window.job_status.text(), self.window.log.toPlainText())
        self.assertEqual(self.window.progress.value(), 100)
        self.assertTrue(Path(self.window.filtered_preview.filename).is_file())
        self.pump_until(lambda: self.window.filtered_preview.original_size != (0, 0))
        self.assertEqual(self.window.filtered_preview.original_size, (64, 48))
        self.assertFalse(self.window.dataset_combo.isEnabled())
        self.assertEqual(self.window.project.datasets, [])

    def test_overview_click_is_submitted_to_worker_with_source_coordinates(self):
        self.window._manifest = {"image_shape": [200, 400]}
        self.window.overview_view._original_size = (100, 50)
        with patch.object(self.window, "selected_dataset", return_value={"id": "dataset"}), \
             patch.object(self.window, "start_job", return_value=True) as start:
            self.window._overview_clicked(25, 10)
        start.assert_called_once_with("pick_tile", dataset_id="dataset", x=100, y=40)

    def test_project_lock_prevents_two_windows_and_mutations_are_disabled(self):
        from src.desktop.project import Project
        with self.assertRaisesRegex(RuntimeError, "другом окне"):
            MainWindow(Project.load(self.project.path), language="ru", preferences=self.preferences)
        self.window._set_busy(True)
        self.assertTrue(all(not button.isEnabled() for button in self.window._job_buttons))
        self.assertTrue(all(not field.isEnabled() for field in self.window._settings_fields.values()))
        self.window._set_busy(False)

    def test_csv_filter_export_preserves_source_columns_and_selected_row(self):
        filename = self.folder / "features.csv"
        with filename.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["Tile_Name", "Object_ID", "Class_Name", "Branch_Points"])
            writer.writeheader()
            writer.writerows([
                {"Tile_Name": "sample_tile_0001", "Object_ID": 1, "Class_Name": "Curve", "Branch_Points": 5},
                {"Tile_Name": "sample_tile_0002", "Object_ID": 2, "Class_Name": "Sphere", "Branch_Points": 0},
            ])
        table = self.window.results_table
        table.load_csv(filename)
        table.class_filter.setCurrentIndex(table.class_filter.findData("Curve"))
        self.assertEqual(len(table.visible_rows), 1)
        self.assertEqual(table.table.horizontalHeaderItem(3).text(), "Пиксели ветвления")
        selection = []
        table.row_selected.connect(selection.append)
        table.table.selectRow(0)
        self.assertEqual(selection[0]["Object_ID"], "1")
        exported = self.folder / "selection.csv"
        self.assertEqual(table.export_filtered(exported), 1)
        with exported.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["Class_Name"], "Curve")
        self.assertIn("Branch_Points", rows[0])

    def test_uint16_preview_is_normalized_and_polygon_overlay_survives_async_load(self):
        from PIL import Image
        import numpy as np
        filename = self.folder / "native16.png"
        Image.fromarray(np.full((60, 80), 32768, dtype=np.uint16)).save(filename)
        viewer = self.window.native_view
        viewer.set_image(filename)
        viewer.set_polygons([{"class_id": 1, "points": [(0, 0), (.9, 0), (.9, .9)]}])
        self.pump_until(lambda: viewer.original_size != (0, 0))
        self.assertEqual(viewer.original_size, (80, 60))
        self.assertEqual(len(viewer._overlay_items), 1)
        image = viewer._pixmap_item.pixmap().toImage()
        self.assertEqual(image.pixelColor(30, 20).red(), 128)

    def test_english_default_language_switch_and_isolated_persistence(self):
        from src.desktop.project import Project
        second = Project.create(self.folder / "english_project.json", "FiberLab")
        window = MainWindow(second, preferences=self.preferences)
        try:
            self.assertEqual(window.language, "en")
            self.assertEqual(window.page_title.text(), "Sources")
            self.assertEqual(window.dataset_combo.placeholderText(), "No prepared datasets")
            self.assertFalse(window.dataset_combo.isEnabled())
            self.assertIn("prepare", window.dataset_status.text().lower())
            self.assertEqual(window.build_request("preview")["language"], "en")
            window._settings_fields["gamma"].setValue(1.6)
            self.assertEqual(window._settings_fields["gamma"].locale().name(), "en_US")
            self.assertIn(".", window._settings_fields["gamma"].text())
            window.sidebar.setCurrentRow(1)
            window.set_language("ru")
            self.assertEqual(window.page_title.text(), "Подготовка")
            self.assertEqual(window.dataset_combo.placeholderText(), "Нет подготовленных наборов")
            self.assertAlmostEqual(window._settings_fields["gamma"].value(), 1.6)
            self.assertEqual(window._settings_fields["gamma"].locale().name(), "ru_RU")
            self.assertIn(",", window._settings_fields["gamma"].text())
            self.assertEqual(self.preferences.value("language"), "ru")
            self.assertNotIn("language", window.collect_settings())
            self.assertEqual(window.build_request("preview")["language"], "ru")
        finally:
            window.close()
        reopened = MainWindow(Project.load(second.path), preferences=self.preferences)
        try:
            self.assertEqual(reopened.language, "ru")
            self.assertEqual(reopened.page_title.text(), "Исходники")
        finally:
            reopened.close()

    def test_every_visible_parameter_has_scientific_hover_help_and_badge(self):
        from src.desktop.help import help_text
        for key, field in self.window._settings_fields.items():
            self.assertEqual(field.property("helpKey"), key)
            self.assertTrue(field.toolTip(), key)
        self.assertGreaterEqual(len(self.window.findChildren(QtWidgets.QLabel, "helpBadge")), len(self.window._settings_fields))
        for widget in (self.window.dataset_combo, self.window.language_combo, self.window.tile_search,
                       self.window.tile_filter, self.window.exclude_specs, self.window.labels_mode,
                       self.window.results_table.class_filter, self.window.results_table.search,
                       self.window.classifier.class_combo):
            self.assertTrue(widget.toolTip())
        self.assertIn("x^(1/gamma)", help_text("gamma", "en"))
        self.assertIn("gamma > 1", help_text("gamma", "ru"))
        self.assertIn("Otsu > 10", help_text("min_clean_threshold", "en"))
        self.assertIn("native", help_text("min_sub_object_area", "en"))

    def test_empty_dataset_stays_disabled_after_busy_and_names_distinguish_runs(self):
        from src.desktop.project import Project
        self.assertEqual(self.window.dataset_combo.count(), 0)
        self.window._set_busy(True)
        self.window._set_busy(False)
        self.assertFalse(self.window.dataset_combo.isEnabled())
        self.project.datasets = [
            {"id": "a123456", "name": "same", "path": str(self.folder / "one"), "status": "ready"},
            {"id": "b123456", "name": "same", "path": str(self.folder / "two"), "status": "awaiting_review"},
        ]
        self.project.active_dataset_id = "b123456"
        with patch.object(self.window, "refresh_tiles"), patch.object(self.window, "check_labels"), patch.object(self.window, "refresh_results"):
            self.window.refresh_project()
            self.assertEqual(self.window.dataset_combo.currentData(), "b123456")
            self.assertTrue(self.window.dataset_combo.isEnabled())
            self.assertNotEqual(self.window.dataset_combo.itemText(0), self.window.dataset_combo.itemText(1))
            self.window.dataset_combo.setCurrentIndex(0)
            self.assertEqual(Project.load(self.project.path).active_dataset_id, "a123456")

    def test_open_prepared_tiles_dialog_describes_specific_dataset_folder(self):
        with patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value=str(self.folder / "dataset")) as dialog, \
             patch.object(self.window, "start_job", return_value=True) as start:
            self.window.connect_dataset()
        self.assertIn("конкретного", dialog.call_args.args[1])
        start.assert_called_once_with("connect", dataset_path=str(self.folder / "dataset"))

    def test_training_export_stays_visible_outside_classification_scroll(self):
        self.window.sidebar.setCurrentRow(4)
        self.window.show_log.setChecked(False)
        self.window.show()
        self.app.processEvents()
        button = self.window.classifier.export_button
        self.assertIsNot(button.parentWidget(), self.window.classifier)
        self.assertTrue(button.isVisible())
        visible_rect = QtCore.QRect(button.mapTo(self.window, QtCore.QPoint(0, 0)), button.size())
        self.assertTrue(self.window.rect().contains(visible_rect))
        self.window.resize(1050, 710)
        self.app.processEvents()
        self.assertEqual(self.window.minimumSize(), QtCore.QSize(1050, 710))
        visible_rect = QtCore.QRect(button.mapTo(self.window, QtCore.QPoint(0, 0)), button.size())
        self.assertTrue(self.window.rect().contains(visible_rect))
        self.window._manual_report = {"current": True, "assigned": 1}
        self.window._set_busy(True)
        self.assertFalse(button.isEnabled())
        self.window._set_busy(False)
        self.assertTrue(button.isEnabled())


if __name__ == "__main__":
    unittest.main()
