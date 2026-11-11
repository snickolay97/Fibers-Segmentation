"""Launch the local SoLoData desktop application."""
import argparse
from pathlib import Path
import sys


def _open_startup_window(default_path, preferences, *, explicit_path=None, language=None, smoke_test=False):
    from src.desktop.editor_preferences import read_profile
    from src.desktop.i18n import tr
    from src.desktop.main_window import MainWindow, ProjectLockError
    from src.desktop.project import LAST_PROJECT_KEY, Project

    notice = None
    if not explicit_path and not smoke_test:
        remembered = preferences.value(LAST_PROJECT_KEY)
        if isinstance(remembered, str) and Path(remembered).is_absolute():
            try:
                project = Project.load(remembered)
                return MainWindow(project, language=language, preferences=preferences)
            except (OSError, ValueError, ProjectLockError) as error:
                # Keep the previous path so a project on a disconnected drive
                # or open in another instance can be retried next session.
                notice = tr('The last project could not be opened. Opened the default project. {error}',
                            error=str(error))
    path = Path(explicit_path).resolve() if explicit_path else default_path
    if not path.exists():
        path = Project.creation_path(path)
    if path.exists():
        project = Project.load(path)
    else:
        profile = read_profile(preferences)
        project = Project.create(path, name=tr('Fiber study'), settings=profile['processing'],
                                 calibration_mode=profile['calibration_mode'])
    window = MainWindow(project, language=language, preferences=preferences)
    if explicit_path and not smoke_test:
        preferences.setValue(LAST_PROJECT_KEY, project.path)
    if notice:
        window.statusBar().showMessage(notice, 15000)
        window._log(notice)
    return window


def main(argv=None):
    """Resolve the local project and run the GUI in the selected Qt binding."""
    parser = argparse.ArgumentParser(description='SoLoData desktop application')
    parser.add_argument('--project', help='Existing or new SoLoData project JSON')
    parser.add_argument('--no-auto-sources', action='store_true',
                        help='Compatibility option; sources are always added explicitly')
    parser.add_argument('--smoke-test', action='store_true', help='Render and exit for installation verification')
    parser.add_argument('--language', choices=('en', 'ru', 'he'), help='Interface language for this launch')
    args = parser.parse_args(argv)
    # Parse first so --help works even in an environment without Qt.
    try:
        from src.desktop.qt import QtCore, QtWidgets
        from src.desktop.branding import configure_application_branding, configure_taskbar_window, set_windows_app_identity
        from src.desktop.i18n import register_translations, set_language, tr
    except ImportError as error:
        print('Missing application dependencies: ' + str(error), file=sys.stderr)
        print('Run launch_app.cmd or install requirements.txt with Python 3.10+.', file=sys.stderr)
        return 1
    fallback = 'The last project could not be opened. Opened the default project. {error}'
    register_translations({'Fiber study': 'Исследование волокон',
                           'SoLoData — startup error': 'SoLoData — ошибка запуска',
                           fallback: 'Не удалось открыть последний проект. Открыт проект по умолчанию. {error}'},
                          hebrew={fallback: 'לא ניתן לפתוח את הפרויקט האחרון. פרויקט ברירת המחדל נפתח. {error}'})
    root = Path(__file__).resolve().parent
    set_windows_app_identity()
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    configure_application_branding(application)
    application.setApplicationName('SoLoData')
    application.setOrganizationName('Fibers Segmentation')
    # Retain the earlier storage namespace for saved preferences and layouts.
    preferences = QtCore.QSettings('FiberLab', 'Desktop')
    language = args.language or str(preferences.value('language', 'en'))
    set_language(language if language in ('en', 'ru', 'he') else 'en')
    try:
        window = _open_startup_window(root / 'data' / 'projects' / 'default' / 'project.json', preferences,
                                      explicit_path=args.project, language=args.language, smoke_test=args.smoke_test)
        configure_taskbar_window(window)
        window.show()
        if args.smoke_test:
            QtCore.QTimer.singleShot(300, window.close)
        status = application.exec()
        # Destroy the window and its child widgets while QApplication is alive.
        window.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(window, QtCore.QEvent.Type.DeferredDelete)
        return status
    except Exception as error:
        if args.smoke_test:
            print(str(error), file=sys.stderr)
        else:
            QtWidgets.QMessageBox.critical(None, tr('SoLoData — startup error'), tr(str(error)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
