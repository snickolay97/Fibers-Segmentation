"""Reproduce safe settings recovery and the trilingual in-app manual.

Uses a temporary project with the same invalid even-kernel edit reported by
the owner. It does not process or modify source TIFFs or prepared datasets.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.default_settings import DEFAULTS_VERSION, FACTORY_DEFAULTS
from src.desktop.qt import QtCore, QtWidgets
from src.desktop.project import Project, atomic_json
from src.desktop.main_window import MainWindow
from src.desktop.help_center import TOPICS
from src.desktop.widgets import image_pool


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    output = ROOT/'data/app_preview/help_recovery_20261029'
    output.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication([])
    stats = dict(defaults_version=DEFAULTS_VERSION, parameter_count=len(FACTORY_DEFAULTS),
                 application_topics=len(TOPICS), languages=['en', 'ru', 'he'])
    with tempfile.TemporaryDirectory(prefix='verification_', dir=output) as directory:
        base = Path(directory)
        project = Project.create(base/'project.json', 'Help and recovery verification')
        damaged = project.to_dict()
        damaged['settings'].update(buffer_kernel_size=6, gamma=1.6)
        atomic_json(project.path, damaged)
        broken_bytes = Path(project.path).read_bytes()
        preferences = QtCore.QSettings(str(base/'preferences.ini'), QtCore.QSettings.Format.IniFormat)
        window = MainWindow(Project.load(project.path), preferences=preferences)
        window.show()
        window.show_log.setChecked(False)
        try:
            app.processEvents()
            stats['invalid_startup_recovered'] = window._recovery_report['changed']
            stats['exact_original_backup'] = Path(window._recovery_report['backup_path']).read_bytes() == broken_bytes
            assert stats['invalid_startup_recovered'] and stats['exact_original_backup']
            assert window.collect_settings()['gamma'] == 1.6
            assert window.collect_settings()['buffer_kernel_size'] == 5
            window.grab().save(str(output/'recovery_en.png'))
            window.sidebar.setCurrentRow(1)
            window._settings_fields['buffer_kernel_size'].setValue(6)
            assert not window.save_button.isEnabled()
            window.set_language('ru')
            panel = window._workspaces['preparation'].panels['settings'].widget()
            panel.ensureWidgetVisible(window._settings_fields['buffer_kernel_size'])
            app.processEvents()
            window.grab().save(str(output/'invalid_edit_ru.png'))
            window.show_help('buffer_kernel_size')
            app.processEvents()
            guide = window._help_center
            guide.grab().save(str(output/'parameter_reference_ru.png'))
            guide.open_topic('getting_started')
            app.processEvents()
            guide.grab().save(str(output/'application_help_ru.png'))
            guide.close()
            window.set_language('he')
            app.processEvents()
            stats['hebrew_rtl'] = window.layoutDirection() == QtCore.Qt.LayoutDirection.RightToLeft
            stats['numeric_inputs_ltr'] = all(field.layoutDirection() == QtCore.Qt.LayoutDirection.LeftToRight
                for field in window._settings_fields.values() if isinstance(field, QtWidgets.QAbstractSpinBox))
            window.grab().save(str(output/'invalid_edit_he.png'))
            window.show_help('getting_started')
            app.processEvents()
            guide.grab().save(str(output/'application_help_he.png'))
            guide.open_parameter('gamma')
            app.processEvents()
            guide.grab().save(str(output/'parameter_reference_he.png'))
            stats['factory_default_stays_fixed'] = FACTORY_DEFAULTS['gamma'] == 1.2
            stats['current_value_separate'] = guide.current_settings['gamma'] == 1.6
            window.close()
            app.processEvents()
            saved = Project.load(project.path)
            stats['invalid_draft_not_saved'] = saved.settings['buffer_kernel_size'] == 5
            stats['other_valid_value_preserved'] = saved.settings['gamma'] == 1.6
            assert all(value for key,value in stats.items() if isinstance(value, bool))
        finally:
            window.close()
            image_pool().waitForDone(5000)
            app.processEvents()
    (output/'verification.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
