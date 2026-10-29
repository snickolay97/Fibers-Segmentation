"""Launch the local SoLoData desktop application."""
import argparse
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description='SoLoData desktop application')
    parser.add_argument('--project', help='Existing or new SoLoData project JSON')
    parser.add_argument('--no-auto-sources', action='store_true')
    parser.add_argument('--smoke-test', action='store_true', help='Render and exit for installation verification')
    parser.add_argument('--language', choices=('en', 'ru', 'he'), help='Interface language for this launch')
    args = parser.parse_args(argv)
    try:
        from src.desktop.qt import QtCore, QtWidgets
        from src.desktop.project import Project
        from src.desktop import service
        from src.desktop.main_window import MainWindow
        from src.desktop.i18n import register_translations, set_language, tr
    except ImportError as error:
        print('Missing application dependencies: ' + str(error), file=sys.stderr)
        print('Run launch_app.cmd or install requirements.txt with Python 3.10+.', file=sys.stderr)
        return 1
    register_translations({'Fiber study': 'Исследование волокон',
                           'SoLoData — startup error': 'SoLoData — ошибка запуска'})
    root = Path(__file__).resolve().parent
    path = Path(args.project).resolve() if args.project else root / 'data' / 'ui_projects' / 'default' / 'project.json'
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    application.setApplicationName('SoLoData')
    application.setOrganizationName('Fibers Segmentation')
    # Retain the earlier storage namespace for saved preferences and layouts.
    preferences = QtCore.QSettings('FiberLab', 'Desktop')
    language = args.language or str(preferences.value('language', 'en'))
    set_language(language if language in ('en', 'ru', 'he') else 'en')
    try:
        project = Project.load(path) if path.exists() else Project.create(path, name=tr('Fiber study'))
        window = MainWindow(project, language=args.language, preferences=preferences)
        if not args.project and not args.no_auto_sources and not project.sources:
            service.add_sources(project, sorted((root / 'data' / '1_raw_large_images').glob('*.tif*')))
            window.refresh_project()
        window.show()
        if args.smoke_test:
            QtCore.QTimer.singleShot(300, application.quit)
        return application.exec()
    except Exception as error:
        if args.smoke_test:
            print(str(error), file=sys.stderr)
        else:
            QtWidgets.QMessageBox.critical(None, tr('SoLoData — startup error'), tr(str(error)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
