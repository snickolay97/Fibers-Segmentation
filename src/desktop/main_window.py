"""SoLoData desktop workflow; expensive operations run in a worker process."""

import json
import math
import sys
import uuid
from datetime import datetime
from pathlib import Path

from .qt import QtCore, QtGui, QtWidgets, configure_font
from .widgets import CsvTable, ImageViewer, image_pool
from .i18n import tr, get_language, set_language, register_translations
from .help import attach_help, help_label
from .object_classifier import ObjectClassifier
from .object_review import ObjectReviewGallery
from .workspace import DockWorkspace
from src.app_settings import PipelineSettings
from src.default_settings import FACTORY_DEFAULTS
from .settings_safety import recover_project_settings
from .help_center import HelpCenter
from .parameter_reference import parameter_entry

register_translations({
    'Help': 'Справка',
    'Application guide · F1': 'Руководство по приложению · F1',
    'Parameter reference': 'Справочник параметров',
    'Settings and recovery': 'Настройки и восстановление',
    'Restore factory defaults': 'Восстановить заводские настройки',
    'Restore saved settings': 'Вернуть сохранённые настройки',
    'Explain': 'Объяснить', 'Dismiss notice': 'Скрыть уведомление',
    'Open help': 'Открыть справку', 'Explain this parameter': 'Объяснить параметр',
    'Use factory default': 'Вернуть заводское значение',
    'Invalid setting: {name}. Allowed: {allowed}. Factory default: {default}.':
        'Недопустимая настройка: {name}. Допустимо: {allowed}. Заводское значение: {default}.',
    'Invalid saved settings were restored safely. The original project was backed up.':
        'Недопустимые настройки восстановлены. Сохранена резервная копия исходного проекта.',
    'Settings recovery backup: {path}': 'Резервная копия настроек: {path}',
    'Factory defaults restored. They apply to future processing.':
        'Заводские значения восстановлены. Они применятся при последующей обработке.',
    'Saved settings restored.': 'Сохранённые настройки восстановлены.',
    'Invalid settings were not saved. The previous saved values were kept.':
        'Недопустимые настройки не сохранены. Оставлены ранее сохранённые значения.',
    'Settings need correction before processing.': 'Исправьте настройки перед запуском обработки.',
})


_STAGES = {
    "prepare": tr("Подготовка"), "extract": tr("Измерения"), "overview": tr("Обзорная карта"),
    "preview": tr("Предпросмотр"), "connect": tr("Подключение набора"), "pick_tile": tr("Выбор тайла"),
    "import_labels": tr("Импорт разметки"), "loading": tr("Чтение TIFF"),
    "preprocessing": tr("Фильтрация"), "slicing": tr("Нарезка"),
    "preprocess": tr("Фильтрация"), "load": tr("Чтение TIFF"), "features": tr("Измерения"),
    "validation": tr("Проверка набора"), "proposals": tr("Поиск границ"), "components": tr("Защитные компоненты"),
    "export": tr("Сохранение тайлов"), "loading_tiles": tr("Чтение тайлов"),
    "filter": tr("Фильтрация"), "slice": tr("Нарезка"), "dataset": tr("Набор"),
    "validate": tr("Проверка набора"), "pipeline": tr("Обработка"),
}
_STATUS = {
    "complete": tr("Готов"), "completed": tr("Готов"), "prepared": tr("Готов к проверке"),
    "running": tr("Выполняется"), "cancelled": tr("Остановлен"), "failed": tr("Ошибка"),
    "connected": tr("Подключён"), "pending": tr("Ожидает"), "partial": tr("Незавершён"),
    "needs_review": tr("Нужна проверка"), "ready": tr("Готов"), "new": tr("Новый"),
    "awaiting_review": tr("Нужна проверка"), "awaiting_annotations": tr("Ожидает разметку"),
    "interrupted": tr("Прерван"), "error": tr("Ошибка"),
}


def stage_name(key, default=None):
    return tr(_STAGES.get(key, default or key))


def status_name(key, default=None):
    return tr(_STATUS.get(key, default or key))


def _display(value):
    if isinstance(value, (list, tuple)):
        return " × ".join(str(part) for part in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value) if value is not None else "—"


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, project, parent=None, *, language=None, preferences=None):
        super().__init__(parent)
        # Keep the existing namespace when changing the displayed product name.
        self.preferences = preferences if preferences is not None else QtCore.QSettings("FiberLab", "Desktop")
        selected_language = language or str(self.preferences.value("language", "en"))
        self.language = selected_language if selected_language in ("en", "ru", "he") else "en"
        set_language(self.language)
        self._apply_language_direction()
        self._font_family = configure_font()
        # The entry point constructs the durable project before opening the UI.
        from .project import Project
        from . import service
        self.Project, self.service, self.project = Project, service, project
        self._project_lock = self._lock_project(project)
        try:
            self._recovery_report = recover_project_settings(project)
        except Exception:
            self._project_lock.unlock()
            raise
        project.recover_interrupted()
        self.process = None
        self.request_path = None
        self._stdout_buffer = b""
        self._stderr_buffer = b""
        self._job_result = None
        self._job_error = None
        self._job_action = None
        self._cancel_requested = False
        self._close_requested = False
        self._refreshing = False
        self._dark = False
        self._job_buttons = []
        self._tile_records = []
        self._selected_tile = None
        self._manual_report = {}
        self._elapsed_timer = QtCore.QElapsedTimer()
        self._elapsed_update = QtCore.QTimer(self)
        self._elapsed_update.setInterval(1000)
        self._elapsed_update.timeout.connect(self._update_elapsed)
        self._manifest = None
        self._settings_fields = {}
        self._loaded_setting_values = {}
        self._workspaces = {}
        self._syncing_object = False
        self._busy = False
        self._settings_loading = False
        self._help_center = None
        self._settings_notice_dismissed = False
        self._saved_settings_snapshot = dict(project.settings)
        self._draft_settings = PipelineSettings.from_dict(project.settings).to_dict()
        self.setMinimumSize(1050, 710)
        self.resize(1380, 960)
        self._build_ui()
        self._apply_theme()
        geometry = self.preferences.value("main/geometry")
        if isinstance(geometry, QtCore.QByteArray):
            self.restoreGeometry(geometry)
        self.refresh_project()
        self._show_recovery_notice()

    def _apply_language_direction(self):
        locale = {"en": "en_US", "ru": "ru_RU", "he": "he_IL"}[self.language]
        self.setLocale(QtCore.QLocale(locale))
        self.setLayoutDirection(QtCore.Qt.LayoutDirection.RightToLeft if self.language == "he"
                                else QtCore.Qt.LayoutDirection.LeftToRight)

    def _button(self, text, callback, primary=False, job_sensitive=True):
        button = QtWidgets.QPushButton(text)
        button.clicked.connect(callback)
        if primary:
            button.setProperty("primary", True)
        if job_sensitive:
            self._job_buttons.append(button)
        return button

    def set_language(self, language, persist=True):
        """Change presentation only; scientific settings and identifiers stay stable."""
        if language not in ("en", "ru", "he") or language == self.language or self.process is not None:
            return
        source_checks = {self.source_table.item(row, 0).data(QtCore.Qt.ItemDataRole.UserRole):
                         self.source_table.item(row, 0).checkState() for row in range(self.source_table.rowCount())}
        state = dict(page=self.sidebar.currentRow(), tile_search=self.tile_search.text(),
                     tile_filter=self.tile_filter.currentData(), tile_tab=self.tile_tabs.currentIndex(),
                     gallery=self.object_gallery.filter_state(), review_tab=self.review_tabs.currentIndex(),
                     labels_mode=self.labels_mode.currentData(),
                     previews=[viewer.filename for viewer in (self.input_preview, self.filtered_preview, self.protective_preview)],
                     preview_tab=self.preview_tabs.currentIndex(),
                     result_search=self.results_table.search.text(), result_class=self.results_table.class_filter.currentData(),
                     object=self.results_table.selected_row(), pending_class=self.classifier.class_combo.currentData(),
                     tile=self._selected_tile.get("id") if self._selected_tile else None,
                     draft=self.collect_settings(), source_row=self.source_table.currentRow(), log=self.log.toPlainText(),
                     log_visible=self.show_log.isChecked(), elapsed=self.elapsed_label.text())
        self._persist_settings(skip_invalid=True)
        self._save_panel_layouts(dispose=True)
        self.language = language
        set_language(language)
        self._apply_language_direction()
        if persist:
            self.preferences.setValue("language", language)
            self.preferences.sync()
        self._job_buttons, self._settings_fields, self._workspaces = [], {}, {}
        self._loaded_setting_values = {}
        old = self.takeCentralWidget()
        old.deleteLater()
        self._build_ui()
        self._apply_theme()
        self.refresh_project()
        self._load_settings(state["draft"])
        self.sidebar.setCurrentRow(state["page"])
        self.tile_search.setText(state["tile_search"])
        self.tile_filter.setCurrentIndex(max(0, self.tile_filter.findData(state["tile_filter"])))
        if state["tile"] is not None:
            self._select_tile_id(state["tile"], clear_filter=False)
        self.tile_tabs.setCurrentIndex(state["tile_tab"])
        self.results_table.search.setText(state["result_search"])
        self.results_table.class_filter.setCurrentIndex(max(0, self.results_table.class_filter.findData(state["result_class"])))
        self.object_gallery.set_filter_state(state["gallery"])
        self.review_tabs.setCurrentIndex(state["review_tab"])
        self.labels_mode.setCurrentIndex(max(0, self.labels_mode.findData(state["labels_mode"])))
        for filename, viewer in zip(state["previews"], (self.input_preview, self.filtered_preview, self.protective_preview)):
            if filename:
                viewer.set_image(filename)
        self.preview_tabs.setCurrentIndex(state["preview_tab"])
        if state["object"]:
            self.results_table.select_object(state["object"].get("Tile_Name"), state["object"].get("Object_ID"))
            self.classifier.class_combo.setCurrentIndex(max(0, self.classifier.class_combo.findData(state["pending_class"])))
        for row in range(self.source_table.rowCount()):
            item = self.source_table.item(row, 0)
            if item.data(QtCore.Qt.ItemDataRole.UserRole) in source_checks:
                item.setCheckState(source_checks[item.data(QtCore.Qt.ItemDataRole.UserRole)])
        if state["source_row"] >= 0:
            self.source_table.selectRow(state["source_row"])
        self.log.setPlainText(state["log"])
        self.show_log.setChecked(state["log_visible"])
        self.elapsed_label.setText(state["elapsed"])
        if self._help_center is not None:
            self._help_center.retranslate(language)
            self._help_center.refresh_settings(self.collect_settings())

    def _language_changed(self, *_):
        language = self.language_combo.currentData()
        if language and language != self.language:
            self.set_language(language)

    def _form_row(self, form, title, field, key):
        label = QtWidgets.QWidget()
        label_layout = QtWidgets.QHBoxLayout(label)
        label_layout.setContentsMargins(0, 0, 0, 0)
        label_layout.addWidget(QtWidgets.QLabel(tr(title)), 1)
        label_layout.addWidget(help_label(key))
        attach_help(field, key)
        field.setProperty("parameterTitle", tr(title))
        form.addRow(label, field)

    @staticmethod
    def _lock_project(project):
        lock = QtCore.QLockFile(str(project.path) + ".lock")
        if not lock.tryLock(0):
            raise RuntimeError(tr("Этот проект уже открыт в другом окне SoLoData. Закройте его или выберите другой проект."))
        return lock

    def _switch_project(self, project):
        if Path(project.path).resolve() == Path(self.project.path).resolve():
            return
        candidate_lock = self._lock_project(project)
        try:
            self._persist_settings(skip_invalid=True)
            recovery_report = recover_project_settings(project)
        except Exception:
            candidate_lock.unlock()
            raise
        self._project_lock.unlock()
        self.project, self._project_lock = project, candidate_lock
        self._recovery_report = recovery_report
        self._recovery_logged = False
        self._saved_settings_snapshot = dict(project.settings)
        self._draft_settings = PipelineSettings.from_dict(project.settings).to_dict()
        self._settings_notice_dismissed = False
        self.project.recover_interrupted()
        for viewer in (self.input_preview, self.filtered_preview, self.protective_preview):
            viewer.clear()
        self.refresh_project()
        self._show_recovery_notice()

    @staticmethod
    def _note(text):
        label = QtWidgets.QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("muted")
        return label

    def _build_ui(self):
        central = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(central)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(12)
        top = QtWidgets.QHBoxLayout()
        brand = QtWidgets.QLabel("SoLoData")
        brand.setObjectName("brand")
        top.addWidget(brand)
        self.project_name = QtWidgets.QLabel()
        self.project_name.setObjectName("muted")
        top.addWidget(self.project_name, 1)
        top.addWidget(self._button(tr("Новый проект"), self.new_project))
        top.addWidget(self._button(tr("Открыть"), self.open_project))
        self.save_button = self._button(tr("Сохранить"), self.save_project)
        top.addWidget(self.save_button)
        self.theme_button = self._button(tr("Тёмная тема"), self.toggle_theme, job_sensitive=False)
        top.addWidget(self.theme_button)
        self.help_button = QtWidgets.QToolButton()
        self.help_button.setText(tr("Help"))
        self.help_button.setObjectName("applicationHelp")
        self.help_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.help_button.clicked.connect(lambda: self.show_help())
        self.help_menu = QtWidgets.QMenu(self.help_button)
        self.help_menu.addAction(tr("Application guide · F1"), lambda: self.show_help("getting_started"))
        self.help_menu.addAction(tr("Parameter reference"), lambda: self.show_help("parameters"))
        self.help_menu.addAction(tr("Settings and recovery"), lambda: self.show_help("recovery"))
        self.help_menu.addSeparator()
        self.restore_defaults_action = self.help_menu.addAction(tr("Restore factory defaults"), self.restore_factory_settings)
        self.restore_saved_action = self.help_menu.addAction(tr("Restore saved settings"), self.restore_saved_settings)
        self.help_button.setMenu(self.help_menu)
        top.addWidget(self.help_button)
        top.addWidget(QtWidgets.QLabel(tr("Language")))
        self.language_combo = QtWidgets.QComboBox()
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("Русский", "ru")
        self.language_combo.addItem("עברית", "he")
        self.language_combo.setCurrentIndex(self.language_combo.findData(self.language))
        attach_help(self.language_combo, "language")
        self.language_combo.currentIndexChanged.connect(self._language_changed)
        top.addWidget(self.language_combo)
        top.addWidget(help_label("language"))
        outer.addLayout(top)

        self.settings_feedback = QtWidgets.QFrame()
        feedback_layout = QtWidgets.QHBoxLayout(self.settings_feedback)
        feedback_layout.setContentsMargins(8, 5, 8, 5)
        self.settings_feedback_text = QtWidgets.QLabel()
        self.settings_feedback_text.setWordWrap(True)
        feedback_layout.addWidget(self.settings_feedback_text, 1)
        self.settings_feedback_help = QtWidgets.QPushButton(tr("Explain"))
        self.settings_feedback_help.clicked.connect(self._explain_setting_issue)
        feedback_layout.addWidget(self.settings_feedback_help)
        self.settings_feedback_restore = QtWidgets.QPushButton(tr("Restore saved settings"))
        self.settings_feedback_restore.clicked.connect(self.restore_saved_settings)
        feedback_layout.addWidget(self.settings_feedback_restore)
        self.settings_feedback_close = QtWidgets.QToolButton()
        self.settings_feedback_close.setText("×")
        self.settings_feedback_close.setAccessibleName(tr("Dismiss notice"))
        self.settings_feedback_close.clicked.connect(self._dismiss_settings_notice)
        feedback_layout.addWidget(self.settings_feedback_close)
        outer.addWidget(self.settings_feedback)
        self.settings_feedback.hide()

        self.body = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.sidebar = QtWidgets.QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setMinimumWidth(155)
        self.sidebar.setMaximumWidth(190)
        for number, label in enumerate((tr("Исходники"), tr("Подготовка"), tr("Тайлы"), tr("Segmentation"), tr("Результаты")), 1):
            self.sidebar.addItem(f"{number:02d}   {label}")
        self.sidebar.setSpacing(7)
        self.sidebar.currentRowChanged.connect(self._change_page)
        self.body.addWidget(self.sidebar)
        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(16, 0, 0, 0)
        heading = QtWidgets.QHBoxLayout()
        self.page_title = QtWidgets.QLabel(tr("Исходники"))
        self.page_title.setObjectName("pageTitle")
        heading.addWidget(self.page_title, 1)
        self.panels_button = QtWidgets.QToolButton()
        self.panels_button.setText(tr("Panels"))
        self.panels_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.panels_menu = QtWidgets.QMenu(self.panels_button)
        self.panels_menu.aboutToShow.connect(self._populate_panels_menu)
        self.panels_button.setMenu(self.panels_menu)
        self.panels_button.setToolTip(tr("Drag panel headers to rearrange them; double-click a header to detach or dock it."))
        heading.addWidget(self.panels_button)
        heading.addWidget(QtWidgets.QLabel(tr("Набор:")))
        self.dataset_combo = QtWidgets.QComboBox()
        self.dataset_combo.setMinimumWidth(250)
        self.dataset_combo.setPlaceholderText(tr("No prepared datasets"))
        attach_help(self.dataset_combo, "dataset")
        self.dataset_combo.currentIndexChanged.connect(self._dataset_changed)
        heading.addWidget(self.dataset_combo)
        heading.addWidget(help_label("dataset"))
        open_tiles = self._button(tr("Открыть тайлы…"), self.connect_dataset)
        attach_help(open_tiles, "open_tiles")
        heading.addWidget(open_tiles)
        content_layout.addLayout(heading)
        self.dataset_status = self._note(tr("Добавьте TIFF или подключите готовую нарезку"))
        content_layout.addWidget(self.dataset_status)
        self.pages = QtWidgets.QStackedWidget()
        self.pages.addWidget(self._sources_page())
        self.pages.addWidget(self._prepare_page())
        self.pages.addWidget(self._tiles_page())
        self.pages.addWidget(self._labels_page())
        self.pages.addWidget(self._results_page())
        content_layout.addWidget(self.pages, 1)
        self.body.addWidget(content)
        self.body.setStretchFactor(1, 1)
        outer.addWidget(self.body, 1)

        job_line = QtWidgets.QHBoxLayout()
        self.job_status = QtWidgets.QLabel(tr("Готов к работе"))
        self.job_status.setMinimumWidth(300)
        job_line.addWidget(self.job_status, 1)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setMaximumWidth(330)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        job_line.addWidget(self.progress)
        self.cancel_button = QtWidgets.QPushButton(tr("Остановить"))
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_job)
        job_line.addWidget(self.cancel_button)
        self.elapsed_label = QtWidgets.QLabel("")
        self.elapsed_label.setObjectName("muted")
        job_line.addWidget(self.elapsed_label)
        self.show_log = QtWidgets.QCheckBox(tr("Журнал"))
        self.show_log.setChecked(True)
        job_line.addWidget(self.show_log)
        outer.addLayout(job_line)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(140)
        self.log.setMinimumHeight(65)
        self.log.document().setMaximumBlockCount(1800)
        self.show_log.toggled.connect(self.log.setVisible)
        outer.addWidget(self.log)
        self.setCentralWidget(central)
        self.sidebar.setCurrentRow(0)
        self._watch_settings()
        for badge in central.findChildren(QtWidgets.QLabel, "helpBadge"):
            badge.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            badge.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
            badge.setAccessibleName(tr("Open help"))
            badge.installEventFilter(self)
        if not hasattr(self, "_help_shortcut"):
            self._help_shortcut = QtGui.QShortcut(QtGui.QKeySequence("F1"), self)
            self._help_shortcut.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)
            self._help_shortcut.activated.connect(self._contextual_help)
        self._apply_reading_directions()

    def _workspace(self, key):
        workspace = DockWorkspace(key, self.preferences)
        self._workspaces[key] = workspace
        return workspace

    def _populate_panels_menu(self):
        workspace = list(self._workspaces.values())[self.pages.currentIndex()]
        workspace.populate_menu(self.panels_menu)

    def _save_panel_layouts(self, dispose=False):
        for workspace in self._workspaces.values():
            workspace.dispose() if dispose else workspace.save_layout()
        if dispose:
            self.object_gallery.dispose()
            self.classifier.dispose()
        self.preferences.sync()

    def _apply_reading_directions(self):
        """Keep image coordinates, numbers and file identifiers LTR in Hebrew."""
        ltr = QtCore.Qt.LayoutDirection.LeftToRight
        for field in self._settings_fields.values():
            if isinstance(field, QtWidgets.QAbstractSpinBox):
                field.setLayoutDirection(ltr)
        for table in (self.source_table, self.results_table.table):
            table.setLayoutDirection(ltr)
        for viewer in self.findChildren(ImageViewer):
            viewer.view.setLayoutDirection(ltr)
        self.log.setLayoutDirection(ltr)
        self.exclude_specs.setLayoutDirection(ltr)
        self.labels_path.setLayoutDirection(ltr)

    def show_help(self, key="getting_started"):
        if self._help_center is None:
            self._help_center = HelpCenter(parent=self, current_settings=self.collect_settings(), language=self.language)
        else:
            self._help_center.refresh_settings(self.collect_settings())
        if key in FACTORY_DEFAULTS:
            self._help_center.open_parameter(key)
        else:
            self._help_center.open_topic(key or "getting_started")
        self._help_center.show()
        self._help_center.raise_()
        self._help_center.activateWindow()

    def _contextual_help(self):
        widget = QtWidgets.QApplication.focusWidget()
        while widget is not None:
            key = widget.property("helpKey")
            if key:
                self.show_help(key)
                return
            widget = widget.parentWidget()
        self.show_help(("sources", "preparation", "tiles", "segmentation", "results")[self.sidebar.currentRow()])

    def eventFilter(self, watched, event):
        if isinstance(watched, QtWidgets.QLabel) and watched.objectName() == "helpBadge":
            activated = (event.type() == QtCore.QEvent.Type.MouseButtonRelease
                         and event.button() == QtCore.Qt.MouseButton.LeftButton)
            activated |= (event.type() == QtCore.QEvent.Type.KeyPress
                          and event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter, QtCore.Qt.Key.Key_Space))
            if activated:
                key = watched.property("helpKey")
                if not key:
                    key = ("sources", "preparation", "tiles", "segmentation", "results")[self.sidebar.currentRow()]
                self.show_help(key)
                return True
        return super().eventFilter(watched, event)

    def _watch_settings(self):
        for key, field in self._settings_fields.items():
            signal = field.toggled if isinstance(field, QtWidgets.QCheckBox) else field.valueChanged
            signal.connect(self._settings_changed)
            field.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
            field.customContextMenuRequested.connect(lambda position, k=key, w=field: self._parameter_menu(w, k, position))
            if isinstance(field, QtWidgets.QAbstractSpinBox):
                editor = field.lineEdit()
                editor.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
                editor.customContextMenuRequested.connect(lambda position, k=key, w=editor: self._parameter_menu(w, k, position))

    def _parameter_menu(self, widget, key, position):
        menu = widget.createStandardContextMenu() if isinstance(widget, QtWidgets.QLineEdit) else QtWidgets.QMenu(widget)
        if menu.actions():
            menu.addSeparator()
        menu.addAction(tr("Explain this parameter"), lambda: self.show_help(key))
        action = menu.addAction(tr("Use factory default"), lambda: self._restore_parameter(key))
        action.setEnabled(not self._busy)
        menu.exec(widget.mapToGlobal(position))

    def _restore_parameter(self, key):
        if self._busy:
            return
        values = self.collect_settings()
        values[key] = FACTORY_DEFAULTS[key]
        self._load_settings(values)

    def _settings_changed(self, *_):
        if not self._settings_loading:
            self._refresh_settings_validation()
            if self._help_center is not None:
                self._help_center.refresh_settings(self.collect_settings())

    def _setting_title(self, key):
        try:
            entry = parameter_entry(key, language=self.language)
            return entry['title'] if entry else key
        except (KeyError, TypeError):
            return key

    def _refresh_settings_validation(self):
        if not hasattr(self, "settings_feedback"):
            return []
        from src.app_settings import inspect_settings
        issues = inspect_settings(self.collect_settings())
        invalid = {issue['field'] for issue in issues}
        for key, field in self._settings_fields.items():
            if field.property("invalidSetting") != (key in invalid):
                field.setProperty("invalidSetting", key in invalid)
                field.style().unpolish(field)
                field.style().polish(field)
        self.save_button.setEnabled(not issues and not self._busy)
        if issues:
            self._active_setting_issue = issues[0]['field']
            key = self._active_setting_issue
            entry = parameter_entry(key, language=self.language)
            allowed = entry['valid_range'] if entry else issues[0]['message']
            self.settings_feedback_text.setText(tr(
                'Invalid setting: {name}. Allowed: {allowed}. Factory default: {default}.',
                name=self._setting_title(key), allowed=allowed, default=FACTORY_DEFAULTS.get(key, '—')))
            self._set_settings_notice_kind("error")
            self.settings_feedback_close.setVisible(False)
            self.settings_feedback_restore.setVisible(True)
            self.settings_feedback.show()
        elif not self._settings_notice_dismissed and self._recovery_report.get('changed'):
            self._show_recovery_notice()
        else:
            self.settings_feedback.hide()
        return issues

    def _explain_setting_issue(self):
        self.show_help(getattr(self, "_active_setting_issue", "recovery"))

    def _set_settings_notice_kind(self, kind):
        if self.settings_feedback.property("noticeKind") != kind:
            self.settings_feedback.setProperty("noticeKind", kind)
            self.settings_feedback.style().unpolish(self.settings_feedback)
            self.settings_feedback.style().polish(self.settings_feedback)

    def _dismiss_settings_notice(self):
        self._settings_notice_dismissed = True
        self.settings_feedback.hide()

    def _show_recovery_notice(self):
        report = self._recovery_report
        if not report.get('changed') or self._settings_notice_dismissed:
            return
        issues = report.get('issues') or []
        self._active_setting_issue = issues[0]['field'] if issues else "recovery"
        self.settings_feedback_text.setText(tr('Invalid saved settings were restored safely. The original project was backed up.'))
        self.settings_feedback_text.setToolTip(str(report.get('backup_path') or ''))
        self._set_settings_notice_kind("recovered")
        self.settings_feedback_close.setVisible(True)
        self.settings_feedback_restore.setVisible(False)
        self.settings_feedback.show()
        if hasattr(self, 'log') and not getattr(self, '_recovery_logged', False):
            self._log(tr('Settings recovery backup: {path}', path=report.get('backup_path', '')))
            self._recovery_logged = True

    def _persist_settings(self, skip_invalid=False):
        try:
            values = PipelineSettings.from_dict(self.collect_settings()).to_dict()
        except ValueError:
            if skip_invalid:
                return False
            raise
        self.project.settings = values
        self.project.save()
        self._saved_settings_snapshot = dict(values)
        return True

    def restore_factory_settings(self):
        if not self._busy:
            self._load_settings(dict(FACTORY_DEFAULTS))
            self.statusBar().showMessage(tr('Factory defaults restored. They apply to future processing.'), 8000)

    def restore_saved_settings(self):
        if not self._busy:
            self._load_settings(PipelineSettings.from_dict(self._saved_settings_snapshot).to_dict())
            self.statusBar().showMessage(tr('Saved settings restored.'), 8000)

    def _sources_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(self._note(tr("Исходные изображения остаются на диске. Выберите TIFF для подготовки или подключите существующий набор v3.")))
        actions = QtWidgets.QHBoxLayout()
        actions.addWidget(self._button(tr("Добавить TIFF"), self.add_sources, True))
        open_tiles = self._button(tr("Открыть подготовленные тайлы"), self.connect_dataset)
        attach_help(open_tiles, "open_tiles")
        actions.addWidget(open_tiles)
        actions.addStretch()
        actions.addWidget(self._button(tr("К подготовке →"), lambda: self.sidebar.setCurrentRow(1)))
        layout.addLayout(actions)
        self.source_table = QtWidgets.QTableWidget(0, 6)
        self.source_table.setHorizontalHeaderLabels([tr("Выбор"), tr("Изображение"), tr("Размеры"), tr("Оси"), tr("Тип"), tr("Статус")])
        self.source_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.source_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.source_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.source_table.verticalHeader().setVisible(False)
        self.source_table.setAlternatingRowColors(True)
        self.source_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.source_table.itemSelectionChanged.connect(self._source_selected)
        attach_help(self.source_table, "source_selection")
        self.source_table.horizontalHeaderItem(0).setToolTip(self.source_table.toolTip())
        actions.addWidget(help_label("source_selection"))
        workspace = self._workspace("sources")
        workspace.add_panel("images", "Source images", self.source_table)
        workspace.finish_layout()
        layout.addWidget(workspace, 1)
        self.source_details = self._note(tr("Выберите строку, чтобы увидеть путь и свойства TIFF. Галочки задают пакет обработки."))
        layout.addWidget(self.source_details)
        return page

    def _spin(self, key, low, high, default, decimal=False):
        field = QtWidgets.QDoubleSpinBox() if decimal else QtWidgets.QSpinBox()
        field.setRange(low, high)
        if decimal:
            field.setDecimals(3)
            field.setSingleStep(.1)
        elif key in ("bridge_kernel_size", "buffer_kernel_size"):
            field.setSingleStep(2)
        field.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        field.setValue(default)
        self._settings_fields[key] = field
        attach_help(field, key)
        return field

    def _prepare_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        workspace = self._workspace("preparation")
        panel = QtWidgets.QWidget()
        panel_layout = QtWidgets.QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 12, 0)
        form = QtWidgets.QFormLayout()
        form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        self._form_row(form, tr("Размер модельного тайла"), self._spin("target_size", 64, 6000, 1500), "target_size")
        self._form_row(form, tr("Размер обзорной карты"), self._spin("overview_size", 200, 12000, 6000), "overview_size")
        self._form_row(form, tr("Канал (нумерация с 0)"), self._spin("channel", 0, 31, 0), "channel")
        plane = self._spin("plane", 0, 100000, 0)
        self._form_row(form, tr("Плоскость стека"), plane, "plane")
        pixel = self._spin("pixel_size_um", 0, 100000, 0, True)
        pixel.setDecimals(6)
        pixel.setSpecialValueText(tr("Не задана · исходные px"))
        self._form_row(form, tr("Калибровка µm/px"), pixel, "pixel_size_um")
        for key, title in (("save_raw_tiles", tr("Сохранить raw-тайлы")),
                           ("enable_animations", tr("Сохранить анимации поиска")),
                           ("save_coverage_masks", tr("Сохранить модельные маски покрытия"))):
            widget = QtWidgets.QCheckBox(title)
            self._settings_fields[key] = widget
            attach_help(widget, key)
            row = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(widget, 1)
            row_layout.addWidget(help_label(key))
            form.addRow(row)
        panel_layout.addLayout(form)
        panel_layout.addWidget(self._note(tr("Крупные объекты уменьшаются до модельного тайла целиком. Native-фрагменты сохраняют пространственный масштаб для измерений.")))
        advanced = QtWidgets.QGroupBox(tr("Choose filters"))
        advanced_layout = QtWidgets.QVBoxLayout(advanced)
        self._filter_parameter_groups = {}
        parameter_forms = {}
        filter_controls = (
            ("enable_bilateral", "Bilateral denoising", ("bilateral_d", "bilateral_sigma_color", "bilateral_sigma_space")),
            ("enable_tophat", "White top-hat", ("tophat_radius",)),
            ("enable_gamma", "Gamma correction", ("gamma",)),
            ("enable_closing", "Morphological closing", ("bridge_kernel_size",)),
            ("enable_dilation", "Protective dilation", ("buffer_kernel_size",)),
        )
        for key, title, parameter_keys in filter_controls:
            card = QtWidgets.QGroupBox()
            card_form = QtWidgets.QFormLayout(card)
            card_form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
            toggle = QtWidgets.QCheckBox(tr(title))
            toggle.setChecked(True)
            self._settings_fields[key] = toggle
            self._filter_parameter_groups[key] = parameter_keys
            attach_help(toggle, key)
            line = QtWidgets.QWidget()
            line_layout = QtWidgets.QHBoxLayout(line)
            line_layout.setContentsMargins(0, 0, 0, 0)
            line_layout.addWidget(toggle, 1)
            line_layout.addWidget(help_label(key))
            card_form.addRow(line)
            advanced_layout.addWidget(card)
            parameter_forms.update({name: card_form for name in parameter_keys})
            toggle.toggled.connect(self._update_filter_controls)
        routing = QtWidgets.QGroupBox(tr("Protective mask"))
        routing_form = QtWidgets.QFormLayout(routing)
        routing_form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        for key, title, lo, hi, value, decimal in (
            ("bilateral_d", tr("Bilateral: размер"), 1, 51, 9, False),
            ("bilateral_sigma_color", tr("Bilateral: интенсивность"), 1, 500, 45, True),
            ("bilateral_sigma_space", tr("Bilateral: пространство"), 1, 500, 15, True),
            ("tophat_radius", tr("Top-hat: радиус"), 1, 1000, 85, False),
            ("gamma", "Gamma", .05, 10, 1.2, True),
            ("otsu_safety_factor", tr("Доля порога Otsu"), .01, 1, .25, True),
            ("bridge_kernel_size", tr("Соединение защитной маски"), 1, 101, 17, False),
            ("buffer_kernel_size", tr("Буфер защитной маски"), 1, 101, 5, False),
            ("min_corridor_width", tr("Минимальная ширина коридора"), 1, 500, 15, False),
        ):
            self._form_row(parameter_forms.get(key, routing_form), title, self._spin(key, lo, hi, value, decimal), key)
        advanced_layout.addWidget(routing)
        panel_layout.addWidget(advanced)
        panel_layout.addWidget(self._note(tr("Changes apply to new preparation. Existing tiles keep their saved filtering settings.")))
        panel_layout.addStretch()
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        scroll.setMinimumWidth(330)
        self.preview_tabs = QtWidgets.QTabWidget()
        self.input_preview = ImageViewer(empty_text=tr("Предпросмотр выбранного TIFF"))
        self.filtered_preview = ImageViewer(empty_text=tr("Здесь появится отфильтрованное изображение"))
        self.protective_preview = ImageViewer(empty_text=tr("Здесь появится защитная маска"))
        self.preview_tabs.addTab(self.input_preview, tr("Исходный канал"))
        self.preview_tabs.addTab(self.filtered_preview, tr("Фильтрация"))
        self.preview_tabs.addTab(self.protective_preview, tr("Защитная маска"))
        settings_dock = workspace.add_panel("settings", "Processing settings", scroll)
        images_dock = workspace.add_panel("images", "Image previews", self.preview_tabs, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        workspace.resizeDocks([settings_dock, images_dock], [355, 750], QtCore.Qt.Orientation.Horizontal)
        workspace.finish_layout()
        layout.addWidget(workspace, 1)
        layout.addWidget(self._note(tr("Предпросмотр служит проверкой параметров. Полная подготовка использует весь TIFF; набор сохраняет собственный снимок настроек.")))
        actions = QtWidgets.QHBoxLayout()
        actions.addWidget(self._button(tr("Предпросмотр выбранного TIFF"), self.preview_source))
        actions.addStretch()
        actions.addWidget(self._button(tr("Подготовить выбранные TIFF"), self.prepare_sources, True))
        layout.addLayout(actions)
        return page

    def _tiles_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        self.tile_summary = self._note(tr("Подключите или подготовьте набор, чтобы проверить тайлы"))
        layout.addWidget(self.tile_summary)
        workspace = self._workspace("tiles")
        list_panel = QtWidgets.QWidget()
        list_layout = QtWidgets.QVBoxLayout(list_panel)
        list_layout.setContentsMargins(0, 0, 8, 0)
        self.tile_search = QtWidgets.QLineEdit()
        self.tile_search.setPlaceholderText(tr("ID или имя тайла"))
        self.tile_search.textChanged.connect(self._filter_tiles)
        attach_help(self.tile_search, "tile_search")
        self.tile_filter = QtWidgets.QComboBox()
        for text, data in ((tr("Все тайлы"), "all"), (tr("Активные"), "active"), (tr("Исключённые"), "excluded"), (tr("Яркие области"), "bright")):
            self.tile_filter.addItem(text, data)
        self.tile_filter.currentIndexChanged.connect(self._filter_tiles)
        attach_help(self.tile_filter, "tile_filter")
        self.tile_list = QtWidgets.QListWidget()
        self.tile_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tile_list.currentItemChanged.connect(self._tile_selected)
        for control, key in ((self.tile_search, "tile_search"), (self.tile_filter, "tile_filter")):
            line = QtWidgets.QHBoxLayout()
            line.addWidget(control, 1)
            line.addWidget(help_label(key))
            list_layout.addLayout(line)
        list_layout.addWidget(self.tile_list, 1)
        list_panel.setMinimumWidth(175)
        self.tile_tabs = QtWidgets.QTabWidget()
        self.overview_view = ImageViewer(empty_text=tr("Обзорная карта ещё не открыта"))
        self.overview_view.clicked.connect(self._overview_clicked)
        self.model_view = ImageViewer(empty_text=tr("Выберите тайл из списка или нажмите на карту"))
        self.native_view = ImageViewer(empty_text=tr("Native-фрагмент сохраняет исходный пространственный масштаб"))
        self.ownership_view = ImageViewer(empty_text=tr("Маска принадлежности пикселей тайлу"))
        self.polygon_view = ImageViewer(empty_text=tr("Полигонная разметка выбранного тайла"))
        for viewer, title in ((self.overview_view, tr("Карта")), (self.model_view, tr("Модельный")),
                              (self.native_view, "Native"), (self.ownership_view, tr("Принадлежность")),
                              (self.polygon_view, tr("Полигоны"))):
            self.tile_tabs.addTab(viewer, title)
        list_dock = workspace.add_panel("browser", "Tile browser", list_panel)
        image_dock = workspace.add_panel("images", "Tile images", self.tile_tabs, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        workspace.resizeDocks([list_dock, image_dock], [210, 900], QtCore.Qt.Orientation.Horizontal)
        workspace.finish_layout()
        layout.addWidget(workspace, 1)
        self.tile_details = self._note(tr("На карте выбор определяется точной маской принадлежности пикселей."))
        layout.addWidget(self.tile_details)
        actions = QtWidgets.QHBoxLayout()
        self.exclude_specs = QtWidgets.QLineEdit()
        self.exclude_specs.setPlaceholderText(tr("ID: 4, 12-18 · или выделите тайлы"))
        attach_help(self.exclude_specs, "tile_ids")
        actions.addWidget(self.exclude_specs, 1)
        actions.addWidget(help_label("tile_ids"))
        actions.addWidget(self._button(tr("Исключить"), lambda: self.change_exclusion(True)))
        actions.addWidget(self._button(tr("Вернуть"), lambda: self.change_exclusion(False)))
        actions.addWidget(self._button(tr("Обновить карту"), self.rebuild_overview))
        actions.addWidget(self._button(tr("Проверка завершена"), self.finish_review, True))
        layout.addLayout(actions)
        return page

    def _labels_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        workspace = self._workspace("segmentation")
        settings_panel = QtWidgets.QWidget()
        settings_layout = QtWidgets.QVBoxLayout(settings_panel)
        layout.addWidget(self._note(tr("Импортируйте YOLO segmentation: один TXT на модельный PNG, нормализованные координаты полигона. Разметка связана с текущими ID тайлов.")))
        actions = QtWidgets.QHBoxLayout()
        actions.addWidget(self._button(tr("Импортировать папку разметки"), self.import_labels, True))
        actions.addWidget(self._button(tr("Проверить разметку"), self.check_labels))
        settings_layout.addLayout(actions)
        settings_layout.addWidget(self._button(tr("Открыть папку"), self.open_labels_folder))
        self.labels_path = self._note(tr("Разметка ещё не подключена"))
        settings_layout.addWidget(self.labels_path)
        self.labels_report = QtWidgets.QPlainTextEdit()
        self.labels_report.setReadOnly(True)
        self.labels_report.setMaximumHeight(170)
        settings_layout.addWidget(self.labels_report)
        self.labels_view = ImageViewer(empty_text=tr("Выберите тайл на странице «Тайлы», чтобы увидеть его разметку"))
        form = QtWidgets.QFormLayout()
        self.labels_mode = QtWidgets.QComboBox()
        self.labels_mode.addItem(tr("Только имеющаяся разметка"), "annotations_only")
        self.labels_mode.addItem(tr("Требовать разметку всех активных тайлов"), "require_annotations")
        self.labels_mode.addItem(tr("Для отсутствующей разметки выделять объекты автоматически"), "auto")
        self._form_row(form, tr("Режим измерений"), self.labels_mode, "labels_mode")
        for key, title, lo, hi, value, decimal in (
            ("min_clean_threshold", tr("Порог очистки объекта"), 0, 255, 25, False),
            ("tier2_threshold_factor", tr("Локальная доля Otsu"), .01, 2, .7, True),
            ("min_sub_object_area", tr("Минимальная площадь (native px²)"), 1, 100000, 30, False),
        ):
            self._form_row(form, title, self._spin(key, lo, hi, value, decimal), key)
        settings_layout.addLayout(form)
        settings_layout.addWidget(self._note(tr("Пустой TXT означает отсутствие размеченных объектов. Автоматически найденные объекты получают класс Unknown. Native используется для измерений и обратного переноса полигонов.")))
        settings_layout.addWidget(self._button(tr("Рассчитать признаки"), self.extract_features))
        self.detect_objects_button = self._button(tr("Detect objects and assign types"), self.detect_and_review, True)
        settings_layout.addWidget(self.detect_objects_button)
        settings_layout.addWidget(self._button(tr("Review detected objects"), lambda: self.sidebar.setCurrentRow(4)))
        settings_layout.addStretch()
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(settings_panel)
        settings_dock = workspace.add_panel("settings", "Segmentation settings", scroll)
        image_dock = workspace.add_panel("image", "Segmentation preview", self.labels_view, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        workspace.resizeDocks([settings_dock, image_dock], [410, 690], QtCore.Qt.Orientation.Horizontal)
        workspace.finish_layout()
        layout.addWidget(workspace, 1)
        return page

    def _results_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        self.results_summary = self._note(tr("Признаки ещё не рассчитаны"))
        layout.addWidget(self.results_summary)
        measurement_note = self._note(tr("Area: source pixels · AR: major / minor mask axis"))
        measurement_note.setToolTip(tr("AR = большая / малая ось маски. Площади v3 измерены в исходных пикселях; µm² доступны при заданной калибровке. Скелет даёт концы и количество пикселей ветвления."))
        layout.addWidget(measurement_note)
        workspace = self._workspace("results")
        self.review_tabs = QtWidgets.QTabWidget()
        self.object_gallery = ObjectReviewGallery()
        self.object_gallery.row_selected.connect(self._gallery_selected)
        self.object_gallery.selection_cleared.connect(self._gallery_selection_cleared)
        self.results_table = CsvTable()
        self.results_table.row_selected.connect(self._result_selected)
        self.review_tabs.addTab(self.object_gallery, tr("Object gallery"))
        self.review_tabs.addTab(self.results_table, tr("Feature table"))
        self.object_view = ImageViewer(empty_text=tr("Выберите объект в таблице для проверки маски"))
        self.classifier = ObjectClassifier()
        # Its dock already names the task; keep narrow panels focused on the
        # object identity and six class buttons rather than a repeated title.
        self.classifier.title.hide()
        self.classifier.apply_class.connect(self.assign_manual_class)
        self.classifier.navigate.connect(self.navigate_objects)
        self.classifier.export_requested.connect(self.export_training_results)
        object_panel = QtWidgets.QWidget()
        object_panel.setMinimumWidth(305)
        object_layout = QtWidgets.QVBoxLayout(object_panel)
        object_layout.setContentsMargins(0, 0, 0, 0)
        classifier_scroll = QtWidgets.QScrollArea()
        classifier_scroll.setWidgetResizable(True)
        classifier_scroll.setWidget(self.classifier)
        classifier_scroll.setMinimumHeight(90)
        classifier_scroll.setMaximumHeight(330)
        object_layout.addWidget(classifier_scroll)
        # Keep the main training action visible while the review controls scroll.
        self.classifier.layout().removeWidget(self.classifier.export_button)
        object_layout.addWidget(self.classifier.export_button)
        gallery_dock = workspace.add_panel("objects", "Detected objects", self.review_tabs)
        preview_dock = workspace.add_panel("preview", "Object preview", self.object_view, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        class_dock = workspace.add_panel("classes", "Assign object type", object_panel, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        workspace.splitDockWidget(preview_dock, class_dock, QtCore.Qt.Orientation.Vertical)
        workspace.resizeDocks([gallery_dock, preview_dock], [720, 360], QtCore.Qt.Orientation.Horizontal)
        workspace.resizeDocks([preview_dock, class_dock], [260, 340], QtCore.Qt.Orientation.Vertical)
        workspace.finish_layout()
        self.classifier.set_shortcut_scope(page)
        self.review_tabs.currentChanged.connect(self._review_mode_changed)
        layout.addWidget(workspace, 1)
        actions = QtWidgets.QHBoxLayout()
        actions.addWidget(self._button(tr("Обновить результаты"), self.refresh_results))
        actions.addStretch()
        actions.addWidget(self._button(tr("Открыть папку результатов"), self.open_results_folder))
        actions.addWidget(self._button(tr("Экспорт всей таблицы"), self.export_results))
        actions.addWidget(self._button(tr("Экспорт видимых строк"), self.export_filtered_results, True))
        layout.addLayout(actions)
        return page

    def _change_page(self, row):
        if row >= 0:
            for index, workspace in enumerate(self._workspaces.values()):
                workspace.activate() if index == row else workspace.deactivate()
            self.pages.setCurrentIndex(row)
            self.page_title.setText((tr("Исходники"), tr("Подготовка"), tr("Тайлы"), tr("Segmentation"), tr("Результаты"))[row])

    def _apply_theme(self):
        if self._dark:
            bg, surface, text, muted, border, accent, alt = "#122024", "#1c2c31", "#e7f2f1", "#a4b8bc", "#354b51", "#43bda8", "#22343a"
        else:
            bg, surface, text, muted, border, accent, alt = "#f2f7f7", "#ffffff", "#183336", "#587478", "#d3e1e0", "#167d70", "#f0f6f5"
        selection = "#197b6e" if self._dark else accent
        self.setStyleSheet(f"""
            QWidget {{ background: {bg}; color: {text}; font-family: '{self._font_family}'; font-size: 13px; }}
            QLabel#brand {{ font-size: 25px; font-weight: 700; color: {accent}; padding-right: 14px; }}
            QLabel#pageTitle {{ font-size: 24px; font-weight: 600; }}
            QLabel#muted {{ color: {muted}; }}
            QLabel#helpBadge {{ color: {accent}; background: {surface}; border: 1px solid {border}; border-radius: 10px; font-weight: 700; }}
            QLabel#sectionTitle {{ font-size: 15px; font-weight: 600; }}
            QPushButton {{ background: {surface}; border: 1px solid {border}; border-radius: 7px; padding: 8px 12px; }}
            QPushButton:hover {{ border-color: {accent}; }}
            QPushButton:disabled {{ color: {muted}; background: {alt}; }}
            QPushButton[primary=true] {{ background: {selection}; color: white; border-color: {selection}; font-weight: 600; }}
            QPushButton[primary=true]:disabled {{ background: {border}; color: {muted}; border-color: {border}; }}
            QSpinBox[invalidSetting=true], QDoubleSpinBox[invalidSetting=true], QCheckBox[invalidSetting=true] {{ border: 2px solid #c54d42; }}
            QFrame[noticeKind=error] {{ border: 1px solid #c54d42; border-radius: 6px; }}
            QFrame[noticeKind=recovered] {{ border: 1px solid {accent}; border-radius: 6px; }}
            QToolButton {{ background: {surface}; border: 1px solid {border}; border-radius: 5px; padding: 6px 9px; }}
            QDockWidget::title {{ background: {alt}; border: 1px solid {border}; padding: 7px 9px; font-weight: 600; }}
            QDockWidget {{ border: 1px solid {border}; }}
            QMainWindow::separator {{ background: {border}; width: 6px; height: 6px; }}
            QMainWindow::separator:hover {{ background: {accent}; }}
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background: {surface}; border: 1px solid {border}; border-radius: 5px; padding: 6px; selection-background-color: {accent}; }}
            QAbstractItemView {{ background: {surface}; alternate-background-color: {alt}; border: 1px solid {border}; border-radius: 6px; selection-background-color: {selection}; selection-color: white; }}
            QHeaderView::section {{ background: {alt}; color: {text}; border: none; border-bottom: 1px solid {border}; padding: 8px; font-weight: 600; }}
            QListWidget#sidebar {{ background: {bg}; border: none; padding-top: 6px; }}
            QListWidget#sidebar::item {{ padding: 14px 8px; border-radius: 7px; }}
            QListWidget#sidebar::item:selected {{ background: {selection}; color: white; }}
            QGraphicsView {{ background: {surface}; border: 1px solid {border}; border-radius: 6px; }}
            QPlainTextEdit {{ background: {surface}; border: 1px solid {border}; border-radius: 6px; padding: 8px; }}
            QGroupBox {{ border: 1px solid {border}; border-radius: 7px; margin-top: 12px; padding-top: 18px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}
            QTabWidget::pane {{ border: none; padding-top: 8px; }}
            QTabBar::tab {{ padding: 8px 12px; border-bottom: 2px solid {border}; }}
            QTabBar::tab:selected {{ border-bottom-color: {accent}; color: {accent}; font-weight: 600; }}
            QProgressBar {{ background: {surface}; border: 1px solid {border}; border-radius: 5px; text-align: center; min-height: 22px; }}
            QProgressBar::chunk {{ background: {selection}; border-radius: 4px; }}
            QScrollArea {{ border: none; }}
            QToolTip {{ color: {text}; background: {surface}; border: 1px solid {border}; }}
        """)
        self.theme_button.setText(tr("Светлая тема") if self._dark else tr("Тёмная тема"))

    def toggle_theme(self):
        self._dark = not self._dark
        self._apply_theme()

    def _log(self, message):
        self.log.appendPlainText(f"{datetime.now():%H:%M:%S}  {message}")

    def _update_elapsed(self):
        seconds = max(0, self._elapsed_timer.elapsed() // 1000)
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.elapsed_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    def _error(self, message):
        if getattr(message, 'issues', None):
            self._refresh_settings_validation()
            self._log(tr('Settings need correction before processing.') + ' ' + str(message))
            self.statusBar().showMessage(tr('Settings need correction before processing.'), 10000)
            return
        message = tr(str(message))
        self._log(tr("Ошибка: ") + message)
        self.statusBar().showMessage(message, 15000)
        QtWidgets.QMessageBox.warning(self, "SoLoData", message)

    def selected_dataset(self):
        dataset_id = self.dataset_combo.currentData()
        if dataset_id is None:
            return None
        return self.project.get_dataset(dataset_id)

    def _require_dataset(self):
        dataset = self.selected_dataset()
        if dataset is None:
            self._error(tr("Сначала подготовьте TIFF или подключите готовую нарезку."))
        return dataset

    def refresh_project(self):
        self._refreshing = True
        selected_sources = {
            self.source_table.item(row, 0).data(QtCore.Qt.ItemDataRole.UserRole):
            self.source_table.item(row, 0).checkState()
            for row in range(self.source_table.rowCount())
            if self.source_table.item(row, 0) is not None
        }
        self.setWindowTitle(f"{tr(self.project.name)} — SoLoData")
        self.project_name.setText(tr(self.project.name))
        self.project_name.setToolTip(str(self.project.path))
        self.source_table.setRowCount(len(self.project.sources))
        for row, source in enumerate(self.project.sources):
            checked = QtWidgets.QTableWidgetItem()
            checked.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            source_id = source.get("id", source.get("path"))
            checked.setCheckState(selected_sources.get(source_id, QtCore.Qt.CheckState.Checked))
            checked.setData(QtCore.Qt.ItemDataRole.UserRole, source_id)
            self.source_table.setItem(row, 0, checked)
            values = [source.get("name", Path(source.get("path", "")).name),
                      _display(source.get("shape")), source.get("axes", "—"),
                      source.get("dtype", "—"), status_name(source.get("status", "new"), source.get("status", tr("Новый")))]
            for column, value in enumerate(values, 1):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setToolTip(source.get("path", ""))
                self.source_table.setItem(row, column, item)
        self.source_table.resizeColumnsToContents()
        self.source_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.dataset_combo.blockSignals(True)
        self.dataset_combo.clear()
        for dataset in self.project.datasets:
            label = f"{dataset.get('name', dataset['id'])} · {dataset['id'][:6]} · {status_name(dataset.get('status', 'ready'))}"
            self.dataset_combo.addItem(label, dataset["id"])
            self.dataset_combo.setItemData(self.dataset_combo.count()-1, dataset.get("path", ""), QtCore.Qt.ItemDataRole.ToolTipRole)
        wanted = self.project.active_dataset_id
        selected_index = self.dataset_combo.findData(wanted)
        if selected_index >= 0:
            self.dataset_combo.setCurrentIndex(selected_index)
        self.dataset_combo.blockSignals(False)
        self.dataset_combo.setEnabled(bool(self.project.datasets) and self.process is None)
        self._load_settings()
        self._refreshing = False
        self._dataset_changed()

    def _load_settings(self, values=None):
        values = PipelineSettings.from_dict(self.project.settings).to_dict() if values is None else dict(values)
        self._draft_settings = dict(FACTORY_DEFAULTS)
        self._draft_settings.update(values)
        self._settings_loading = True
        try:
            for key, field in self._settings_fields.items():
                if key not in values:
                    continue
                value = values[key]
                if isinstance(field, QtWidgets.QCheckBox):
                    field.setChecked(bool(value))
                else:
                    number = 0 if key == "pixel_size_um" and value is None else value
                    integral = isinstance(field, QtWidgets.QSpinBox)
                    representable = (-2147483648 <= number <= 2147483647) if integral else (math.isfinite(number) and abs(number) <= 1e12 and (number == 0 or abs(number) >= 1e-12))
                    field.setReadOnly(not representable)
                    if representable:
                        if number < field.minimum():
                            field.setMinimum(number)
                        if number > field.maximum():
                            field.setMaximum(number)
                        if not integral and number > 0:
                            field.setDecimals(max(field.decimals(), min(15, max(0, -math.floor(math.log10(number))) + 3)))
                        field.setValue(number)
                    else:
                        # Preserve unusual but valid imported values exactly;
                        # they remain resettable without overflowing Qt editors.
                        field.lineEdit().setText(str(number) if integral else format(number, '.8g'))
                rendered = field.isChecked() if isinstance(field, QtWidgets.QCheckBox) else field.value()
                self._loaded_setting_values[key] = (value, rendered)
        finally:
            self._settings_loading = False
        self._update_filter_controls()
        self._refresh_settings_validation()

    def _update_filter_controls(self, *_):
        busy = self._busy
        for toggle_key, parameter_keys in self._filter_parameter_groups.items():
            enabled = self._settings_fields[toggle_key].isChecked() and not busy
            for key in parameter_keys:
                if key in self._settings_fields:
                    self._settings_fields[key].setEnabled(enabled)

    def collect_settings(self):
        values = dict(self._draft_settings)
        for key, field in self._settings_fields.items():
            value = field.isChecked() if isinstance(field, QtWidgets.QCheckBox) else field.value()
            loaded = self._loaded_setting_values.get(key)
            if loaded is not None and value == loaded[1]:
                value = loaded[0]
            if key == "pixel_size_um" and value == 0:
                value = None
            values[key] = value
        return values

    def save_project(self):
        try:
            self._persist_settings()
            self._log(tr("Проект сохранён: ") + str(self.project.path))
        except Exception as exc:
            self._error(exc)

    def new_project(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, tr("Создать проект"), str(Path(self.project.workspace).parent / "new_project.json"), tr("Проект SoLoData (*.json)"))
        if not path:
            return
        try:
            self._switch_project(self.Project.create(path, Path(path).stem))
            self._log(tr("Создан проект ") + self.project.name)
        except Exception as exc:
            self._error(exc)

    def open_project(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, tr("Открыть проект"), str(Path(self.project.path).parent), tr("Проект SoLoData (*.json)"))
        if path:
            try:
                self._switch_project(self.Project.load(path))
                self._log(tr("Открыт проект ") + self.project.name)
            except Exception as exc:
                self._error(exc)

    def add_sources(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, tr("Добавить TIFF"), "", "TIFF (*.tif *.tiff *.TIF *.TIFF)")
        if paths:
            try:
                added = self.service.add_sources(self.project, paths)
                draft = self.collect_settings()
                self.refresh_project()
                self._load_settings(draft)
                self._log(tr('Добавлено исходников: {v0}', v0=len(added)))
            except Exception as exc:
                self._error(exc)

    def _source_selected(self):
        row = self.source_table.currentRow()
        if 0 <= row < len(self.project.sources):
            source = self.project.sources[row]
            self.source_details.setText(tr('{v0}\nОси: {v1} · Размеры: {v2} · Тип: {v3}', v0=source.get('path', ''), v1=source.get('axes', '—'), v2=_display(source.get('shape')), v3=source.get('dtype', '—')))

    def selected_source_ids(self):
        return [self.source_table.item(row, 0).data(QtCore.Qt.ItemDataRole.UserRole)
                for row in range(self.source_table.rowCount())
                if self.source_table.item(row, 0).checkState() == QtCore.Qt.CheckState.Checked]

    def preview_source(self):
        row = self.source_table.currentRow()
        if row < 0 and self.project.sources:
            row = 0
        if row < 0 or row >= len(self.project.sources):
            self._error(tr("Добавьте TIFF для предпросмотра."))
            return
        source = self.project.sources[row]
        self.start_job("preview", source_ids=[source["id"]], source_id=source["id"], settings=self.collect_settings())

    def prepare_sources(self):
        ids = self.selected_source_ids()
        if not ids:
            self._error(tr("Выберите хотя бы один TIFF галочкой на странице «Исходники»."))
            return
        self.start_job("prepare", source_ids=ids, settings=self.collect_settings())

    def connect_dataset(self):
        existing_tiles = Path(__file__).resolve().parents[2] / "data" / "2_sliced_tiles_1500"
        initial = existing_tiles if existing_tiles.is_dir() else Path(self.project.workspace)
        path = QtWidgets.QFileDialog.getExistingDirectory(self,
            tr("Open prepared tile dataset — select a dataset folder, not its parent"), str(initial))
        if path:
            self.start_job("connect", dataset_path=path)

    def _dataset_changed(self, *_):
        if self._refreshing:
            return
        dataset = self.selected_dataset()
        self.project.active_dataset_id = dataset["id"] if dataset else None
        if dataset:
            state = status_name(dataset.get("status", ""), dataset.get("status", tr("Подключён")))
            reviewed = tr("Проверен") if dataset.get("reviewed") else tr("Нужна проверка тайлов")
            self.dataset_status.setText(f"{state} · {reviewed} · {dataset.get('name', '')}")
            self.dataset_status.setToolTip(dataset.get('path', ''))
        else:
            self.dataset_status.setText(tr("Create a tile dataset on Preparation, or open a folder prepared earlier."))
            self.dataset_status.setToolTip("")
        try:
            self.project.save()
            self.refresh_tiles()
            self.check_labels(quiet=True)
            self.refresh_results(quiet=True)
        except Exception as exc:
            self._log(tr("Не удалось обновить набор: ") + str(exc))

    def refresh_tiles(self):
        dataset = self.selected_dataset()
        self._manifest = None
        self._tile_records = []
        self._selected_tile = None
        for viewer in (self.overview_view, self.model_view, self.native_view,
                       self.ownership_view, self.polygon_view, self.labels_view):
            viewer.clear()
        if not dataset:
            self.tile_list.clear()
            self.tile_summary.setText(tr("Подключите или подготовьте набор, чтобы проверить тайлы"))
            return
        try:
            self._manifest = self.service.dataset_manifest(dataset)
            self._tile_records = self.service.tile_records(dataset)
            excluded = sum(bool(record.get("excluded")) for record in self._tile_records)
            bright = sum(bool(record.get("quality", {}).get("review_bright_region")) for record in self._tile_records)
            self.tile_summary.setText(tr('Тайлов: {v0} · Активных: {v1} · Исключённых: {v2} · Ярких областей: {v3}', v0=len(self._tile_records), v1=len(self._tile_records) - excluded, v2=excluded, v3=bright))
            self._filter_tiles()
            images = sorted((Path(dataset["path"]) / "overview").glob("*_TILE_INDEX_MAP_*px.png"), key=lambda p: p.stat().st_mtime)
            if images:
                self.overview_view.set_image(images[-1], tr("Обзорная карта · нажмите на область для выбора тайла"))
            else:
                self.overview_view.clear(tr("Карта отсутствует. Нажмите «Обновить карту»."))
        except Exception as exc:
            self.tile_list.clear()
            self.tile_summary.setText(tr("Набор недоступен или незавершён: ") + str(exc))
            self._log(tr("Проверка набора: ") + str(exc))

    def _filter_tiles(self, *_):
        previous = self._selected_tile.get("id") if self._selected_tile else None
        self.tile_list.clear()
        query = self.tile_search.text().strip().casefold()
        mode = self.tile_filter.currentData()
        for record in self._tile_records:
            excluded = bool(record.get("excluded"))
            bright = bool(record.get("quality", {}).get("review_bright_region"))
            if mode == "active" and excluded or mode == "excluded" and not excluded or mode == "bright" and not bright:
                continue
            if query and query not in f"{record['id']} {record.get('filename', '')}".casefold():
                continue
            label = f"{record['id']:04d}"
            if excluded:
                label += tr("  · исключён")
            if bright:
                label += tr("  · яркая область")
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, record)
            self.tile_list.addItem(item)
            if record["id"] == previous:
                self.tile_list.setCurrentItem(item)

    def _tile_selected(self, item, previous=None):
        if item is None:
            return
        dataset = self.selected_dataset()
        if dataset is None:
            return
        record = item.data(QtCore.Qt.ItemDataRole.UserRole)
        self._selected_tile = record
        base = Path(dataset["path"])
        model = base / record["filename"]
        if record.get("excluded"):
            model = base / "excluded_tiles" / record["filename"]
        native = base / record.get("native_filename", record["filename"])
        mask = base / record.get("valid_mask", "")
        transform = record.get("transform", {})
        factor = transform.get("source_pixels_per_output_pixel", 1)
        self.tile_details.setText(tr('Тайл {v0} · {v1} · Native: {v2} px · Исходных px / модельный px: {v3:.4f} · Принадлежащих пикселей: {v4}', v0=record['id'], v1=tr('исключён') if record.get('excluded') else tr('активен'), v2=_display(transform.get('native_crop_shape')), v3=float(factor), v4=record.get('valid_pixels', '—')))
        self.model_view.set_image(model)
        self.native_view.set_image(native, tr("Native · исходный пространственный масштаб"))
        self.ownership_view.set_image(mask, tr("Точная принадлежность · белые пиксели относятся к выбранному тайлу"))
        self._show_polygons(model, record)

    def _show_polygons(self, model, record):
        dataset = self.selected_dataset()
        polygons = []
        label_file = Path(dataset.get("labels_dir") or ".") / (Path(record["filename"]).stem + ".txt")
        annotation_state = tr("Файл разметки отсутствует")
        if label_file.is_file():
            try:
                for line in label_file.read_text(encoding="utf-8-sig").splitlines():
                    parts = line.strip().split()
                    if not parts:
                        continue
                    if len(parts) < 7 or (len(parts) - 1) % 2:
                        raise ValueError(tr("Нужен полигон YOLO с минимум тремя точками"))
                    points = [(float(parts[i]), float(parts[i + 1])) for i in range(1, len(parts), 2)]
                    polygons.append({"class_id": int(parts[0]), "points": points})
                annotation_state = tr('Размеченных полигонов: {v0}', v0=len(polygons)) if polygons else tr("Пустой TXT · размеченных объектов нет")
            except Exception as exc:
                annotation_state = tr("Ошибка разметки: ") + str(exc)
                self._log(annotation_state)
        for viewer in (self.polygon_view, self.labels_view):
            viewer.set_image(model, annotation_state)
            viewer.set_polygons(polygons)

    def _overview_clicked(self, x, y):
        dataset = self.selected_dataset()
        if dataset is None or self._manifest is None:
            return
        width, height = self.overview_view.original_size
        source_h, source_w = self._manifest["image_shape"][:2]
        if width <= 0 or height <= 0:
            return
        if self.process is not None:
            self.statusBar().showMessage(tr("Дождитесь текущей операции"), 3000)
            return
        # Native valid masks can have hundreds of millions of pixels; decode in
        # the isolated worker, never in the GUI thread or a bounding-box guess.
        self.start_job("pick_tile", dataset_id=dataset["id"],
                       x=x * source_w / width, y=y * source_h / height)

    def _select_tile_id(self, tile_id, clear_filter=True):
        if tile_id is None:
            self._log(tr("В выбранном пикселе нет тайла"))
            return
        if clear_filter:
            self.tile_search.clear()
            self.tile_filter.setCurrentIndex(0)
        self._filter_tiles()
        for index in range(self.tile_list.count()):
            item = self.tile_list.item(index)
            if item.data(QtCore.Qt.ItemDataRole.UserRole)["id"] == tile_id:
                self.tile_list.setCurrentItem(item)
                self.tile_list.scrollToItem(item)
                break

    def change_exclusion(self, excluded):
        dataset = self._require_dataset()
        if dataset is None:
            return
        specs = self.exclude_specs.text().strip()
        if not specs:
            specs = [item.data(QtCore.Qt.ItemDataRole.UserRole)["id"] for item in self.tile_list.selectedItems()]
        if not specs:
            self._error(tr("Выделите тайлы или введите их ID/диапазоны."))
            return
        try:
            result = self.service.exclusion(self.project, dataset["id"], specs, excluded=excluded)
            self._log((tr("Исключение: ") if excluded else tr("Возврат: ")) + _display(result))
            self.exclude_specs.clear()
            self._dataset_changed()
        except Exception as exc:
            self._error(exc)

    def rebuild_overview(self):
        dataset = self._require_dataset()
        if dataset:
            self.start_job("overview", dataset_id=dataset["id"])

    def finish_review(self):
        dataset = self._require_dataset()
        if dataset:
            try:
                self.service.mark_reviewed(self.project, dataset["id"])
                self._dataset_changed()
                self.sidebar.setCurrentRow(3)
                self._log(tr("Проверка тайлов завершена: ") + dataset.get("name", dataset["id"]))
            except Exception as exc:
                self._error(exc)

    def import_labels(self):
        dataset = self._require_dataset()
        if dataset is None:
            return
        path = QtWidgets.QFileDialog.getExistingDirectory(self, tr("Папка с TXT в формате YOLO segmentation"))
        if path:
            self.start_job("import_labels", dataset_id=dataset["id"], labels_source=path)

    def check_labels(self, checked=False, quiet=False):
        dataset = self.selected_dataset()
        if dataset is None:
            self.labels_path.setText(tr("Разметка ещё не подключена"))
            self.labels_report.setPlainText(tr("Подготовьте или подключите набор."))
            return
        self.labels_path.setText(dataset.get("labels_dir") or tr("Разметка ещё не импортирована"))
        try:
            report = self.service.inspect_labels(self.project, dataset["id"])
            names = {"active_tiles": tr("Активных тайлов"), "tiles": tr("Активных тайлов"), "total": tr("Всего"), "annotated": tr("С разметкой"),
                     "empty": tr("Пустых TXT"), "missing": tr("Без TXT"), "invalid": tr("Некорректных TXT"),
                     "orphan": tr("Неизвестные имена"), "errors": tr("Ошибки"), "objects": tr("Полигонов"),
                     "valid": tr("Корректных TXT"), "extra": tr("Лишних TXT"), "orphan_names": tr("Неизвестные имена"),
                     "missing_names": tr("Отсутствующие TXT"), "empty_names": tr("Пустые TXT"), "annotated_names": tr("Размеченные TXT")}
            lines = []
            for key, value in report.items():
                if key in ("missing_names", "empty_names", "annotated_names"):
                    continue
                if isinstance(value, list):
                    lines.append(f"{names.get(key, key)}: {len(value)}")
                    if key in ("errors", "invalid"):
                        lines.extend("  " + _display(item) for item in value[:20])
                else:
                    lines.append(f"{names.get(key, key)}: {_display(value)}")
            self.labels_report.setPlainText("\n".join(lines))
            if not quiet:
                self._log(tr("Проверка разметки завершена"))
        except Exception as exc:
            self.labels_report.setPlainText(tr("Ошибка проверки: ") + str(exc))
            if not quiet:
                self._error(exc)

    def extract_features(self):
        dataset = self._require_dataset()
        if dataset:
            self.start_job("extract", dataset_id=dataset["id"], labels_mode=self.labels_mode.currentData(), settings=self.collect_settings())

    def detect_and_review(self):
        self.labels_mode.setCurrentIndex(self.labels_mode.findData("auto"))
        self.extract_features()

    def refresh_results(self, checked=False, quiet=False):
        dataset = self.selected_dataset()
        self.classifier.set_object(None)
        self.classifier.set_progress(0, 0)
        self.classifier.set_enabled_current(False)
        self._manual_report = {}
        self.object_gallery.set_rows([], None)
        self.object_view.clear(tr("Выберите объект в таблице для проверки маски"))
        csv_path = dataset.get("last_csv") if dataset else None
        if not csv_path or not Path(csv_path).is_file():
            self.results_table.clear()
            if dataset and dataset.get("results_dir"):
                self.results_summary.setText(tr("Результаты требуют пересчёта: разметка или состав тайлов изменились"))
            else:
                self.results_summary.setText(tr("Признаки ещё не рассчитаны") if dataset else tr("Выберите набор для просмотра результатов"))
            return
        if not self.service.results_are_current(dataset):
            self.results_table.clear()
            self.results_summary.setText(tr("Результаты требуют пересчёта: разметка или состав тайлов изменились"))
            return
        try:
            self.results_table.load_csv(csv_path)
            self.object_gallery.set_rows(self.results_table.rows, dataset)
            self.refresh_manual_labels()
            if self.object_gallery.visible_rows:
                first = self.object_gallery.visible_rows[0]
                self.object_gallery.select_object(first['Tile_Name'], first['Object_ID'])
            self.results_summary.setText(tr('{v0} объектов · {v1}', v0=len(self.results_table.rows), v1=Path(csv_path).name))
            self.results_summary.setToolTip(csv_path)
            if not quiet:
                self._log(tr("Результаты обновлены"))
        except Exception as exc:
            self.results_table.clear()
            self.object_gallery.set_rows([], None)
            self.results_summary.setText(tr("Не удалось открыть CSV: ") + str(exc))
            if not quiet:
                self._error(exc)

    def _result_selected(self, row):
        if self._syncing_object:
            return
        self._syncing_object = True
        try:
            self.object_gallery.select_object(row.get("Tile_Name"), row.get("Object_ID"))
        finally:
            self._syncing_object = False
        dataset = self.selected_dataset()
        self.classifier.set_object(row)
        if not dataset or not dataset.get("results_dir"):
            return
        folder = Path(dataset["results_dir"]) / "verification_masks" / row.get("Tile_Name", "")
        try:
            object_id = int(row.get("Object_ID", 0))
            files = sorted(folder.glob(f"obj_{object_id:03d}_*.png"))
            if files:
                self.object_view.set_image(files[0], tr('Объект {v0} · {v1} · {v2}', v0=object_id, v1=tr(row.get('Class_Name', 'Unknown')), v2=tr(row.get('Measurement_Space', 'source_pixels'))))
            else:
                self.object_view.clear(tr("Сохранённая маска объекта отсутствует"))
        except (ValueError, TypeError):
            self.object_view.clear(tr("Некорректный идентификатор объекта"))

    def _gallery_selected(self, row):
        if self._syncing_object:
            return
        self._syncing_object = True
        try:
            if not self.results_table.select_object(row.get("Tile_Name"), row.get("Object_ID")):
                # Gallery and table have independent filters. Reveal the selected
                # object in the scientific table so saving always targets it.
                self.results_table.search.clear()
                self.results_table.class_filter.setCurrentIndex(0)
                self.results_table.select_object(row.get("Tile_Name"), row.get("Object_ID"))
        finally:
            self._syncing_object = False
        self._result_selected(row)

    def _gallery_selection_cleared(self):
        if self.review_tabs.currentIndex() == 0 and not self._syncing_object:
            self.results_table.table.clearSelection()
            self.classifier.set_object(None)
            self.object_view.clear(tr("No objects match these filters"))

    def _review_mode_changed(self, index):
        if index == 0:
            row = self.object_gallery.selected_row()
            if row is not None:
                self._gallery_selected(row)
            elif self.object_gallery.visible_rows:
                first = self.object_gallery.visible_rows[0]
                self.object_gallery.select_object(first['Tile_Name'], first['Object_ID'])
            else:
                self._gallery_selection_cleared()
        elif index == 1:
            row = self.results_table.selected_row()
            if row is not None:
                self._result_selected(row)
            else:
                self.classifier.set_object(None)
                self.object_view.clear(tr("Выберите объект в таблице для проверки маски"))

    def refresh_manual_labels(self):
        dataset = self.selected_dataset()
        if not dataset or not self.results_table.source_path:
            self.classifier.set_enabled_current(False)
            return
        try:
            report = self.service.get_object_labels(dataset)
            self._manual_report = report
            self.results_table.set_manual_labels(report)
            self.object_gallery.set_manual_labels(report)
            self.classifier.set_progress(report.get("assigned", 0), report.get("total", 0))
            self.classifier.set_enabled_current(report.get("current", True) and self.process is None)
            self.classifier.set_object(self.results_table.selected_row())
        except Exception as exc:
            self.classifier.set_enabled_current(False)
            self._log(tr("Ошибка: ") + tr(str(exc)))

    def assign_manual_class(self, class_key, save_and_next=False):
        dataset, row = self.selected_dataset(), self.results_table.selected_row()
        if dataset is None or row is None or self.process is not None:
            return
        try:
            report = self.service.assign_object_class(self.project, dataset["id"],
                row["Tile_Name"], row["Object_ID"], class_key)
            self._manual_report = report
            previous = dict(row)
            self.results_table.set_manual_labels(report)
            self.object_gallery.set_manual_labels(report)
            self.classifier.set_progress(report.get("assigned", 0), report.get("total", 0))
            selected = self.results_table.selected_row()
            self.classifier.set_object(selected)
            if selected is None:
                self.object_view.clear(tr("Выберите объект в таблице для проверки маски"))
            self._log(tr("Manual class saved"))
            if save_and_next:
                if self.review_tabs.currentIndex() == 0 and self.object_gallery.visible_rows:
                    # If the unclassified filter removed this object, its next
                    # visible neighbour is already selected by the gallery.
                    if self.object_gallery.select_object(previous["Tile_Name"], previous["Object_ID"]):
                        self.navigate_objects("next")
                    elif self.object_gallery.selected_row() is None:
                        first = self.object_gallery.visible_rows[0]
                        self.object_gallery.select_object(first["Tile_Name"], first["Object_ID"])
                else:
                    self.navigate_objects("next")
        except Exception as exc:
            self._error(exc)
            self.classifier.set_enabled_current(self.service.results_are_current(dataset))

    def navigate_objects(self, direction):
        target = self.object_gallery if self.review_tabs.currentIndex() == 0 else self.results_table
        row = target.navigate(direction)
        if row is None and direction == "unlabeled":
            self.statusBar().showMessage(tr("No unclassified objects match the current filters"), 8000)

    def export_training_results(self):
        dataset = self._require_dataset()
        if dataset is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, tr("Export training data"),
            f"{dataset.get('name', 'fibers')}_training.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            result = self.service.export_training_csv(dataset, path, only_labeled=True)
            self._log(tr("Exported {rows} objects to {path}", rows=result["rows"], path=result["path"]))
        except Exception as exc:
            self._error(exc)

    def _open_folder(self, path):
        if path and Path(path).is_dir():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(Path(path).resolve())))
        else:
            self._error(tr("Папка ещё не создана."))

    def open_labels_folder(self):
        dataset = self._require_dataset()
        if dataset:
            self._open_folder(dataset.get("labels_dir"))

    def open_results_folder(self):
        dataset = self._require_dataset()
        if dataset:
            self._open_folder(dataset.get("results_dir"))

    def export_results(self):
        dataset = self._require_dataset()
        if dataset is None:
            return
        if not self.results_table.source_path:
            self._error(tr("Сначала рассчитайте признаки."))
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, tr("Экспорт результатов"), f"{dataset.get('name', 'fibers')}_features.csv", "CSV (*.csv)")
        if path:
            try:
                self.service.export_csv(dataset, path)
                self._log(tr("CSV сохранён: ") + path)
            except Exception as exc:
                self._error(exc)

    def export_filtered_results(self):
        if not self.results_table.source_path:
            self._error(tr("Сначала рассчитайте признаки."))
            return
        dataset = self.selected_dataset()
        if not dataset or not self.service.results_are_current(dataset):
            self.refresh_results(quiet=True)
            self._error(tr("Разметка или состав тайлов изменились. Пересчитайте признаки перед экспортом."))
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, tr("Экспорт видимых строк"), "fibers_selection.csv", "CSV (*.csv)")
        if path:
            try:
                count = self.results_table.export_filtered(path)
                self._log(tr('Экспортировано объектов: {v0} · {v1}', v0=count, v1=path))
            except Exception as exc:
                self._error(exc)

    def build_request(self, action, **kwargs):
        return {"project_path": str(self.project.path), "action": action, "language": self.language, **kwargs}

    def start_job(self, action, **kwargs):
        if self.process is not None:
            self._error(tr("Дождитесь завершения текущей задачи или остановите её."))
            return False
        try:
            self.project.settings = PipelineSettings.from_dict(kwargs.get("settings", self.collect_settings())).to_dict()
            self.project.save()
            self._saved_settings_snapshot = dict(self.project.settings)
            folder = Path(self.project.workspace) / "jobs"
            folder.mkdir(parents=True, exist_ok=True)
            self.request_path = folder / (datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:10] + ".json")
            request = self.build_request(action, **kwargs)
            self.request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
            self._stdout_buffer = self._stderr_buffer = b""
            self._job_result = self._job_error = None
            self._job_action = action
            self._cancel_requested = False
            self._elapsed_timer.start()
            self._elapsed_update.start()
            self._update_elapsed()
            self.process = QtCore.QProcess(self)
            self.process.setWorkingDirectory(str(Path(__file__).resolve().parents[2]))
            self.process.setProgram(sys.executable)
            self.process.setArguments(["-u", "-m", "src.desktop.worker", "--request", str(self.request_path)])
            environment = QtCore.QProcessEnvironment.systemEnvironment()
            environment.insert("PYTHONIOENCODING", "utf-8")
            environment.insert("PYTHONUNBUFFERED", "1")
            self.process.setProcessEnvironment(environment)
            self.process.readyReadStandardOutput.connect(self._read_stdout)
            self.process.readyReadStandardError.connect(self._read_stderr)
            self.process.errorOccurred.connect(self._process_error)
            self.process.finished.connect(self._process_finished)
            self._set_busy(True)
            self.progress.setRange(0, 0)
            self.job_status.setText(stage_name(action, action) + tr(" · запуск…"))
            self._log(tr("Запуск: ") + stage_name(action, action))
            self.process.start()
            return True
        except Exception as exc:
            self.process = None
            self._set_busy(False)
            self._error(exc)
            return False

    def _set_busy(self, busy):
        self._busy = bool(busy)
        for button in self._job_buttons:
            button.setEnabled(not busy)
        self.dataset_combo.setEnabled(not busy and bool(self.project.datasets))
        self.language_combo.setEnabled(not busy)
        self.classifier.setEnabled(not busy)
        self.classifier.set_enabled_current(not busy and self._manual_report.get("current", False))
        self.classifier.export_button.setEnabled(
            not busy and self._manual_report.get("current", False)
            and self._manual_report.get("assigned", 0) > 0)
        self.source_table.setEnabled(not busy)
        for field in self._settings_fields.values():
            field.setEnabled(not busy)
        self._update_filter_controls()
        self.labels_mode.setEnabled(not busy)
        self.restore_defaults_action.setEnabled(not busy)
        self.restore_saved_action.setEnabled(not busy)
        self.settings_feedback_restore.setEnabled(not busy)
        self._refresh_settings_validation()
        self.cancel_button.setEnabled(busy and not self._cancel_requested)

    def _read_stdout(self):
        if self.process is None:
            return
        self._stdout_buffer += bytes(self.process.readAllStandardOutput())
        while b"\n" in self._stdout_buffer:
            line, self._stdout_buffer = self._stdout_buffer.split(b"\n", 1)
            self._handle_line(line.decode("utf-8", errors="replace").rstrip("\r"))

    def _read_stderr(self):
        if self.process is None:
            return
        self._stderr_buffer += bytes(self.process.readAllStandardError())
        while b"\n" in self._stderr_buffer:
            line, self._stderr_buffer = self._stderr_buffer.split(b"\n", 1)
            self._log(line.decode("utf-8", errors="replace").rstrip("\r"))

    def _handle_line(self, line):
        if not line.strip():
            return
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            self._log(line)
            return
        if not isinstance(event, dict) or "type" not in event:
            self._log(line)
            return
        self.handle_worker_event(event)

    def handle_worker_event(self, event):
        event_type = event.get("type")
        if event_type == "progress":
            stage = stage_name(event.get("stage"), event.get("stage", tr("Обработка")))
            message = event.get("message", "")
            current, total = event.get("current", event.get("completed")), event.get("total")
            if isinstance(total, (int, float)) and total > 0 and isinstance(current, (int, float)):
                self.progress.setRange(0, 100)
                self.progress.setValue(max(0, min(100, int(current * 100 / total))))
                suffix = f" · {int(current)} / {int(total)}"
            else:
                self.progress.setRange(0, 0)
                suffix = ""
            self.job_status.setText(tr("Останавливается…") if self._cancel_requested else stage + suffix)
            if message:
                self._log(tr(message))
        elif event_type == "result":
            self._job_result = event
            if event.get("status") in ("error", "failed"):
                self._job_error = event.get("message") or _display(event.get("summary", tr("Задача завершилась ошибкой")))
            self._log(tr("Результат: ") + _display(event.get("summary", event.get("status", ""))))
        elif event_type == "error":
            self._job_error = str(event.get("message", tr("Неизвестная ошибка")))
            self._log(tr("Ошибка: ") + self._job_error)
            if event.get("details"):
                self._log(str(event["details"]))
            self.job_status.setText(tr("Ошибка · подробности в журнале"))
        elif event_type == "log":
            self._log(str(event.get("message", "")))

    def _process_error(self, error):
        if self.process is None:
            return
        self._job_error = self.process.errorString()
        self._log(tr("Ошибка процесса: ") + self._job_error)
        # FailedToStart does not reliably emit finished across Qt bindings.
        if error == QtCore.QProcess.ProcessError.FailedToStart:
            self._process_finished(1, QtCore.QProcess.ExitStatus.CrashExit)

    def _process_finished(self, exit_code, exit_status):
        if self.process is None:
            return
        self._read_stdout()
        self._read_stderr()
        if self._stdout_buffer:
            self._handle_line(self._stdout_buffer.decode("utf-8", errors="replace"))
            self._stdout_buffer = b""
        if self._stderr_buffer:
            self._log(self._stderr_buffer.decode("utf-8", errors="replace"))
            self._stderr_buffer = b""
        result = self._job_result
        cancelled = bool(result and result.get("status") == "cancelled")
        succeeded = exit_code == 0 and exit_status == QtCore.QProcess.ExitStatus.NormalExit and result is not None and not self._job_error and not cancelled
        if cancelled:
            self.job_status.setText(tr("Остановлено · завершённые результаты сохранены"))
        elif succeeded:
            self.job_status.setText(stage_name(self._job_action, tr("Задача")) + tr(" · завершено"))
        else:
            detail = self._job_error or (tr("Обработчик не подтвердил результат") if result is None else tr('Код завершения: {v0}', v0=exit_code))
            self.job_status.setText(tr("Ошибка · подробности в журнале"))
            self._log(tr("Задача не завершена: ") + detail)
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if succeeded else 0)
        self._elapsed_update.stop()
        if self._elapsed_timer.isValid():
            self._update_elapsed()
        old_process, self.process = self.process, None
        old_process.deleteLater()
        self._set_busy(False)
        try:
            self.project = self.Project.load(self.project.path)
            self.refresh_project()
            if succeeded and self._job_action == "preview":
                paths = result.get("paths") or result.get("summary", {})
                if not isinstance(paths, dict):
                    paths = result
                for key, viewer in (("input_path", self.input_preview), ("filtered_path", self.filtered_preview), ("mask_path", self.protective_preview)):
                    filename = result.get(key) or paths.get(key)
                    if filename:
                        viewer.set_image(filename)
                self.sidebar.setCurrentRow(1)
            elif succeeded and self._job_action in ("prepare", "connect", "overview"):
                self.sidebar.setCurrentRow(2)
            elif succeeded and self._job_action == "extract":
                self.sidebar.setCurrentRow(4)
            elif succeeded and self._job_action == "import_labels":
                self.sidebar.setCurrentRow(3)
            elif succeeded and self._job_action == "pick_tile":
                self._select_tile_id(result.get("summary", {}).get("tile_id"))
        except Exception as exc:
            self._log(tr("Не удалось перечитать проект: ") + str(exc))
        if self._close_requested:
            self.close()

    def cancel_job(self):
        if self.process is None or self.request_path is None:
            return
        try:
            Path(str(self.request_path) + ".cancel").write_text("cancel\n", encoding="utf-8")
            self._cancel_requested = True
            self.cancel_button.setEnabled(False)
            self.job_status.setText(tr("Останавливается после текущей операции…"))
            self._log(tr("Запрошена безопасная остановка. Текущая операция может требовать времени."))
        except Exception as exc:
            self._error(exc)

    def closeEvent(self, event):
        if self.process is not None:
            question = QtWidgets.QMessageBox(self)
            question.setWindowTitle(tr("Задача выполняется"))
            question.setText(tr("Остановить задачу и закрыть приложение после безопасного завершения текущей операции?"))
            question.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
            question.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)
            question.button(QtWidgets.QMessageBox.StandardButton.Yes).setText(tr("Yes"))
            question.button(QtWidgets.QMessageBox.StandardButton.No).setText(tr("No"))
            answer = question.exec()
            if answer == QtWidgets.QMessageBox.StandardButton.Yes:
                self._close_requested = True
                self.cancel_job()
            event.ignore()
            return
        try:
            if not self._persist_settings(skip_invalid=True):
                self._log(tr('Invalid settings were not saved. The previous saved values were kept.'))
        except Exception:
            pass
        self.preferences.setValue("main/geometry", self.saveGeometry())
        self._save_panel_layouts(dispose=True)
        if self._help_center is not None:
            self._help_center.close()
        # Let outstanding thumbnail readers finish before Qt objects disappear.
        image_pool().waitForDone(3000)
        self._project_lock.unlock()
        event.accept()
