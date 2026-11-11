"""Project metadata diagnostics and bounded SQL browsing for desktop owners."""
from datetime import datetime
from pathlib import Path
import sqlite3

from .i18n import register_translations, tr
from .qt import QtCore, QtGui, QtWidgets
from .storage_names import version_path


_TEXT = {
    'Project database…': ('База данных проекта…', 'מסד הנתונים של הפרויקט…'),
    'Project database': ('База данных проекта', 'מסד הנתונים של הפרויקט'),
    'Close': ('Закрыть', 'סגירה'),
    'Help': ('Справка', 'עזרה'),
    'SQLite catalog: current': ('Каталог SQLite актуален', 'קטלוג SQLite מעודכן'),
    'SQLite catalog: missing': ('Каталог SQLite ещё не создан', 'קטלוג SQLite טרם נוצר'),
    'SQLite catalog: unavailable': ('Каталог SQLite требует проверки', 'קטלוג SQLite דורש בדיקה'),
    'Refresh catalog': ('Обновить каталог', 'עדכון הקטלוג'),
    'Rebuild catalog': ('Пересоздать каталог', 'בנייה מחדש של הקטלוג'),
    'Back up project metadata…': ('Копия метаданных проекта…', 'גיבוי מטא־נתוני הפרויקט…'),
    'Sources: {sources} · Datasets: {datasets} · History entries: {history}': (
        'Исходники: {sources} · Наборы: {datasets} · Записи истории: {history}',
        'מקורות: {sources} · מערכים: {datasets} · רשומות היסטוריה: {history}'),
    'Saved project metadata is indexed here. JSON remains authoritative. Images, masks, manual labels, measurement CSVs and models are stored separately. For a full backup, close SoLoData and copy the entire project folder.': (
        'Здесь учитываются сохранённые метаданные проекта. Основным остаётся JSON. Изображения, маски, ручные метки, CSV измерений и модели хранятся отдельно. Для полной резервной копии закройте SoLoData и скопируйте всю папку проекта.',
        'כאן מקוטלגים מטא־נתונים שמורים של הפרויקט. JSON נשאר המקור הקובע. תמונות, מסכות, תוויות ידניות, CSV של מדידות ומודלים נשמרים בנפרד. לגיבוי מלא סגרו את SoLoData והעתיקו את כל תיקיית הפרויקט.'),
    'Saved datasets': ('Сохранённые наборы', 'מערכים שמורים'),
    'Saved history': ('Сохранённая история', 'היסטוריה שמורה'),
    'Dataset ID': ('ID набора', 'מזהה מערך'),
    'Dataset name': ('Название набора', 'שם המערך'),
    'Saved status': ('Сохранённое состояние', 'מצב שמור'),
    'Source ID': ('ID исходника', 'מזהה מקור'),
    'Event time (UTC)': ('Время события (UTC)', 'זמן האירוע (UTC)'),
    'Action key': ('Ключ действия', 'מפתח הפעולה'),
    'Previous page': ('Предыдущая страница', 'העמוד הקודם'),
    'Next page': ('Следующая страница', 'העמוד הבא'),
    'Rows {first}–{last} of {total}': ('Строки {first}–{last} из {total}', 'שורות {first}–{last} מתוך {total}'),
    'Database operation failed': ('Операция с базой не выполнена', 'פעולת מסד הנתונים נכשלה'),
    'Choose a parent folder for the metadata-only backup': (
        'Выберите папку для копии только метаданных', 'בחרו תיקיית אב לגיבוי המטא־נתונים בלבד'),
    'Metadata backup saved: {path}\nImages, masks, labels, CSVs and models are not included.': (
        'Копия метаданных сохранена: {path}\nИзображения, маски, метки, CSV и модели в неё не входят.',
        'גיבוי המטא־נתונים נשמר: {path}\nתמונות, מסכות, תוויות, CSV ומודלים אינם כלולים.'),
    'Previous catalog preserved: {path}': ('Прежний каталог сохранён: {path}', 'הקטלוג הקודם נשמר: {path}'),
    'Unsupported or unrelated project catalog; file preserved': (
        'Каталог другой программы или неподдерживаемой версии; файл сохранён.',
        'הקטלוג שייך ליישום אחר או לגרסה לא נתמכת; הקובץ נשמר.'),
    'Project catalog is out of date; synchronize or rebuild it': (
        'Каталог устарел. Нажмите «Обновить каталог» или «Пересоздать каталог».',
        'הקטלוג אינו מעודכן. בחרו עדכון או בנייה מחדש של הקטלוג.'),
    'Catalog integrity check failed': (
        'Проверка целостности каталога не пройдена. Пересоздайте каталог.',
        'בדיקת תקינות הקטלוג נכשלה. בנו את הקטלוג מחדש.'),
    'The catalog must not be a symbolic link': (
        'Вместо каталога обнаружена символическая ссылка. Используйте обычный локальный файл.',
        'הקטלוג הוא קישור סמלי. השתמשו בקובץ מקומי רגיל.'),
    'Project changed while indexing; retry after the writer finishes': (
        'Проект изменился во время обновления каталога. Повторите после завершения записи.',
        'הפרויקט השתנה בזמן עדכון הקטלוג. נסו שוב לאחר סיום הכתיבה.'),
    'Project changed during rebuild; retry': (
        'Проект изменился во время пересоздания каталога. Повторите операцию.',
        'הפרויקט השתנה בזמן בניית הקטלוג מחדש. נסו שוב.'),
    'Project changed during backup; retry after the writer finishes': (
        'Проект изменился во время резервного копирования. Повторите после завершения записи.',
        'הפרויקט השתנה בזמן הגיבוי. נסו שוב לאחר סיום הכתיבה.'),
    'Backup integrity check failed': ('Копия не прошла проверку целостности.', 'הגיבוי נכשל בבדיקת התקינות.'),
    'file is not a database': (
        'Файл каталога повреждён или не является базой SQLite. Нажмите «Пересоздать каталог».',
        'קובץ הקטלוג פגום או שאינו מסד SQLite. בחרו בנייה מחדש של הקטלוג.'),
    'database is locked': (
        'Каталог занят другим обращением. Повторите после завершения операции.',
        'הקטלוג נעול לשימוש אחר. נסו שוב לאחר סיום הפעולה.'),
}
register_translations({key: value[0] for key, value in _TEXT.items()},
                      hebrew={key: value[1] for key, value in _TEXT.items()})


class DatabaseDialog(QtWidgets.QDialog):
    """Modal maintenance under the main window's project lock, without a worker."""
    PAGE_SIZE = 100

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.catalog = project.catalog()
        self.project = project
        self._saved_settings = dict(project.settings)
        self._help_center = None
        self.offset = 0
        self.setWindowTitle(tr('Project database'))
        self.resize(900, 590)
        layout = QtWidgets.QVBoxLayout(self)
        explanation = QtWidgets.QLabel(tr(
            'Saved project metadata is indexed here. JSON remains authoritative. Images, masks, manual labels, measurement CSVs and models are stored separately. For a full backup, close SoLoData and copy the entire project folder.'))
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.state = QtWidgets.QLabel()
        self.state.setWordWrap(True)
        self.state.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        layout.addWidget(self.state)
        path = QtWidgets.QLabel(str(self.catalog.path))
        path.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        path.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        path.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        path.setWordWrap(True)
        layout.addWidget(path)
        row = QtWidgets.QHBoxLayout()
        self.sync_button = QtWidgets.QPushButton(tr('Refresh catalog'))
        self.sync_button.clicked.connect(lambda: self._operate(self.catalog.synchronize))
        self.rebuild_button = QtWidgets.QPushButton(tr('Rebuild catalog'))
        self.rebuild_button.clicked.connect(self._rebuild)
        self.backup_button = QtWidgets.QPushButton(tr('Back up project metadata…'))
        self.backup_button.clicked.connect(self._backup)
        for button in (self.sync_button, self.rebuild_button, self.backup_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.kind = QtWidgets.QComboBox()
        self.kind.addItem(tr('Saved datasets'), 'datasets')
        self.kind.addItem(tr('Saved history'), 'history')
        self.kind.currentIndexChanged.connect(self._reset_page)
        layout.addWidget(self.kind)
        self.table = QtWidgets.QTableWidget()
        self.table.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)
        pages = QtWidgets.QHBoxLayout()
        self.previous = QtWidgets.QPushButton(tr('Previous page'))
        self.next = QtWidgets.QPushButton(tr('Next page'))
        self.previous.clicked.connect(lambda: self._page(-1))
        self.next.clicked.connect(lambda: self._page(1))
        self.page_label = QtWidgets.QLabel()
        for widget in (self.previous, self.page_label, self.next):
            pages.addWidget(widget)
        layout.addLayout(pages)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close |
                                            QtWidgets.QDialogButtonBox.StandardButton.Help)
        buttons.rejected.connect(self.reject)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Close).setText(tr('Close'))
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Help).setText(tr('Help'))
        buttons.helpRequested.connect(self._show_help)
        self._help_shortcut = QtGui.QShortcut(QtGui.QKeySequence('F1'), self)
        self._help_shortcut.activated.connect(self._show_help)
        layout.addWidget(buttons)
        self.refresh()

    def _show_help(self):
        # A child of this modal dialog remains interactive while its owner is blocked.
        from .help_center import HelpCenter
        if self._help_center is None:
            self._help_center = HelpCenter(self, current_settings=self._saved_settings)
        self._help_center.open_topic('database')
        self._help_center.show()
        self._help_center.raise_()
        self._help_center.activateWindow()

    def refresh(self):
        self.report = self.catalog.status()
        if self.report['state'] == 'current':
            # Label audit events are durable in their measurement database even
            # before the next project JSON/catalog checkpoint.
            self.report['counts']['history'] = len(self.project.history)
        state = self.report['state']
        text = tr('SQLite catalog: ' + state)
        if state == 'current':
            text += '\n' + tr('Sources: {sources} · Datasets: {datasets} · History entries: {history}',
                                **self.report['counts'])
        elif self.report.get('error'):
            text += '\n' + tr(self.report['error'])
        self.state.setText(text)
        self.backup_button.setEnabled(state == 'current')
        self.rebuild_button.setEnabled(state != 'current')
        self._load_page()

    def _reset_page(self):
        self.offset = 0
        self.refresh()

    def _page(self, direction):
        self.offset = max(0, self.offset + direction * self.PAGE_SIZE)
        self.refresh()

    def _load_page(self):
        kind = self.kind.currentData()
        total = self.report.get('counts', {}).get(kind, 0)
        self.offset = min(self.offset, max(0, (total - 1) // self.PAGE_SIZE * self.PAGE_SIZE))
        fields = ('id', 'name', 'status', 'source_id') if kind == 'datasets' else ('time', 'action', 'dataset_id')
        titles = ('Dataset ID', 'Dataset name', 'Saved status', 'Source ID') if kind == 'datasets' else (
            'Event time (UTC)', 'Action key', 'Dataset ID')
        rows = []
        if self.report['state'] == 'current':
            try:
                rows = (self.project.history[self.offset:self.offset+self.PAGE_SIZE] if kind == 'history'
                        else self.catalog.records(kind, offset=self.offset, limit=self.PAGE_SIZE))
            except (OSError, ValueError, sqlite3.Error) as error:
                self.state.setText(tr('SQLite catalog: unavailable') + '\n' + tr(str(error)))
        self.table.setColumnCount(len(fields))
        self.table.setHorizontalHeaderLabels([tr(title) for title in titles])
        self.table.setRowCount(len(rows))
        for i, item in enumerate(rows):
            for j, field in enumerate(fields):
                self.table.setItem(i, j, QtWidgets.QTableWidgetItem(str(item.get(field, ''))))
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.page_label.setText(tr('Rows {first}–{last} of {total}',
                                   first=self.offset + 1 if rows else 0,
                                   last=self.offset + len(rows), total=total))
        self.previous.setEnabled(self.offset > 0)
        self.next.setEnabled(self.offset + len(rows) < total and bool(rows))

    def _operate(self, operation):
        try:
            result = operation()
        except (OSError, ValueError, sqlite3.Error) as error:
            QtWidgets.QMessageBox.warning(self, tr('Database operation failed'), tr(str(error)))
            result = None
        self.refresh()
        return result

    def _rebuild(self):
        result = self._operate(self.catalog.rebuild)
        if result and result.get('preserved_catalog'):
            self.state.setText(self.state.text() + '\n' + tr('Previous catalog preserved: {path}',
                                                                           path=result['preserved_catalog']))

    def _backup(self):
        parent = QtWidgets.QFileDialog.getExistingDirectory(
            self, tr('Choose a parent folder for the metadata-only backup'), str(self.catalog.project_path.parent))
        if parent:
            destination = version_path(parent, 'Project_metadata_' + datetime.now().strftime('%Y-%m-%d'))
            result = self._operate(lambda: self.catalog.backup(destination))
            if result:
                QtWidgets.QMessageBox.information(self, tr('Project database'),
                    tr('Metadata backup saved: {path}\nImages, masks, labels, CSVs and models are not included.',
                       path=result['path']))
