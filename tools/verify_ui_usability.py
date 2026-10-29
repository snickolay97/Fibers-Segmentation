"""Reproduce the desktop workflow on a temporary crop without editing data.

Run with the scientific Python from the repository root. Screenshots and a
verification report go to data/app_preview/usability_20261029. The real source
TIFF is opened read-only; the temporary project and its outputs are removed.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import tifffile
from src.desktop.qt import QtCore, QtWidgets
from src.desktop.main_window import MainWindow
from src.desktop.project import Project
from src.desktop.widgets import image_pool
from src.desktop import service


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    output = ROOT / 'data/app_preview/usability_20261029'
    output.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication([])
    stats = dict(source='G3, read-only crop 2048 × 2048', expert_labels_assigned=False)

    def pump(predicate, timeout=60):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            app.processEvents()
            if predicate():
                return
            time.sleep(.01)
        raise TimeoutError('UI verification timed out')

    def finish_thumbnails(window):
        # Only visible cards are decoded. The count depends on the panel size,
        # so wait for the bounded visible batches instead of a fixed total.
        for _ in range(4):
            app.processEvents()
            image_pool().waitForDone(3000)
            app.processEvents()

    source = ROOT / 'data/1_raw_large_images/FL01_G3_RGB_Red.tif'
    before = (source.stat().st_size, source.stat().st_mtime_ns)
    with tempfile.TemporaryDirectory(prefix='verification_', dir=output) as directory:
        base = Path(directory)
        mapping = tifffile.memmap(source)
        crop = np.array(mapping[7000:9048, 7000:9048], copy=True)
        mapping._mmap.close()
        del mapping
        sample = base / 'G3_crop.tif'
        tifffile.imwrite(sample, crop, photometric='rgb', metadata={'axes':'YXS'})
        del crop
        project = Project.create(base / 'project.json', 'G3 · UI verification')
        service.add_sources(project, [sample])
        preferences = QtCore.QSettings(str(base / 'preferences.ini'), QtCore.QSettings.Format.IniFormat)
        window = MainWindow(project, preferences=preferences)
        window.show()
        window.show_log.setChecked(False)
        window.source_table.selectRow(0)
        try:
            window._settings_fields['enable_gamma'].setChecked(False)
            window.preview_source()
            pump(lambda: window.process is None)
            assert window._job_error is None, window.log.toPlainText()
            pump(lambda: window.filtered_preview.original_size != (0, 0))
            window.preview_tabs.setCurrentIndex(1)
            scroll = window._workspaces['preparation'].panels['settings'].widget()
            scroll.ensureWidgetVisible(window._settings_fields['enable_gamma'])
            app.processEvents()
            window.grab().save(str(output / 'filters_en.png'))
            stats['filter_selection_preview'] = not window.collect_settings()['enable_gamma']
            window._settings_fields['enable_gamma'].setChecked(True)
            window._settings_fields['overview_size'].setValue(1200)
            for action, callback in (('prepare', window.prepare_sources),
                                     ('detect', window.detect_and_review)):
                start = time.monotonic()
                callback()
                assert window.process is not None
                pump(lambda: window.process is None)
                assert window._job_error is None, window.log.toPlainText()
                assert window._job_result['status'] == 'completed'
                stats[action + '_seconds'] = round(time.monotonic() - start, 2)
            dataset = window.selected_dataset()
            stats['tiles'] = len(service.tile_records(dataset))
            stats['objects'] = len(window.results_table.rows)
            scientific = Path(dataset['last_csv'])
            scientific_before = scientific.read_bytes()
            target = max(window.results_table.rows, key=lambda row: float(row['Aspect_Ratio']))
            window.object_gallery.select_object(target['Tile_Name'], target['Object_ID'])
            pump(lambda: window.object_view.original_size != (0, 0))
            finish_thumbnails(window)
            app.processEvents()
            window.grab().save(str(output / 'gallery_en.png'))
            dialog = window.object_view.open_fullscreen()
            assert dialog is not None
            app.processEvents()
            assert dialog.isFullScreen()
            dialog.grab().save(str(output / 'object_fullscreen.png'))
            window.object_view.close_fullscreen()
            dock = window._workspaces['results'].panels['preview']
            dock.setFloating(True)
            dock.resize(740, 550)
            app.processEvents()
            dock.grab().save(str(output / 'object_detached.png'))
            window.sidebar.setCurrentRow(1)
            assert dock.isHidden()
            window.sidebar.setCurrentRow(4)
            assert dock.isVisible()
            stats['detached_panel_stage_restore'] = True
            window._workspaces['results'].reset_layout()
            window.set_language('ru')
            pump(lambda: window.object_view.original_size != (0, 0))
            finish_thumbnails(window)
            app.processEvents()
            window.grab().save(str(output / 'gallery_ru.png'))
            window.resize(1050, 710)
            app.processEvents()
            window.grab().save(str(output / 'gallery_small_ru.png'))
            button = window.classifier.export_button
            rectangle = QtCore.QRect(button.mapTo(window, QtCore.QPoint()), button.size())
            assert window.rect().contains(rectangle)
            stats['small_window_export_visible'] = True
            stats['scientific_csv_unchanged'] = scientific.read_bytes() == scientific_before
            stats['source_unchanged'] = before == (source.stat().st_size, source.stat().st_mtime_ns)
            assert stats['scientific_csv_unchanged'] and stats['source_unchanged']
            assert service.get_object_labels(window.selected_dataset())['assigned'] == 0
        finally:
            if window.process is not None:
                window.process.kill()
                window.process.waitForFinished(5000)
            window.close()
            image_pool().waitForDone(5000)
            app.processEvents()
    (output / 'verification.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
