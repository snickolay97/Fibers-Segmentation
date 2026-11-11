"""SoLoData desktop workflow; expensive operations run in a worker process."""

import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

from .qt import QtCore, QtGui, QtWidgets, configure_font, show_centered_window
from .widgets import CsvTable, ImageViewer, image_pool
from .source_viewer import ReadTiffViewTask, SourceViewer
from .branding import app_icon
from .input_safety import install_parameter_wheel_guard
from .parameter_inputs import ParameterSpinBox, ParameterDoubleSpinBox
from .source_options import calibration_mode
from .i18n import tr, get_language, set_language, register_translations
from .help import attach_help, help_label
from .channel_composite_dialog import ChannelCompositeDialog
from .image_comparison import add_comparison
from .image_controls import size_action, tool_icon
from .object_classifier import ObjectClassifier
from .object_review import ObjectReviewGallery
from .workspace import DockWorkspace
from src.app_settings import PipelineSettings, search_window_end_range, straight_shift_limits
from src.default_settings import FACTORY_DEFAULTS, STRAIGHT_SHIFT_FIELDS
from .settings_safety import recover_project_settings
from .help_center import HelpCenter
from .parameter_reference import parameter_entry
from .model_evaluation_ui import ModelEvaluationPage
from .object_prediction_ui import PredictionReviewDialog, PredictionSetupDialog
from .segmentation_review import SegmentationReview
from .analysis_page import AnalysisPage
from . import black_tile_text
from .tile_edit import TileEditContext
from .image_ruler import measurement_ruler_scale, tile_ruler_scale
from .editor_preferences import read_profile, write_profile
from .settings_dialog import SettingsDialog
from .database_dialog import DatabaseDialog
from .storage_names import version_file
from .pixel_segmentation_ui import PixelSegmentationDialog, overlay_legend
from .yolo_preview import add_yolo_status, show_yolo_polygons
from src.tile_edits import tile_artifact_path

_PREVIEW_TEXT = {
    'Edit selected tile…': ('Редактировать выбранный тайл…', 'עריכת האריח הנבחר…'),
    'View at source resolution…': ('Просмотр в исходном разрешении…', 'תצוגה ברזולוציית המקור…'),
    'Exact ownership · white pixels belong to the selected tile': (
        'Точная принадлежность · белые пиксели принадлежат выбранному тайлу',
        'שיוך מדויק · פיקסלים לבנים שייכים לאריח הנבחר'),
    'This tile owns its entire native crop.': (
        'Тайлу принадлежит весь native-фрагмент.', 'כל חיתוך המקור שייך לאריח זה.'),
    'No saved ownership mask for this tile.': (
        'Для этого тайла нет сохранённой маски принадлежности.', 'אין מסכת שיוך שמורה לאריח זה.'),
    'Select a TIFF to view its source channel.': (
        'Выберите TIFF, чтобы увидеть исходный канал.', 'בחרו TIFF כדי להציג את ערוץ המקור.'),
    'Calculate the preview to see filtering and the protective mask.': (
        'Рассчитайте предпросмотр, чтобы увидеть фильтрацию и защитную маску.',
        'חשבו את התצוגה המקדימה כדי לראות את הסינון ואת מסכת ההגנה.'),
    'Saved preview. Recalculate after changing the channel, plane or filters.': (
        'Сохранённый предпросмотр. После смены канала, плоскости или фильтров пересчитайте его.',
        'תצוגה מקדימה שמורה. חשבו אותה מחדש לאחר שינוי הערוץ, המישור או המסננים.'),
    'Channel {channel}, plane {plane}': (
        'Канал {channel}, плоскость {plane}', 'ערוץ {channel}, מישור {plane}'),
}
register_translations({key: text[0] for key, text in _PREVIEW_TEXT.items()},
                      hebrew={key: text[1] for key, text in _PREVIEW_TEXT.items()})

register_translations({
    'Overview predates the active edits. Choose Rebuild overview.': 'Карта создана до активных правок. Нажмите «Обновить карту».',
    'Native source pixels for editing': 'Исходные native-пиксели для редактирования',
    'Use saved edit…': 'Использовать сохранённую правку…',
    'Restore prepared tile': 'Вернуть подготовленный тайл',
    'Active edit: {version}. Recalculate measurements after changing it.': 'Активная правка — {version}. После изменения пересчитайте измерения.',
    'Tile edits changed during measurement. Recalculate the features.': 'Правки тайлов изменились во время измерения. Пересчитайте признаки.',
    'Tile saved for measurement. Recalculate the features.': 'Тайл сохранён для измерений. Пересчитайте признаки.',
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

register_translations({}, hebrew={
    'Overview predates the active edits. Choose Rebuild overview.': 'המפה נוצרה לפני העריכות הפעילות. בחרו בנייה מחדש של המפה.',
    'Native source pixels for editing': 'פיקסלי מקור לעריכה',
    'Use saved edit…': 'שימוש בעריכה שמורה…',
    'Restore prepared tile': 'שחזור האריח המוכן',
    'Active edit: {version}. Recalculate measurements after changing it.': 'העריכה הפעילה היא {version}. חשבו מחדש את המדידות לאחר שינוי.',
    'Tile edits changed during measurement. Recalculate the features.': 'עריכות האריחים השתנו במהלך המדידה. חשבו מחדש את התכונות.',
    'Tile saved for measurement. Recalculate the features.': 'האריח נשמר למדידה. חשבו מחדש את התכונות.',
})

register_translations({
    'Straight corridor search': 'Поиск прямого коридора',
    'Initial search window end': 'Конец исходного окна поиска',
    'Window shift left / up': 'Сдвиг окна влево / вверх',
    'Window shift right / down': 'Сдвиг окна вправо / вниз',
    'Automatic': 'Автоматически',
    'Automatic or {range}': 'Автоматически или {range}',
})


_STAGES = {
    'exclude_black': 'Checking black tiles',
    'merge_objects': 'Merging objects',
    'correct_objects': 'Saving mask correction',
    'delete_objects': 'Deleting selected masks',
    'undo_object_merge': 'Restoring previous segmentation',
    'tile_edit': 'Edit tile…',
    'model_evaluation': 'Model training',
    'object_prediction': 'Review new objects…',
    'train_pixel_segmentation': 'Train pixel model',
    'apply_pixel_segmentation': 'Apply pixel model',
    'pixel_segmentation': 'Pixel segmentation…',
    'add_sources': 'Adding TIFFs', 'sources': 'Adding TIFFs',
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
_PAGE_TITLES = ("Исходники", "Подготовка", "Тайлы", "Segmentation", "Object labeling", "Model training", "Результаты")
_PAGE_HELP = ("sources", "preparation", "tiles", "segmentation", "manual_types", "model_evaluation", "results")
# Keep saved dock identities from the former Results review page.
_PAGE_WORKSPACE = ('sources', 'preparation', 'tiles', 'segmentation', 'results', None, None)
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


class ProjectLockError(RuntimeError):
    """The project cannot be acquired for this window."""


class MainWindow(QtWidgets.QMainWindow):
    """Coordinate stage views, project settings and one active worker job."""

    def __init__(self, project, parent=None, *, language=None, preferences=None):
        super().__init__(parent)
        self.setWindowIcon(app_icon())
        install_parameter_wheel_guard(self)
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
        self._storage_report = self._migrate_storage(project)
        self.process = None
        self.request_path = None
        self._stdout_buffer = b""
        self._stderr_buffer = b""
        self._job_result = None
        self._job_error = None
        self._job_action = None
        self._job_settings_draft = None
        self._cancel_requested = False
        self._close_requested = False
        self._refreshing = False
        self._dark = False
        self._ui_scale = 1.0
        self._scale_timer = QtCore.QTimer(self, singleShot=True, interval=100)
        self._scale_timer.timeout.connect(self._update_interface_scale)
        self._native_preview_request = None
        self._job_buttons = []
        self._tile_records = []
        self._selected_tile = None
        self._manual_report = {}
        self._elapsed_timer = QtCore.QElapsedTimer()
        self._elapsed_update = QtCore.QTimer(self)
        self._elapsed_update.setInterval(1000)
        self._elapsed_update.timeout.connect(self._update_elapsed)
        self._manifest = None
        self._result_tile_dialog = None
        self._settings_fields = {}
        self._loaded_setting_values = {}
        self._workspaces = {}
        self._syncing_object = False
        self._busy = False
        self._black_scan_attempts = set()
        self._settings_loading = False
        self._editor_profile = read_profile(self.preferences)
        self._help_center = None
        self._settings_notice_dismissed = False
        self._saved_settings_snapshot = dict(project.settings)
        self._draft_settings = PipelineSettings.from_dict(project.settings).to_dict()
        self._calibration_mode = calibration_mode(project)
        self._manual_calibration = project.settings.get('pixel_size_um')
        self._preview_source_id = None
        self._has_preparation_cache = False
        self._quick_preview_task = None
        self._quick_preview_key = None
        self.setMinimumSize(1050, 710)
        self.resize(1380, 960)
        self._build_ui()
        self._apply_theme()
        geometry = self.preferences.value("main/geometry")
        if isinstance(geometry, QtCore.QByteArray):
            self.restoreGeometry(geometry)
        self.refresh_project()
        self._show_recovery_notice()
        if self._storage_report.get('changed'):
            self._log(tr('Folder names updated. Original project backup: {path}', path=self._storage_report['backup']))
        elif self._storage_report.get('error'):
            self._log(tr('Folder rename postponed: {error}', error=self._storage_report['error']))

    @staticmethod
    def _migrate_storage(project):
        from .storage_migration import migrate_storage_names
        try:
            return migrate_storage_names(project)
        except (OSError, ValueError, KeyError, TypeError) as error:
            return dict(changed=False, error=str(error))

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
        icon = {
            'new_project': 'new', 'open_project': 'open', 'save_project': 'save', 'open_settings': 'levels',
            'add_sources': 'new', 'connect_dataset': 'open', 'preview_source': 'zoom_in',
            'open_channel_composite': 'compare', 'open_preparation_resolution': 'enlarge',
            'edit_selected_tile': 'edit',
            'open_source_viewer': 'enlarge', 'prepare_sources': 'run', 'extract_features': 'run',
            'detect_and_review': 'run', 'open_pixel_segmentation': 'edit', 'open_result_tile': 'enlarge',
            'use_saved_tile_edit': 'open', 'restore_prepared_tile': 'undo', 'open_detailed_map': 'enlarge',
            'finish_review': 'apply', 'import_labels': 'open', 'check_labels': 'apply',
        }.get(getattr(callback, '__name__', ''))
        if icon:
            button.setProperty('workflowIcon', icon)
            button.setIcon(tool_icon(button, icon))
            size_action(button, self.width())
        if job_sensitive:
            self._job_buttons.append(button)
        return button

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_scale_timer'):
            self._scale_timer.start()
        for button in self.findChildren(QtWidgets.QPushButton):
            if button.property('workflowIcon'):
                size_action(button, self.width())

    def set_language(self, language, persist=True):
        """Change presentation only; scientific settings and identifiers stay stable."""
        if language not in ("en", "ru", "he") or language == self.language or self.process is not None:
            return
        source_checks = {self.source_table.item(row, 0).data(QtCore.Qt.ItemDataRole.UserRole):
                         self.source_table.item(row, 0).checkState() for row in range(self.source_table.rowCount())}
        state = dict(page=self.sidebar.currentRow(), tile_search=self.tile_search.text(),
                     segmentation_tile=self.segmentation_review.record['id'] if self.segmentation_review.record else None,
                     segmentation_ids=self.segmentation_review.selected_ids(), segmentation_tab=self.segmentation_review.tabs.currentIndex(),
                     analysis_tab=self.analytics.tabs.currentIndex(), analysis_search=self.analytics.table.search.text(),
                     analysis_class=self.analytics.table.class_filter.currentData(),
                     tile_filter=self.tile_filter.currentData(), tile_tab=self.tile_tabs.currentIndex(),
                     gallery=self.object_gallery.filter_state(), review_tab=self.review_tabs.currentIndex(),
                     labels_mode=self.labels_mode.currentData(),
                     manual_calibration=self._manual_calibration,
                     preview_tab=self.preview_tabs.currentIndex(),
                     preview_source=self.preview_source_combo.currentData(),
                     preview_files=[(view.filename, view.ruler.scale)
                                    for view in (self.input_preview, self.filtered_preview, self.protective_preview)],
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
        self._manual_calibration = state['manual_calibration']
        self.sidebar.setCurrentRow(state["page"])
        self.analytics.tabs.setCurrentIndex(state['analysis_tab'])
        self.analytics.table.search.setText(state['analysis_search'])
        self.analytics.table.class_filter.setCurrentIndex(max(0,self.analytics.table.class_filter.findData(state['analysis_class'])))
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
        if self.preview_source_combo.currentData() == state['preview_source']:
            # A language rebuild can restore a file already shown outside the
            # saved preview registry, provided the same source is selected.
            for view, (filename, scale) in zip(
                    (self.input_preview, self.filtered_preview, self.protective_preview), state['preview_files']):
                if filename and not view.filename and Path(filename).is_file():
                    view.set_image(filename, ruler_scale=scale)
        self.log.setPlainText(state["log"])
        self.show_log.setChecked(state["log_visible"])
        self.elapsed_label.setText(state["elapsed"])
        if state['segmentation_tile'] is not None:
            self.segmentation_review.select_tile(state['segmentation_tile'])
            self.segmentation_review.select_ids(state['segmentation_ids'])
        self.segmentation_review.tabs.setCurrentIndex(state['segmentation_tab'])
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
        # Hold the project lock while workers write on behalf of this window.
        # Reject a second open immediately so the UI does not block.
        lock = QtCore.QLockFile(str(project.path) + ".lock")
        if not lock.tryLock(0):
            raise ProjectLockError(tr("Этот проект уже открыт в другом окне SoLoData. Закройте его или выберите другой проект."))
        return lock

    def _switch_project(self, project):
        """Acquire and validate the next project before releasing the current one."""
        from .project import LAST_PROJECT_KEY
        if Path(project.path).resolve() == Path(self.project.path).resolve():
            self.preferences.setValue(LAST_PROJECT_KEY, self.project.path)
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
        self._calibration_mode = calibration_mode(project)
        self.calibration_mode_combo.blockSignals(True)
        self.calibration_mode_combo.setCurrentIndex(self.calibration_mode_combo.findData(self._calibration_mode))
        self.calibration_mode_combo.blockSignals(False)
        self._settings_notice_dismissed = False
        self.project.recover_interrupted()
        self._storage_report = self._migrate_storage(project)
        self._reset_preparation_previews()
        self.refresh_project()
        self._show_recovery_notice()
        self.preferences.setValue(LAST_PROJECT_KEY, self.project.path)

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
        top.addWidget(self._button(tr('Settings…'), self.open_settings))
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
        self.database_action = self.help_menu.addAction(tr('Project database…'), self.open_project_database)
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
        self.sidebar.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for number, label in enumerate(_PAGE_TITLES, 1):
            self.sidebar.addItem(f"{number:02d}   {tr(label)}")
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
        dataset_label = QtWidgets.QLabel(tr("Набор:"))
        heading.addWidget(dataset_label)
        self.dataset_combo = QtWidgets.QComboBox()
        self.dataset_combo.setMinimumWidth(250)
        self.dataset_combo.setPlaceholderText(tr("No prepared datasets"))
        attach_help(self.dataset_combo, "dataset")
        self.dataset_combo.currentIndexChanged.connect(self._dataset_changed)
        heading.addWidget(self.dataset_combo)
        dataset_help = help_label("dataset")
        heading.addWidget(dataset_help)
        open_tiles = self._button(tr("Открыть тайлы…"), self.connect_dataset)
        attach_help(open_tiles, "open_tiles")
        heading.addWidget(open_tiles)
        self._dataset_heading = (dataset_label, self.dataset_combo, dataset_help, open_tiles)
        content_layout.addLayout(heading)
        self.dataset_status = self._note(tr("Добавьте TIFF или подключите готовую нарезку"))
        content_layout.addWidget(self.dataset_status)
        self.pages = QtWidgets.QStackedWidget()
        self.pages.addWidget(self._sources_page())
        self.pages.addWidget(self._prepare_page())
        self.pages.addWidget(self._tiles_page())
        self.pages.addWidget(self._labels_page())
        self.pages.addWidget(self._results_page())
        self.model_evaluation = ModelEvaluationPage(self)
        self.pages.addWidget(self.model_evaluation)
        self.analytics = AnalysisPage()
        self.pages.addWidget(self.analytics)
        for label, callback, key in (
                ('Обновить результаты', self.refresh_results, 'open_measurements'),
                ('Экспорт всей таблицы', self.export_results, 'results'),
                ('Экспорт видимых строк', self.export_analysis_filtered, 'results'),
                ('Export Excel workbook', self.export_excel, 'excel_export'),
                ('Export ML bundle', self.export_ml, 'ml_bundle')):
            self.analytics.actions.addWidget(attach_help(self._button(tr(label),callback),key))
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
        key = _PAGE_WORKSPACE[self.pages.currentIndex()]
        if key in self._workspaces:
            self._workspaces[key].populate_menu(self.panels_menu)

    def _save_panel_layouts(self, dispose=False):
        self.preferences.setValue('workspaces/tiles/vertical_split', self.tile_splitter.saveState())
        self.preferences.setValue('workspaces/tiles/vertical_split_scale', self._ui_scale)
        self.preferences.setValue('workspaces/preparation/comparison', self.preview_comparison.saveState())
        self.preferences.setValue('workspaces/segmentation/comparison', self.segmentation_review.comparison.saveState())
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
        values = self.collect_settings()
        if self._calibration_mode == 'auto':
            values['pixel_size_um'] = self._settings_fields['pixel_size_um'].value() or None
        if self._help_center is None:
            self._help_center = HelpCenter(parent=self, current_settings=values, language=self.language)
        else:
            self._help_center.refresh_settings(values)
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
        self.show_help(_PAGE_HELP[self.sidebar.currentRow()])

    def eventFilter(self, watched, event):
        if isinstance(watched, QtWidgets.QLabel) and watched.objectName() == "helpBadge":
            activated = (event.type() == QtCore.QEvent.Type.MouseButtonRelease
                         and event.button() == QtCore.Qt.MouseButton.LeftButton)
            activated |= (event.type() == QtCore.QEvent.Type.KeyPress
                          and event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter, QtCore.Qt.Key.Key_Space))
            if activated:
                key = watched.property("helpKey")
                if not key:
                    key = _PAGE_HELP[self.sidebar.currentRow()]
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
            self._request_quick_preview()
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
        values = self.collect_settings()
        end_range = search_window_end_range(values['target_size'])
        shift_limits = straight_shift_limits(values['target_size'], values['search_window_end'])
        end_field = self._settings_fields['search_window_end']
        # Keep a previously entered value visible after shrinking the tile.
        end_field.setMaximum(max(end_field.value(), min(end_range[1], 2147483647)))
        self._sync_straight_shift_sliders(shift_limits)
        issues = inspect_settings(values)
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
            default = FACTORY_DEFAULTS.get(key, '—')
            if key == 'search_window_end':
                allowed = tr('Automatic or {range}', range=f'{end_range[0]}–{end_range[1]} px')
                default = tr('Automatic')
            if key in shift_limits:
                allowed = f"0–{shift_limits[key]} px"
                if key == 'straight_shift_left':
                    allowed = tr('Automatic or {range}', range=allowed)
                    default = tr('Automatic')
            self.settings_feedback_text.setText(tr(
                'Invalid setting: {name}. Allowed: {allowed}. Factory default: {default}.',
                name=self._setting_title(key), allowed=allowed, default=default))
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
        self.project._extra_fields['calibration_mode'] = self._calibration_mode
        self.project.save()
        self._saved_settings_snapshot = dict(values)
        return True

    def restore_factory_settings(self):
        if not self._busy:
            self._load_settings(dict(FACTORY_DEFAULTS))
            self.statusBar().showMessage(tr('Factory defaults restored. They apply to future processing.'), 8000)

    def restore_saved_settings(self):
        if not self._busy:
            self._calibration_mode = calibration_mode(self.project)
            self.calibration_mode_combo.blockSignals(True)
            self.calibration_mode_combo.setCurrentIndex(self.calibration_mode_combo.findData(self._calibration_mode))
            self.calibration_mode_combo.blockSignals(False)
            self._load_settings(PipelineSettings.from_dict(self._saved_settings_snapshot).to_dict())
            self.statusBar().showMessage(tr('Saved settings restored.'), 8000)

    def open_settings(self):
        if self._busy:
            return
        profile = read_profile(self.preferences)
        dialog = SettingsDialog(self, self.collect_settings(), self._calibration_mode, profile)
        accepted = dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted
        draft, remember = dialog.result_values, dialog.personal.isChecked()
        ui_scale, cursor = dialog.ui_scale.currentData(), dialog.drawing_cursor.currentData()
        dialog.deleteLater()
        if not accepted:
            return
        mode = draft['calibration_mode']
        prior_settings = self.project.settings
        prior_extra = self.project._extra_fields.copy()
        self.project.settings = draft['processing']
        self.project._extra_fields['calibration_mode'] = mode
        try:
            self.project.save()
        except (OSError, ValueError) as error:
            self.project.settings = prior_settings
            self.project._extra_fields = prior_extra
            self._error(error)
            return
        self._saved_settings_snapshot = dict(draft['processing'])
        self._calibration_mode = mode
        with QtCore.QSignalBlocker(self.calibration_mode_combo):
            self.calibration_mode_combo.setCurrentIndex(self.calibration_mode_combo.findData(mode))
        self._load_settings(draft['processing'])
        profile.update(tile=draft['tile'], mask=draft['mask'])
        if remember:
            profile.update(processing=draft['processing'], calibration_mode=mode)
        write_profile(self.preferences, profile)
        self._editor_profile = profile
        self.segmentation_review.editor_defaults = profile['mask']
        self.preferences.setValue('appearance/scale', ui_scale)
        self.preferences.setValue('appearance/drawing_cursor', cursor)
        self.preferences.sync()
        self._update_interface_scale()
        self._log(tr("Проект сохранён: ") + str(self.project.path))

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
        field = ParameterDoubleSpinBox() if decimal else ParameterSpinBox()
        field.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.PlusMinus)
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

    def _sync_straight_shift_sliders(self, limits):
        for key, slider in self._straight_shift_sliders.items():
            field = self._settings_fields[key]
            limit = min(limits[key], 2147483647)
            # Keep an out-of-range draft visible when the user shrinks the tile.
            field.setMaximum(max(field.value(), limit))
            with QtCore.QSignalBlocker(slider):
                slider.setMaximum(limit)
                slider.setValue(limit if field.value() == -1 else field.value())
            slider.setEnabled(field.isEnabled() and not field.isReadOnly())

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
        search = QtWidgets.QGroupBox(tr("Straight corridor search"))
        search_form = QtWidgets.QFormLayout(search)
        search_form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        self._straight_shift_sliders = {}
        factory_size = FACTORY_DEFAULTS['target_size']
        end_field = self._spin('search_window_end', -1, factory_size, -1)
        end_field.setSuffix(' px')
        end_field.setSpecialValueText(tr('Automatic'))
        self._form_row(search_form, 'Initial search window end', end_field, 'search_window_end')
        limits = straight_shift_limits(factory_size)
        for key, title in zip(STRAIGHT_SHIFT_FIELDS, ("Window shift left / up", "Window shift right / down")):
            default = FACTORY_DEFAULTS[key]
            field = self._spin(key, -1 if default is None else 0, limits[key], -1 if default is None else default)
            field.setSuffix(" px")
            if default is None:
                field.setSpecialValueText(tr("Automatic"))
            slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
            slider.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
            slider.setRange(0, limits[key])
            slider.setAccessibleName(tr(title))
            slider.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
            slider.customContextMenuRequested.connect(
                lambda position, k=key, w=slider: self._parameter_menu(w, k, position))
            attach_help(slider, key)
            slider.valueChanged.connect(field.setValue)
            self._straight_shift_sliders[key] = slider
            row = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(slider, 1)
            row_layout.addWidget(field)
            self._form_row(search_form, title, row, key)
        form.addRow(search)
        self._form_row(form, tr("Размер обзорной карты"), self._spin("overview_size", 200, 12000, 6000), "overview_size")
        self._form_row(form, tr("Канал (нумерация с 0)"), self._spin("channel", 0, 31, 0), "channel")
        plane = self._spin("plane", 0, 100000, 0)
        self._form_row(form, tr("TIFF slice / frame (0-based)"), plane, "plane")
        pixel = self._spin("pixel_size_um", 0, 100000, 0, True)
        pixel.setDecimals(6)
        pixel.setSpecialValueText(tr("Не задана · исходные px"))
        calibration_row = QtWidgets.QWidget()
        calibration_layout = QtWidgets.QVBoxLayout(calibration_row)
        calibration_layout.setContentsMargins(0,0,0,0)
        self.calibration_mode_combo = QtWidgets.QComboBox()
        self.calibration_mode_combo.addItem(tr('From TIFF metadata'), 'auto')
        self.calibration_mode_combo.addItem(tr('Manual / source pixels'), 'manual')
        self.calibration_mode_combo.setCurrentIndex(self.calibration_mode_combo.findData(self._calibration_mode))
        attach_help(self.calibration_mode_combo, 'pixel_size_um')
        calibration_layout.addWidget(self.calibration_mode_combo)
        calibration_layout.addWidget(pixel)
        self.calibration_note = self._note('')
        calibration_layout.addWidget(self.calibration_note)
        self._form_row(form, tr("Калибровка µm/px"), calibration_row, "pixel_size_um")
        self.calibration_mode_combo.currentIndexChanged.connect(self._calibration_mode_changed)
        self.plane_note = self._note('')
        form.addRow(self.plane_note)
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
        self.preparation_views = (self.input_preview, self.filtered_preview, self.protective_preview)
        for index, (view, key) in enumerate(zip(self.preparation_views, ('prep_source', 'prep_filtering', 'prep_mask'))):
            view.set_view_help(key)
            view.resolution_action = lambda i=index: self.open_preparation_resolution(i)
            self.preview_tabs.setTabToolTip(index, view.view.toolTip())
        self.preview_comparison = add_comparison(self.preview_tabs, 0, 1, 'preparation')
        self._has_preparation_cache = False
        self._quick_preview_key = None
        saved_split = self.preferences.value('workspaces/preparation/comparison')
        if isinstance(saved_split, QtCore.QByteArray):
            self.preview_comparison.restoreState(saved_split)
        workspace.after_reset = lambda: self.preview_comparison.setSizes([1, 1])
        settings_dock = workspace.add_panel("settings", "Processing settings", scroll)
        images = QtWidgets.QWidget()
        images_layout = QtWidgets.QVBoxLayout(images)
        images_layout.setContentsMargins(0, 0, 0, 0)
        preview_actions = QtWidgets.QHBoxLayout()
        self.preparation_preview_note = self._note(tr('Select a TIFF to view its source channel.'))
        preview_actions.addWidget(self.preparation_preview_note, 1)
        preview_actions.addWidget(self._button(tr("Предпросмотр выбранного TIFF"), self.preview_source))
        images_layout.addLayout(preview_actions)
        resolution_row = QtWidgets.QHBoxLayout()
        resolution_row.addStretch()
        self.preparation_resolution = self._button(tr('View at source resolution…'), self.open_preparation_resolution)
        resolution_row.addWidget(attach_help(self.preparation_resolution, 'prep_resolution'))
        images_layout.addLayout(resolution_row)
        images_layout.addWidget(self.preview_tabs, 1)
        images_dock = workspace.add_panel("images", "Image previews", images, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        workspace.resizeDocks([settings_dock, images_dock], [355, 750], QtCore.Qt.Orientation.Horizontal)
        workspace.finish_layout()
        layout.addWidget(workspace, 1)
        layout.addWidget(self._note(tr('Preview processes the whole selected TIFF before reducing it for display. It can take time; unchanged completed previews are reused.')))
        actions = QtWidgets.QHBoxLayout()
        self.preview_source_combo = QtWidgets.QComboBox()
        attach_help(self.preview_source_combo, 'source_selection')
        self.preview_source_combo.currentIndexChanged.connect(self._preview_source_changed)
        actions.addWidget(self.preview_source_combo, 1)
        self.whole_tiff_button = self._button(tr('View whole TIFF…'), self.open_source_viewer)
        actions.addWidget(attach_help(self.whole_tiff_button, 'source_viewer'))
        self.combine_channels_button = self._button(tr('Combine TIFF channels…'), self.open_channel_composite)
        actions.addWidget(attach_help(self.combine_channels_button, 'channel_composite'))
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
        self.model_view = ImageViewer(empty_text=tr("Выберите тайл из списка или нажмите на карту"), full_when_safe=True)
        self.native_view = ImageViewer(empty_text=tr("Native-фрагмент сохраняет исходный пространственный масштаб"), full_when_safe=True)
        self.model_view.tile_saved.connect(self._tile_edit_saved)
        self.native_view.tile_saved.connect(self._tile_edit_saved)
        self.ownership_view = ImageViewer(empty_text=tr("Маска принадлежности пикселей тайлу"), full_when_safe=True)
        self.ownership_view.view.setBackgroundBrush(QtGui.QColor('#34454d'))
        self.ownership_view.view.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, False)
        self.polygon_view = ImageViewer(empty_text=tr("Полигонная разметка выбранного тайла"), full_when_safe=True)
        self.polygon_status = add_yolo_status(self.polygon_view)
        for viewer, title in ((self.overview_view, tr("Карта")), (self.model_view, tr("Модельный")),
                              (self.native_view, "Native"), (self.ownership_view, tr("Принадлежность")),
                              (self.polygon_view, tr("Полигоны"))):
            self.tile_tabs.addTab(viewer, title)
        for index, key in enumerate(('tile_overview', 'tile_model', 'tile_native', 'tile_ownership', 'tile_polygons')):
            viewer = self.tile_tabs.widget(index)
            viewer.set_view_help(key)
            self.tile_tabs.setTabToolTip(index, viewer.view.toolTip())
        self.overview_view.resolution_action = self.open_detailed_map
        self.edit_selected_tile_button = self._button(tr('Edit selected tile…'), self.edit_selected_tile, job_sensitive=False)
        self.edit_selected_tile_button.setEnabled(False)
        self.native_view.loaded.connect(lambda *_: self.edit_selected_tile_button.setEnabled(
            self.native_view._tile_editor is not None and self.process is None))
        self.native_view.failed.connect(lambda *_: self.edit_selected_tile_button.setEnabled(False))
        self.tile_tabs.setCornerWidget(attach_help(self.edit_selected_tile_button, 'tile_editor'))
        list_dock = workspace.add_panel("browser", "Tile browser", list_panel)
        image_dock = workspace.add_panel("images", "Tile images", self.tile_tabs, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        workspace.resizeDocks([list_dock, image_dock], [210, 900], QtCore.Qt.Orientation.Horizontal)
        self.tile_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.tile_splitter.setChildrenCollapsible(False)
        self.tile_splitter.setHandleWidth(9)
        self.tile_splitter.addWidget(workspace)
        layout.addWidget(self.tile_splitter, 1)
        controls_panel = QtWidgets.QWidget()
        controls_layout = QtWidgets.QVBoxLayout(controls_panel)
        controls_layout.setContentsMargins(4, 4, 4, 4)
        self.tile_details = self._note(tr("На карте выбор определяется точной маской принадлежности пикселей."))
        controls_layout.addWidget(self.tile_details)
        actions = QtWidgets.QHBoxLayout()
        self.exclude_specs = QtWidgets.QLineEdit()
        self.exclude_specs.setPlaceholderText(tr("ID: 4, 12-18 · или выделите тайлы"))
        attach_help(self.exclude_specs, "tile_ids")
        actions.addWidget(self.exclude_specs, 1)
        actions.addWidget(help_label("tile_ids"))
        actions.addWidget(self._button(tr("Исключить"), lambda: self.change_exclusion(True)))
        actions.addWidget(self._button(tr("Вернуть"), lambda: self.change_exclusion(False)))
        controls_layout.addLayout(actions)
        map_actions = QtWidgets.QHBoxLayout()
        self.use_saved_edit_button = self._button(tr('Use saved edit…'), self.use_saved_tile_edit)
        self.restore_tile_button = self._button(tr('Restore prepared tile'), self.restore_prepared_tile)
        for button in (self.use_saved_edit_button, self.restore_tile_button):
            attach_help(button, 'tile_editor')
            map_actions.addWidget(button)
        map_actions.addStretch()
        self.check_black_button = self._button(tr('Check black tiles'),self.check_black_tiles)
        attach_help(self.check_black_button,'black_tiles')
        map_actions.addWidget(self.check_black_button)
        map_actions.addWidget(self._button(tr("Обновить карту"), self.rebuild_overview))
        self.detailed_map_button = self._button(tr("Detailed boundary map…"), self.open_detailed_map)
        attach_help(self.detailed_map_button, "detailed_map")
        map_actions.addWidget(self.detailed_map_button)
        map_actions.addWidget(self._button(tr("Проверка завершена"), self.finish_review, True))
        controls_layout.addLayout(map_actions)
        controls_scroll = QtWidgets.QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setMinimumHeight(45)
        controls_scroll.setWidget(controls_panel)
        self.tile_splitter.addWidget(controls_scroll)
        self.tile_splitter.setStretchFactor(0, 1)
        self.tile_splitter.setStretchFactor(1, 0)
        default_sizes = [650, max(145, controls_panel.sizeHint().height() + 12)]
        self.tile_splitter.setSizes(default_sizes)
        saved_split = self.preferences.value('workspaces/tiles/vertical_split')
        if isinstance(saved_split, QtCore.QByteArray):
            self.tile_splitter.restoreState(saved_split)
            try:
                stored_scale = float(self.preferences.value('workspaces/tiles/vertical_split_scale', 1))
            except (TypeError, ValueError):
                stored_scale = 1
            if 1 <= stored_scale <= 2:
                self._resize_tile_actions(self._ui_scale / stored_scale)
        workspace.after_reset = lambda: self.tile_splitter.setSizes(
            [650, max(round(145 * self._ui_scale), controls_panel.sizeHint().height() + 12)])
        workspace.finish_layout()
        return page

    def _labels_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        workspace = self._workspace("segmentation")
        settings_panel = QtWidgets.QWidget()
        settings_layout = QtWidgets.QVBoxLayout(settings_panel)
        intro = QtWidgets.QHBoxLayout()
        intro.addWidget(self._note(tr("Choose a prepared dataset, then choose how to find objects.")), 1)
        intro.addWidget(self._button(tr("Segmentation guide"), lambda: self.show_help("segmentation"), job_sensitive=False))
        layout.addLayout(intro)
        annotations = QtWidgets.QGroupBox(tr("1. YOLO annotations (optional)"))
        annotation_layout = QtWidgets.QVBoxLayout(annotations)
        actions = QtWidgets.QVBoxLayout()
        actions.addWidget(attach_help(self._button(tr("Импортировать папку разметки"), self.import_labels), 'import_yolo'))
        actions.addWidget(attach_help(self._button(tr("Проверить разметку"), self.check_labels), 'check_yolo'))
        annotation_layout.addLayout(actions)
        annotation_layout.addWidget(attach_help(self._button(tr("Open saved annotations"), self.open_labels_folder), 'open_yolo'))
        self.labels_path = self._note(tr("Разметка ещё не подключена"))
        annotation_layout.addWidget(self.labels_path)
        self.labels_report = QtWidgets.QPlainTextEdit()
        self.labels_report.setReadOnly(True)
        self.labels_report.setFixedHeight(90)
        annotation_layout.addWidget(attach_help(self.labels_report, 'check_yolo'))
        settings_layout.addWidget(annotations)
        self.segmentation_review = SegmentationReview()
        saved_split = self.preferences.value('workspaces/segmentation/comparison')
        if isinstance(saved_split, QtCore.QByteArray):
            self.segmentation_review.comparison.restoreState(saved_split)
        workspace.after_reset = lambda: self.segmentation_review.comparison.setSizes([1, 1])
        self.segmentation_review.editor_defaults = self._editor_profile['mask']
        self.labels_view = self.segmentation_review.polygons_view
        self.segmentation_review.merge_requested.connect(self.merge_segmented_objects)
        self.segmentation_review.correct_requested.connect(self.correct_segmented_objects)
        self.segmentation_review.batch_edit_requested.connect(
            lambda *args: self.correct_segmented_objects(*args, keep_separate=True))
        self.segmentation_review.delete_requested.connect(self.delete_segmented_objects)
        self.segmentation_review.undo_requested.connect(self.undo_segment_merge)
        self.segmentation_review.labeling_requested.connect(lambda:self.sidebar.setCurrentRow(4))
        measurement = QtWidgets.QGroupBox(tr("2. Object selection and measurement"))
        form = QtWidgets.QFormLayout(measurement)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
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
        settings_layout.addWidget(measurement)
        results = QtWidgets.QGroupBox(tr("3. Run and review"))
        result_layout = QtWidgets.QVBoxLayout(results)
        result_layout.addWidget(attach_help(self._button(tr("Measure using selected mode"), self.extract_features, True), 'measure_objects'))
        self.detect_objects_button = self._button(tr("Measure with automatic fallback"), self.detect_and_review)
        result_layout.addWidget(attach_help(self.detect_objects_button, 'detect_fallback'))
        result_layout.addWidget(attach_help(self._button(tr("Open object labeling"), lambda: self.sidebar.setCurrentRow(4)), 'open_measurements'))
        pixel_model = self._button(tr('Pixel segmentation…'), self.open_pixel_segmentation)
        result_layout.addWidget(attach_help(pixel_model, 'pixel_segmentation'))
        result_layout.addWidget(help_label('pixel_segmentation'))
        settings_layout.addWidget(results)
        settings_layout.addStretch()
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(settings_panel)
        settings_dock = workspace.add_panel("settings", "Segmentation settings", scroll)
        image_dock = workspace.add_panel("image", "Segmentation preview", self.segmentation_review, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        workspace.resizeDocks([settings_dock, image_dock], [330, 850], QtCore.Qt.Orientation.Horizontal)
        workspace.finish_layout()
        layout.addWidget(workspace, 1)
        return page

    def open_pixel_segmentation(self):
        if self.process is not None:
            return
        dialog = PixelSegmentationDialog(self.project, self.selected_dataset(), self.segmentation_review.record, self)
        accepted = dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted
        request = dialog.request
        dialog.deleteLater()
        if accepted and request:
            action, options = request
            self.start_job(action, **options)

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
        self.results_table.table.itemSelectionChanged.connect(self._update_result_tile_button)
        self.review_tabs.addTab(self.object_gallery, tr("Object gallery"))
        self.review_tabs.addTab(self.results_table, tr("Feature table"))
        self.object_view = ImageViewer(empty_text=tr("Выберите объект в таблице для проверки маски"))
        preview_panel = QtWidgets.QWidget()
        preview_layout = QtWidgets.QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.open_object_tile_button = self._button(tr("Open object's tile"), self.open_result_tile)
        self.open_object_tile_button.setObjectName('openObjectTile')
        self.open_object_tile_button.setToolTip(tr('Open the full tile for the selected object. Native pixels are preferred; the model canvas is a fallback.'))
        self.open_object_tile_button.setProperty('helpKey', 'result_tile')
        self.open_object_tile_button.setEnabled(False)
        preview_layout.addWidget(self.open_object_tile_button)
        preview_layout.addWidget(self.object_view, 1)
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
        preview_dock = workspace.add_panel("preview", "Object preview", preview_panel, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
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
        actions.addWidget(self._button(tr("Train a model"), lambda:self.sidebar.setCurrentRow(5)))
        actions.addWidget(self._button(tr("Open final results"), lambda:self.sidebar.setCurrentRow(6)))
        layout.addLayout(actions)
        return page

    def _change_page(self, row):
        if row >= 0:
            key = _PAGE_WORKSPACE[row]
            for name, workspace in self._workspaces.items():
                workspace.activate() if name == key else workspace.deactivate()
            self.pages.setCurrentIndex(row)
            self.page_title.setText(tr(_PAGE_TITLES[row]))
            self.panels_button.setVisible(key in self._workspaces)
            for widget in self._dataset_heading:
                widget.setVisible(_PAGE_HELP[row] != 'model_evaluation')
            if row == 1:
                self._request_quick_preview()
            if row == 6:
                self.analytics.ensure_plot()
            if row == 2:
                QtCore.QTimer.singleShot(0,self._check_black_tiles_automatically)

    def _apply_theme(self):
        if self._dark:
            bg, surface, text, muted, border, accent, alt = "#122024", "#1c2c31", "#e7f2f1", "#a4b8bc", "#354b51", "#43bda8", "#22343a"
        else:
            bg, surface, text, muted, border, accent, alt = "#f2f7f7", "#ffffff", "#183336", "#587478", "#d3e1e0", "#167d70", "#f0f6f5"
        selection = "#197b6e" if self._dark else accent
        stylesheet = f"""
            QWidget {{ background: {bg}; color: {text}; font-family: '{self._font_family}'; font-size: 13px; }}
            QLabel#brand {{ font-size: 25px; font-weight: 700; color: {accent}; padding-right: 14px; }}
            QLabel#pageTitle {{ font-size: 24px; font-weight: 600; }}
            QLabel#muted {{ color: {muted}; }}
            QLabel#helpBadge {{ color: {accent}; background: {surface}; border: 1px solid {border}; border-radius: 10px; font-weight: 700; }}
            QLabel#sectionTitle {{ font-size: 15px; font-weight: 600; }}
            QPushButton {{ background: {surface}; border: 1px solid {border}; border-radius: 7px; padding: 8px 12px; }}
            QPushButton:hover {{ border-color: {accent}; }}
            QPushButton#imageComparisonMode:checked {{ background: {alt}; border-color: {accent}; }}
            QPushButton:disabled {{ color: {muted}; background: {alt}; }}
            QPushButton[primary=true] {{ background: {selection}; color: white; border-color: {selection}; font-weight: 600; }}
            QPushButton[primary=true]:disabled {{ background: {border}; color: {muted}; border-color: {border}; }}
            QSpinBox[invalidSetting=true], QDoubleSpinBox[invalidSetting=true], QCheckBox[invalidSetting=true] {{ border: 2px solid #c54d42; }}
            QFrame[noticeKind=error] {{ border: 1px solid #c54d42; border-radius: 6px; }}
            QFrame[noticeKind=recovered] {{ border: 1px solid {accent}; border-radius: 6px; }}
            QToolButton {{ background: {surface}; border: 1px solid {border}; border-radius: 5px; padding: 6px 9px; }}
            QWidget#imageActions QToolButton {{ padding: 3px 4px; }}
            QWidget#imageActions QToolButton:hover {{ border-color: {accent}; }}
            QWidget#imageActions QToolButton:checked {{ background: {alt}; border-color: {accent}; }}
            QDockWidget::title {{ background: {alt}; border: 1px solid {border}; padding: 7px 9px; font-weight: 600; }}
            QDockWidget {{ border: 1px solid {border}; }}
            QMainWindow::separator {{ background: {border}; width: 9px; height: 9px; }}
            QMainWindow::separator:hover {{ background: {accent}; }}
            QSplitter::handle {{ background: {border}; }}
            QSplitter::handle:hover {{ background: {accent}; }}
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background: {surface}; border: 1px solid {border}; border-radius: 5px; padding: 6px; selection-background-color: {accent}; }}
            QSpinBox, QDoubleSpinBox {{ padding-right: 30px; }}
            QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 26px; border-left: 1px solid {border}; border-bottom: 1px solid {border}; background: {alt}; }}
            QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 26px; border-left: 1px solid {border}; background: {alt}; }}
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
        """
        self.setStyleSheet(re.sub(r'(\d+)px', lambda match: f'{round(int(match[1]) * self._ui_scale)}px', stylesheet))
        self.sidebar.setMinimumWidth(round(155 * self._ui_scale))
        self.sidebar.setMaximumWidth(round(190 * self._ui_scale))
        for button in self.findChildren(QtWidgets.QPushButton):
            icon = button.property('workflowIcon')
            if icon:
                button.ensurePolished()
                button.setIcon(tool_icon(button, icon))
        self.theme_button.setText(tr("Светлая тема") if self._dark else tr("Тёмная тема"))

    def _update_interface_scale(self):
        choice = str(self.preferences.value('appearance/scale', 'auto'))
        if choice in ('100', '125', '150', '175', '200'):
            scale = int(choice) / 100
        else:
            available = min(self.width() / 1440, self.height() / 880)
            scale = min(1.8, max(1.0, math.floor(available * 10) / 10))
        if scale != self._ui_scale:
            factor = scale / self._ui_scale
            self._ui_scale = scale
            self._apply_theme()
            self._resize_tile_actions(factor)

    def _resize_tile_actions(self, factor):
        if factor != 1:
            top, bottom = self.tile_splitter.sizes()
            if bottom:
                actions = round(bottom * factor)
                self.tile_splitter.setSizes([max(160, top + bottom - actions), actions])

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
        """Rebuild selectors from persisted state while retaining source checks by ID."""
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
        self.preview_source_combo.blockSignals(True)
        self.preview_source_combo.clear()
        for source in self.project.sources:
            self.preview_source_combo.addItem(source['name'], source['id'])
        index = self.preview_source_combo.findData(self._preview_source_id)
        self.preview_source_combo.setCurrentIndex(max(0,index))
        self._set_preview_source(self.preview_source_combo.currentData())
        self.preview_source_combo.blockSignals(False)
        self.preview_source_combo.setEnabled(bool(self.project.sources) and not self._busy)
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
        self._restore_preparation_previews()
        self._dataset_changed()
        self.model_evaluation.refresh(self.project)

    def _load_settings(self, values=None):
        """Populate editors while retaining exact loaded values alongside rendered ones."""
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
                    if key in ('search_window_end', 'straight_shift_left') and value is None:
                        number = -1
                    integral = isinstance(field, QtWidgets.QSpinBox)
                    representable = (-2147483648 <= number <= 2147483647) if integral else (math.isfinite(number) and abs(number) <= 1e12 and (number == 0 or abs(number) >= 1e-12))
                    field.setReadOnly(not representable)
                    field.setProperty('unrepresentableSetting', not representable)
                    if representable:
                        if number < field.minimum():
                            field.setMinimum(number)
                        if number > field.maximum():
                            field.setMaximum(number)
                        if not integral and number > 0:
                            field.setDecimals(max(field.decimals(), min(15, max(0, -math.floor(math.log10(number))) + 3)))
                        field.setValue(number)
                    else:
                        # Keep the imported value in the snapshot and display it
                        # as text when the spin box cannot represent it.
                        field.lineEdit().setText(str(number) if integral else format(number, '.8g'))
                rendered = field.isChecked() if isinstance(field, QtWidgets.QCheckBox) else field.value()
                self._loaded_setting_values[key] = (value, rendered)
        finally:
            self._settings_loading = False
        self._update_filter_controls()
        self._manual_calibration = values.get('pixel_size_um')
        self._update_source_context()
        self._refresh_settings_validation()

    def _update_filter_controls(self, *_):
        busy = self._busy
        for toggle_key, parameter_keys in self._filter_parameter_groups.items():
            enabled = self._settings_fields[toggle_key].isChecked() and not busy
            for key in parameter_keys:
                if key in self._settings_fields:
                    self._settings_fields[key].setEnabled(enabled)

    def collect_settings(self):
        """Snapshot the draft, mapping editor sentinel values back to JSON null."""
        values = dict(self._draft_settings)
        for key, field in self._settings_fields.items():
            value = field.isChecked() if isinstance(field, QtWidgets.QCheckBox) else field.value()
            loaded = self._loaded_setting_values.get(key)
            # Reuse the exact imported value if the displayed value still matches.
            if loaded is not None and value == loaded[1]:
                value = loaded[0]
            if key == "pixel_size_um" and value == 0:
                value = None
            if key in ('search_window_end', 'straight_shift_left') and value == -1:
                value = None
            values[key] = value
        if self._calibration_mode == 'auto':
            values['pixel_size_um'] = None
        return values

    def save_project(self):
        try:
            self._persist_settings()
            self._log(tr("Проект сохранён: ") + str(self.project.path))
        except Exception as exc:
            self._error(exc)

    def open_project_database(self):
        """Inspect saved metadata while the project lock excludes other writers."""
        if self.process is not None or self._busy:
            return
        dialog = DatabaseDialog(self.project, self)
        dialog.exec()
        dialog.deleteLater()

    def new_project(self):
        name, accepted = QtWidgets.QInputDialog.getText(self, tr("Создать проект"), tr("Project folder name"))
        name = name.strip()
        if not accepted or not name:
            return
        if name in ('.', '..') or any(c in name for c in '\\/:*?"<>|') or name.endswith(('.', ' ')):
            self._error(tr("Choose a valid folder name without path separators."))
            return
        parent = QtWidgets.QFileDialog.getExistingDirectory(self, tr("Choose the parent folder for the new project"),
            str(Path(__file__).resolve().parents[2] / 'data' / 'projects'))
        if not parent:
            return
        try:
            folder = Path(parent) / name
            if folder.exists():
                raise FileExistsError(tr('A folder with this name already exists. Choose another project name.'))
            profile = read_profile(self.preferences)
            self._switch_project(self.Project.create(folder / 'project.json', name, settings=profile['processing'],
                                                     calibration_mode=profile['calibration_mode']))
            self._log(tr("Создан проект ") + self.project.name)
        except Exception as exc:
            self._error(exc)

    def open_project(self):
        projects_directory = Path(__file__).resolve().parents[2] / 'data' / 'projects'
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, tr("Открыть проект"), str(projects_directory), tr("Проект SoLoData (*.json)"))
        if path:
            try:
                self._switch_project(self.Project.load(path))
                self._log(tr("Открыт проект ") + self.project.name)
            except Exception as exc:
                self._error(exc)

    def add_sources(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, tr("Добавить TIFF"), "", "TIFF (*.tif *.tiff *.TIF *.TIFF)")
        if paths:
            self.start_job('add_sources', paths=paths)

    def _source_selected(self):
        row = self.source_table.currentRow()
        if 0 <= row < len(self.project.sources):
            source = self.project.sources[row]
            self.source_details.setText(tr('{v0}\nОси: {v1} · Размеры: {v2} · Тип: {v3}', v0=source.get('path', ''), v1=source.get('axes', '—'), v2=_display(source.get('shape')), v3=source.get('dtype', '—')))
            self._set_preview_source(source['id'])
            if hasattr(self, 'preview_source_combo'):
                self.preview_source_combo.blockSignals(True)
                self.preview_source_combo.setCurrentIndex(self.preview_source_combo.findData(source['id']))
                self.preview_source_combo.blockSignals(False)
                self._update_source_context()

    def _preview_source_changed(self, *_):
        self._set_preview_source(self.preview_source_combo.currentData())
        index = next((i for i,s in enumerate(self.project.sources) if s['id'] == self._preview_source_id), -1)
        if index >= 0:
            self.source_table.selectRow(index)
        self._update_source_context()

    def _set_preview_source(self, source_id):
        changed = source_id != self._preview_source_id
        self._preview_source_id = source_id
        if changed:
            self._reset_preparation_previews()
            if not self._refreshing:
                self._restore_preparation_previews()
        if hasattr(self, 'whole_tiff_button'):
            self.whole_tiff_button.setEnabled(source_id is not None)
            self.combine_channels_button.setEnabled(source_id is not None)
            self.preparation_resolution.setEnabled(source_id is not None and self.process is None)

    def _reset_preparation_previews(self):
        self._has_preparation_cache = False
        self._quick_preview_key = None
        self.input_preview.clear(tr('Select a TIFF to view its source channel.'))
        message = tr('Calculate the preview to see filtering and the protective mask.')
        self.filtered_preview.clear(message)
        self.protective_preview.clear(message)

    def _restore_preparation_previews(self):
        source = next((s for s in self.project.sources if s['id'] == self._preview_source_id), None)
        cached = (source or {}).get('last_preview') or {}
        try:
            root = (Path(self.project.workspace) / 'previews').resolve()
            paths = [Path(cached[key]).resolve() for key in ('input_path', 'filtered_path', 'mask_path')]
            complete = (cached.get('source_id', self._preview_source_id) == self._preview_source_id
                        and all(root in path.parents and path.is_file() for path in paths))
        except (OSError, KeyError, TypeError, ValueError, RuntimeError):
            complete = False
        if complete:
            self._show_preparation_previews(cached, reveal=False)
        else:
            if self._has_preparation_cache:
                self._reset_preparation_previews()
            self.preparation_preview_note.setText(tr('Calculate the preview to see filtering and the protective mask.'
                                                     if source else 'Select a TIFF to view its source channel.'))
            self._request_quick_preview()

    def _quick_input_key(self):
        source = next((s for s in self.project.sources if s['id'] == self._preview_source_id), None)
        if source is None or self._has_preparation_cache:
            return None
        settings = self.collect_settings()
        calibration = source.get('calibration', {})
        pixel_um = settings.get('pixel_size_um') if self._calibration_mode == 'manual' else (
            calibration.get('pixel_size_um') if calibration.get('status') == 'valid' else None)
        return source['id'], source['path'], settings['channel'], settings['plane'], pixel_um

    def _request_quick_preview(self):
        if (not hasattr(self, 'preparation_preview_note') or not self.isVisible() or self.sidebar.currentRow() != 1
                or self._quick_preview_task is not None or self._close_requested):
            return
        key = self._quick_input_key()
        if key is None or key == self._quick_preview_key:
            return
        self._quick_preview_key = key
        self.input_preview.clear(tr('Loading preview…'))
        task = ReadTiffViewTask(key[1], key[2], key[3])
        self._quick_preview_task = task
        task.signals.ready.connect(self._show_quick_preview)
        task.signals.failed.connect(self._quick_preview_failed)
        image_pool().start(task)

    def _finish_quick_preview(self):
        self._quick_preview_task = None
        key = self._quick_preview_key
        if self._close_requested or not self.isVisible() or key is None or key != self._quick_input_key():
            self._request_quick_preview()
            return None
        return key

    def _show_quick_preview(self, result):
        key = self._finish_quick_preview()
        if key is not None:
            pixels, (width, height), step = result
            caption = tr('Overview · {width} × {height} source px · channel {channel}, plane {plane}',
                         width=width, height=height, channel=key[2], plane=key[3])
            self.input_preview.set_grayscale_pixels(pixels, caption, ruler_scale=(step, step, key[4]))

    def _quick_preview_failed(self, error):
        if self._finish_quick_preview() is not None:
            self.input_preview.clear(tr('Could not open image: {message}', message=error))

    def _calibration_mode_changed(self, *_):
        if self._settings_loading:
            return
        if self._calibration_mode == 'manual':
            self._manual_calibration = self._settings_fields['pixel_size_um'].value() or None
        self._calibration_mode = self.calibration_mode_combo.currentData()
        field = self._settings_fields['pixel_size_um']
        if self._calibration_mode == 'manual':
            field.setValue(self._manual_calibration or 0)
        self._update_source_context()
        self._settings_changed()

    def _update_source_context(self):
        """Show the selected TIFF's plane and calibration context in Preparation."""
        if not hasattr(self, 'preview_source_combo'):
            return
        source = next((s for s in self.project.sources if s['id'] == self._preview_source_id), None)
        if source and 'calibration' not in source:
            try:
                from src.image_io import inspect_tiff
                info = inspect_tiff(source['path'])
                source.update(calibration=info['calibration'], plane_axis=info['plane_axis'], plane_count=info['plane_count'])
            except (OSError, ValueError):
                pass
        plane = self._settings_fields['plane']
        single = source is not None and source.get('plane_count',1) == 1
        plane.setReadOnly(bool(plane.property('unrepresentableSetting')) or (single and plane.value() == 0))
        self.plane_note.setText(tr('This TIFF has one 2D plane. Slice/frame is not used (0).') if single else
            tr('Slice/frame selects one Z, time or image plane; it does not combine the stack.'))
        field = self._settings_fields['pixel_size_um']
        if self._calibration_mode == 'auto':
            calibration = (source or {}).get('calibration', {})
            value = calibration.get('pixel_size_um') if calibration.get('status') == 'valid' else None
            field.blockSignals(True)
            precision = len(format(value or 0, '.12f').rstrip('0').partition('.')[2])
            field.setDecimals(max(6, precision))
            if value and value > field.maximum():
                field.setMaximum(value)
            field.setValue(value or 0)
            field.setReadOnly(True)
            field.blockSignals(False)
            self.calibration_note.setText(tr('TIFF: {value} µm/px · {origin}', value=format(value,'.12g'), origin=calibration.get('source','')) if value else
                tr('No supported isotropic TIFF calibration. Measurements use source pixels.'))
        else:
            field.setReadOnly(bool(field.property('unrepresentableSetting')))
            self.calibration_note.setText(tr('Manual calibration applies to the processing batch. Set 0 to keep pixel units.'))

    def selected_source_ids(self):
        """Return the checked processing batch independently of the preview selector."""
        return [self.source_table.item(row, 0).data(QtCore.Qt.ItemDataRole.UserRole)
                for row in range(self.source_table.rowCount())
                if self.source_table.item(row, 0).checkState() == QtCore.Qt.CheckState.Checked]

    def preview_source(self):
        row = next((i for i,s in enumerate(self.project.sources) if s['id'] == self._preview_source_id), self.source_table.currentRow())
        if row < 0 and self.project.sources:
            row = 0
        if row < 0 or row >= len(self.project.sources):
            self._error(tr("Добавьте TIFF для предпросмотра."))
            return
        source = self.project.sources[row]
        self._native_preview_request = None
        self.start_job("preview", source_ids=[source["id"]], source_id=source["id"], settings=self.collect_settings())

    def open_source_viewer(self):
        source = next((s for s in self.project.sources if s['id'] == self._preview_source_id), None)
        if source:
            settings = self.collect_settings()
            calibration = source.get('calibration') or {}
            pixel_um = settings.get('pixel_size_um') if self._calibration_mode == 'manual' else (
                calibration.get('pixel_size_um') if calibration.get('status') == 'valid' else None)
            viewer = SourceViewer(self, source['path'], settings['channel'], settings['plane'], pixel_um=pixel_um)
            show_centered_window(viewer)

    def open_channel_composite(self):
        from src.image_io import inspect_tiff
        source = next((item for item in self.project.sources if item['id'] == self._preview_source_id), None)
        if source is None:
            return
        try:
            info = inspect_tiff(source['path'])
        except (OSError, ValueError) as error:
            self._error(error)
            return
        dialog = ChannelCompositeDialog(self, info, self.collect_settings()['plane'])
        show_centered_window(dialog)

    def open_preparation_resolution(self, index=None):
        source = next((item for item in self.project.sources if item['id'] == self._preview_source_id), None)
        if source is None:
            return
        if type(index) is not int:
            index = self.preview_tabs.currentIndex()
        cached = source.get('last_preview') or {}
        settings = self.collect_settings()
        if index not in (1, 2):
            if self._has_preparation_cache:
                settings = cached.get('settings') or settings
            pixel_um = settings.get('pixel_size_um')
            if not self._has_preparation_cache and self._calibration_mode == 'auto':
                calibration = source.get('calibration') or {}
                if calibration.get('status') == 'valid':
                    pixel_um = calibration.get('pixel_size_um')
            viewer = SourceViewer(self, source['path'], settings.get('channel', 0), settings.get('plane', 0),
                                  pixel_um=pixel_um, title=tr('Source channel'))
            show_centered_window(viewer)
        elif not self._open_processed_resolution(source, index):
            if self.start_job('preview', source_id=source['id'], settings=settings, native_resolution=True):
                self._native_preview_request = source['id'], index

    def _open_processed_resolution(self, source, index):
        cached = source.get('last_preview') or {}
        key = 'native_filtered_path' if index == 1 else 'native_mask_path'
        filename = Path(cached.get(key) or '').resolve()
        root = (Path(self.project.workspace) / 'previews').resolve()
        if root not in filename.parents or not filename.is_file():
            return False
        title = tr('Filtering' if index == 1 else 'Protective mask')
        pixel_um = (cached.get('settings') or {}).get('pixel_size_um')
        viewer = SourceViewer(self, filename, 0, 0, pixel_um=pixel_um, title=title, binary=index == 2)
        show_centered_window(viewer)
        return True

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
            if self.sidebar.currentRow() == 2:
                QtCore.QTimer.singleShot(0,self._check_black_tiles_automatically)
        except Exception as exc:
            self._log(tr("Не удалось обновить набор: ") + str(exc))

    def refresh_tiles(self):
        dataset = self.selected_dataset()
        self._manifest = None
        self._tile_records = []
        self._selected_tile = None
        self.edit_selected_tile_button.setEnabled(False)
        for viewer in (self.overview_view, self.model_view, self.native_view,
                       self.ownership_view, self.polygon_view, self.labels_view):
            viewer.clear()
        self.polygon_status.hide()
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
            self._refresh_overview(dataset)
        except Exception as exc:
            self.tile_list.clear()
            self.tile_summary.setText(tr("Набор недоступен или незавершён: ") + str(exc))
            self._log(tr("Проверка набора: ") + str(exc))

    def _refresh_overview(self, dataset, *, reload_image=True, preserve_view=False):
        from src.partition_geometry import png_shape
        from src.tile_edits import active_tile_edits

        images = sorted((Path(dataset['path']) / 'overview').glob('*_TILE_INDEX_MAP_*px.png'),
                        key=lambda path: path.stat().st_mtime)
        if not images:
            self.overview_view.clear(tr("Карта отсутствует. Нажмите «Обновить карту»."))
            return
        image = images[-1]
        marker = image.with_suffix('.edits.json')
        recorded = json.loads(marker.read_text(encoding='utf-8')) if marker.is_file() else {}
        caption = tr("Обзорная карта · нажмите на область для выбора тайла")
        caption += '\n' + tr('EXCLUDED labels mark excluded tiles; Restore returns a selected tile to measurement.')
        # This caption compares saved version identities. Scientific operations
        # still verify file hashes before using a version for measurement.
        if recorded != active_tile_edits(dataset['path']):
            caption += '\n' + tr('Overview predates the active edits. Choose Rebuild overview.')
        inclusion = image.with_suffix('.inclusion.json')
        active = sorted(record['id'] for record in self._tile_records if not record['excluded'])
        recorded_active = json.loads(inclusion.read_text(encoding='utf-8')) if inclusion.is_file() else None
        if recorded_active != active and (recorded_active is not None or len(active) != len(self._tile_records)):
            caption += '\n' + tr('Overview predates tile exclusions. Choose Rebuild overview.')
        if not reload_image and self.overview_view.filename == str(image):
            self.overview_view.set_caption(caption)
        else:
            scale = None
            try:
                source_h, source_w = self._manifest['image_shape'][:2]
                display_h, display_w = png_shape(image)
                scale = (source_w / display_w, source_h / display_h, tile_ruler_scale(dataset, {}, 'native')[2])
            except (OSError, ValueError, ZeroDivisionError):
                # The preview decoder reports an unreadable overview. Tile
                # selection remains available independently of that image.
                pass
            self.overview_view.set_image(image, caption, ruler_scale=scale, preserve_view=preserve_view)

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
                label += (tr(' · excluded automatically (black)') if record.get('exclusion_reason') == 'black'
                          else tr("  · исключён"))
            if bright:
                label += tr("  · яркая область")
            item = QtWidgets.QListWidgetItem(label)
            if excluded and record.get('exclusion_reason') == 'black':
                item.setToolTip(tr('Automatically excluded: all valid native pixels are zero.'))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, record)
            self.tile_list.addItem(item)
            if record["id"] == previous:
                self.tile_list.setCurrentItem(item)

    def _tile_selected(self, item, previous=None, *, preserve_view=False):
        """Open the distinct model, native, ownership and annotation views for a tile."""
        if item is None:
            return
        dataset = self.selected_dataset()
        if dataset is None:
            return
        record = item.data(QtCore.Qt.ItemDataRole.UserRole)
        self._selected_tile = record
        self.edit_selected_tile_button.setEnabled(False)
        base = Path(dataset["path"])
        model = base / record["filename"]
        if record.get("excluded"):
            model = base / "excluded_tiles" / record["filename"]
        if record.get('edit_reference'):
            model = tile_artifact_path(base, record, 'filename')
        native = tile_artifact_path(base, record, 'native_filename') if record.get('native_filename') else model
        mask = tile_artifact_path(base, record, 'valid_mask') if record.get('valid_mask') else None
        transform = record.get("transform", {})
        factor = transform.get("source_pixels_per_output_pixel", 1)
        self.tile_details.setText(tr('Тайл {v0} · {v1} · Native: {v2} px · Исходных px / модельный px: {v3:.4f} · Принадлежащих пикселей: {v4}', v0=record['id'], v1=tr('исключён') if record.get('excluded') else tr('активен'), v2=_display(transform.get('native_crop_shape')), v3=float(factor), v4=record.get('valid_pixels', '—')))
        if record.get('edit_reference'):
            self.tile_details.setText(self.tile_details.text() + '\n' + tr(
                'Active edit: {version}. Recalculate measurements after changing it.', version=Path(record['edit_reference']).name))
        model_editor = self._tile_edit_context(dataset, record, 'model')
        native_editor = self._tile_edit_context(dataset, record, 'native' if record.get('native_filename') else 'model')
        native_space = 'native' if record.get('native_filename') else 'model'
        self.model_view.set_image(model, tile_editor=model_editor, ruler_scale=tile_ruler_scale(dataset, record, 'model'),
                                  preserve_view=preserve_view)
        self.native_view.set_image(native, tr("Native · исходный пространственный масштаб"), tile_editor=native_editor,
                                   ruler_scale=tile_ruler_scale(dataset, record, native_space), preserve_view=preserve_view)
        if mask and mask.is_file():
            caption = tr('Exact ownership · white pixels belong to the selected tile')
            shape = transform.get('native_crop_shape')
            if shape and record.get('valid_pixels') == math.prod(shape[:2]):
                caption += ' · ' + tr('This tile owns its entire native crop.')
            self.ownership_view.set_image(mask, caption, ruler_scale=tile_ruler_scale(dataset, record, native_space),
                                          preserve_view=preserve_view)
        else:
            self.ownership_view.clear(tr('No saved ownership mask for this tile.'))
        if not preserve_view:
            self.segmentation_review.select_tile(record['id'])
        self._show_polygons(model, record, preserve_view=preserve_view)

    def _tile_edit_context(self, dataset, record, space):
        if record.get('valid_mask'):
            return TileEditContext(self.project.workspace, dataset.get('id', ''), dataset['path'], record, space,
                                   expected_revision=record.get('edit_reference'),
                                   editor_defaults=self._editor_profile['tile'])
        return None

    def edit_selected_tile(self):
        if self.process is None and self._selected_tile is not None:
            self.native_view.open_original(start_editor=True)

    def _tile_edit_saved(self, dataset_id, tile_id, directory):
        try:
            dataset = self.project.get_dataset(dataset_id)
        except ValueError:
            return
        if self.process is None:
            dataset['results_current'] = False
            self.project.add_history('tile_edit_saved', dataset_id=dataset_id, tile_id=tile_id, path=str(directory))
            self.model_evaluation.refresh(self.project)
        if self.selected_dataset() and self.selected_dataset()['id'] == dataset_id:
            # A result-window editor remains usable after its old object list clears.
            self._result_tile_dialog = None
            self._refresh_edited_tile(dataset, tile_id)
        self._log(tr('Tile saved for measurement. Recalculate the features.'))

    def _refresh_edited_tile(self, dataset, tile_id):
        """Update the edited revision in place and retire its old measurements."""
        from src.tile_edits import effective_tile_record

        original = next((record for record in (self._manifest or {}).get('tiles', [])
                         if record['id'] == tile_id), None)
        if original is None:
            self.refresh_tiles()
            self._select_tile_id(tile_id)
        else:
            try:
                revised = effective_tile_record(dataset['path'], original)
                for index, previous in enumerate(self._tile_records):
                    if previous['id'] == tile_id:
                        revised.update(excluded=previous['excluded'],
                                       exclusion_reason=previous.get('exclusion_reason'))
                        self._tile_records[index] = revised
                        break
                for index in range(self.tile_list.count()):
                    item = self.tile_list.item(index)
                    if item.data(QtCore.Qt.ItemDataRole.UserRole)['id'] == tile_id:
                        item.setData(QtCore.Qt.ItemDataRole.UserRole, revised)
                        if self.tile_list.currentItem() is item:
                            self._tile_selected(item, preserve_view=True)
                        break
                self._refresh_overview(dataset, reload_image=False)
            except (OSError, ValueError, KeyError) as exc:
                self._log(tr("Проверка набора: ") + str(exc))
                self.refresh_tiles()
        self.refresh_results(quiet=True)
        self._black_scan_attempts.discard(dataset['id'])
        if self.sidebar.currentRow() == 2:
            QtCore.QTimer.singleShot(0, self._check_black_tiles_automatically)

    def use_saved_tile_edit(self):
        dataset, record = self.selected_dataset(), self._selected_tile
        if not dataset or not record:
            return
        workspace = Path(self.project.workspace).resolve()
        roots = [workspace] + [p for p in Path(dataset['path']).resolve().parents if workspace in p.parents]
        folder = Path(dataset['path']) / 'tile_edits' / Path(record['filename']).stem
        for root in roots:
            legacy = root / 'tile_edits' / Path(record['filename']).stem
            if legacy.is_dir():
                folder = legacy
                break
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, tr('Use saved edit…'), str(folder), 'Edit record (edit.json)')
        if path:
            self.start_job('tile_edit', dataset_id=dataset['id'], tile_id=record['id'], metadata_file=path)

    def restore_prepared_tile(self):
        dataset, record = self.selected_dataset(), self._selected_tile
        if dataset and record and record.get('edit_reference'):
            self.start_job('tile_edit', dataset_id=dataset['id'], tile_id=record['id'], restore=True)

    def _show_polygons(self, model, record, *, preserve_view=False):
        dataset = self.selected_dataset()
        self.polygon_view.set_image(model, ruler_scale=tile_ruler_scale(dataset, record, 'model'),
                                    preserve_view=preserve_view)
        show_yolo_polygons(self.polygon_view, self.polygon_status, dataset, record)

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

    def _check_black_tiles_automatically(self):
        dataset = self.selected_dataset()
        if (not self.isVisible() or self.process is not None or self.sidebar.currentRow() != 2 or not dataset
                or dataset['id'] in self._black_scan_attempts):
            return
        base = Path(dataset.get('path','')).resolve()
        if Path(self.project.workspace).resolve() not in base.parents:
            return
        try:
            from src.black_tiles import black_scan_needed
            if black_scan_needed(base):
                self._black_scan_attempts.add(dataset['id'])
                self.start_job('exclude_black',dataset_id=dataset['id'])
        except (OSError,ValueError,KeyError) as error:
            self._log(tr('Ошибка: ')+str(error))

    def check_black_tiles(self):
        dataset = self._require_dataset()
        if dataset:
            self.start_job('exclude_black',dataset_id=dataset['id'])

    def open_detailed_map(self):
        dataset = self._require_dataset()
        if dataset:
            self.start_job('overview', dataset_id=dataset['id'], full_resolution=True)

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

    def refresh_results(self, checked=False, quiet=False, *, preferred_tile=None):
        """Expose measurements and manual labels only while their inputs still match."""
        self._close_result_tile_window()
        self.open_object_tile_button.setEnabled(False)
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
            self._sync_segmentation_and_analysis(preferred_tile)
            return
        if not self.service.results_are_current(dataset):
            self.results_table.clear()
            self.results_summary.setText(tr("Результаты требуют пересчёта: разметка или состав тайлов изменились"))
            self._sync_segmentation_and_analysis(preferred_tile)
            return
        try:
            self.results_table.load_csv(csv_path)
            self.object_gallery.set_rows(self.results_table.rows, dataset)
            self.refresh_manual_labels(current=True)
            if self.object_gallery.visible_rows:
                first = self.object_gallery.visible_rows[0]
                self.object_gallery.select_object(first['Tile_Name'], first['Object_ID'])
            self.results_summary.setText(tr('{v0} объектов · {v1}', v0=len(self.results_table.rows), v1=Path(csv_path).name))
            self.results_summary.setToolTip(csv_path)
            self._sync_segmentation_and_analysis(preferred_tile)
            if not quiet:
                self._log(tr("Результаты обновлены"))
        except Exception as exc:
            self.results_table.clear()
            self.object_gallery.set_rows([], None)
            self._sync_segmentation_and_analysis(preferred_tile)
            self.results_summary.setText(tr("Не удалось открыть CSV: ") + str(exc))
            if not quiet:
                self._error(exc)

    def _sync_segmentation_and_analysis(self, preferred_tile=None):
        dataset = self.selected_dataset()
        current = bool(self.results_table.source_path)
        rows = self.results_table.rows if current else []
        self.segmentation_review.set_context(dataset, self._tile_records, rows, current, preferred_tile=preferred_tile)
        self.analytics.set_data(dataset, self.results_table.headers if current else [], rows, self._manual_report,
                                project_datasets=self.project.datasets)

    def merge_segmented_objects(self, tile_name, identifiers, signature):
        dataset = self._require_dataset()
        if dataset:
            self.start_job('merge_objects',dataset_id=dataset['id'],tile_name=tile_name,
                           object_ids=identifiers,expected_signature=signature)

    def undo_segment_merge(self, signature):
        dataset = self._require_dataset()
        if dataset:
            self.start_job('undo_object_merge',dataset_id=dataset['id'],expected_signature=signature)

    def correct_segmented_objects(self, tile_name, identifiers, signature, operations, *, keep_separate=False):
        dataset = self._require_dataset()
        if dataset:
            self.start_job('correct_objects',dataset_id=dataset['id'],tile_name=tile_name,
                           object_ids=identifiers,expected_signature=signature,operations=operations,
                           keep_separate=keep_separate)

    def delete_segmented_objects(self, tile_name, identifiers, signature):
        dataset = self._require_dataset()
        if dataset:
            self.start_job('delete_objects',dataset_id=dataset['id'],tile_name=tile_name,
                           object_ids=identifiers,expected_signature=signature)

    def export_analysis_filtered(self):
        dataset = self._require_dataset()
        if not dataset or not self.analytics.table.source_path:
            return
        path,_ = QtWidgets.QFileDialog.getSaveFileName(self,tr('Экспорт результатов'),
                    f"{dataset.get('name','fibers')}_visible.csv",'CSV (*.csv)')
        if path:
            try:
                if not self.service.results_are_current(dataset):
                    raise ValueError(tr('No current measurements to export.'))
                self.analytics.table.export_filtered(path)
            except Exception as error:
                self._error(error)

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
        self._update_result_tile_button()
        if not dataset or not dataset.get("results_dir"):
            return
        folder = Path(dataset["results_dir"]) / "verification_masks" / row.get("Tile_Name", "")
        try:
            object_id = int(row.get("Object_ID", 0))
            files = sorted(folder.glob(f"obj_{object_id:03d}_*.png"))
            if files:
                scale = measurement_ruler_scale(dataset["results_dir"], row.get('Measurement_Space'))
                self.object_view.set_image(files[0], tr('Объект {v0} · {v1} · {v2}', v0=object_id, v1=tr(row.get('Class_Name', 'Unknown')), v2=tr(row.get('Measurement_Space', 'source_pixels'))),
                                           ruler_scale=scale)
            else:
                self.object_view.clear(tr("Сохранённая маска объекта отсутствует"))
        except (ValueError, TypeError):
            self.object_view.clear(tr("Некорректный идентификатор объекта"))

    def _update_result_tile_button(self):
        button = getattr(self, 'open_object_tile_button', None)
        if button is not None:
            button.setEnabled(not self._busy and self.process is None and bool(self.selected_dataset())
                              and self.results_table.selected_row() is not None)

    def _close_result_tile_window(self):
        dialog, self._result_tile_dialog = getattr(self, '_result_tile_dialog', None), None
        if dialog is not None:
            try:
                dialog.close()
            except RuntimeError:
                pass

    def open_result_tile(self):
        dataset, row = self.selected_dataset(), self.results_table.selected_row()
        if not dataset or row is None or self.process is not None:
            self._update_result_tile_button()
            return None
        try:
            from .result_tile import find_result_tile_record, resolve_tile_image, ObjectHighlightTask
            record = find_result_tile_record(row, self.service.tile_records(dataset))
            filename, space = resolve_tile_image(dataset, record)
            space_text = tr('Native crop · source-pixel scale') if space == 'native' else tr('Model tile · resized/padded canvas')
            caption = tr('Tile {tile} · Object {object} · {space}',
                         tile=row.get('Tile_Name', ''), object=row.get('Object_ID', ''), space=space_text)
            caption += '\n' + tr('Locating the selected object…')
            self._close_result_tile_window()
            dialog = ImageViewer.open_image_window(filename, parent=self, language=self.language,
                                                  caption=caption, original=True,
                                                  tile_editor=self._tile_edit_context(dataset, record, space),
                                                  ruler_scale=tile_ruler_scale(dataset, record, space))
            self._result_tile_dialog = dialog
            if dialog is not None:
                if hasattr(dialog, 'viewer'):
                    task = ObjectHighlightTask(dict(dataset), dict(row), dict(record), space)
                    dialog._object_highlight_task = task
                    dialog._object_highlight_label = str(row.get('Object_ID', ''))
                    task.signals.ready.connect(lambda result, current=dialog: self._show_result_highlight(current, caption, result))
                    QtCore.QThreadPool.globalInstance().start(task)
                if record.get('valid_mask'):
                    dialog.viewer.tile_saved.connect(self._tile_edit_saved)
                dialog.finished.connect(lambda _result, current=dialog: self._result_tile_closed(current))
            return dialog
        except Exception as exc:
            self._error(exc)
            return None

    def _show_result_highlight(self, dialog, caption, result):
        if self._result_tile_dialog is not dialog:
            return
        viewer = dialog.viewer
        message = ('The exact measured mask is highlighted.' if result and not result['recovered'] else
                   'Located by a unique exact match of the saved crop.' if result else
                   'This older result cannot be located unambiguously. Recalculate to save object positions.')
        text = caption.split('\n')[0] + '\n' + tr(message)
        # The image decode and location task may finish in either order.
        def show(*_):
            viewer.caption.setText(text)
            if result:
                result['label'] = '#' + dialog._object_highlight_label
                viewer.set_object_highlight(result)
        if viewer._loading:
            viewer.loaded.connect(show)
        else:
            show()

    def _result_tile_closed(self, dialog):
        if self._result_tile_dialog is dialog:
            self._result_tile_dialog = None

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
            self._update_result_tile_button()
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

    def refresh_manual_labels(self, *, current=None):
        dataset = self.selected_dataset()
        if not dataset or not self.results_table.source_path:
            self.classifier.set_enabled_current(False)
            return
        try:
            report = self.service.get_object_labels(dataset, current=current)
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
            self.analytics.set_data(dataset, self.results_table.headers, self.results_table.rows, report,
                                    project_datasets=self.project.datasets)
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

    def show_feature_statistics(self):
        dataset = self._require_dataset()
        if not dataset:
            return
        try:
            from .result_statistics import StatisticsDialog
            from .object_labels import RF_PREDICTORS
            fields, rows = self.service.read_results(dataset)
            if not rows or not set(fields).intersection(RF_PREDICTORS):
                raise ValueError(tr('No current objects to plot.'))
            dialog = StatisticsDialog(fields, rows, self, dataset=dataset, labels=self._manual_report,
                                      project_datasets=self.project.datasets)
            try:
                dialog.exec()
            finally:
                dialog.deleteLater()
        except Exception as exc:
            self._error(exc)

    def export_excel(self):
        from .result_exports import export_workbook
        self._export_result_copy(export_workbook, 'Export Excel workbook', 'xlsx', 'measurements')

    def export_ml(self):
        from .result_exports import export_ml_bundle
        self._export_result_copy(export_ml_bundle, 'Export ML bundle', 'zip', 'ml')

    def _export_result_copy(self, exporter, title, extension, suffix):
        dataset = self._require_dataset()
        if not dataset:
            return
        dialog = QtWidgets.QFileDialog(self, tr(title))
        dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptMode.AcceptSave)
        dialog.setNameFilter(f'{extension.upper()} (*.{extension})')
        dialog.setDefaultSuffix(extension)
        dialog.selectFile(f"{dataset.get('name', 'fibers')}_{suffix}.{extension}")
        if not dialog.exec():
            dialog.deleteLater()
            return
        path = dialog.selectedFiles()[0]
        dialog.deleteLater()
        try:
            if Path(path).suffix.lower() != f'.{extension}':
                raise ValueError(tr('Use the .{extension} file extension.', extension=extension))
            count = exporter(dataset, path)
            self._log(tr("Exported {rows} objects to {path}", rows=count, path=path))
        except Exception as exc:
            self._error(exc)

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

    def open_prediction_review(self):
        if self.process is not None:
            return
        page = self.model_evaluation
        selected = (str(page.current_result_path), page.models.currentData()) if page.current_result_path else None
        dialog = PredictionSetupDialog(self.project, self, preferred_model=selected)
        accepted = dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted
        request, review_path = dialog.request, dialog.review_path
        dialog.deleteLater()
        if accepted and review_path:
            self._show_prediction_review(review_path)
        elif accepted and request:
            self.start_job('object_prediction', **request)

    def _show_prediction_review(self, path):
        try:
            dialog = PredictionReviewDialog(self.project, path, self)
        except (OSError, ValueError, KeyError, TypeError) as error:
            self._error(error)
            return
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.open()

    def build_request(self, action, **kwargs):
        return {"project_path": str(self.project.path), "action": action, "language": self.language, **kwargs}

    def start_job(self, action, **kwargs):
        """Save a worker request and suspend conflicting edits while it runs."""
        if self.process is not None:
            self._error(tr("Дождитесь завершения текущей задачи или остановите её."))
            return False
        try:
            # Corrections use the saved measurement's settings, independently
            # of an unfinished draft for a future extraction.
            independent = action in ('add_sources','merge_objects','undo_object_merge','correct_objects','delete_objects','exclude_black')
            self._job_settings_draft = self.collect_settings() if independent else None
            if action not in ('model_evaluation', 'object_prediction', 'train_pixel_segmentation', 'apply_pixel_segmentation'):
                options = self.project.settings if independent else kwargs.get("settings", self.collect_settings())
                self.project.settings = PipelineSettings.from_dict(options).to_dict()
                self.project._extra_fields['calibration_mode'] = self._calibration_mode
                self.project.save()
                self._saved_settings_snapshot = dict(self.project.settings)
            folder = Path(self.project.workspace) / "jobs"
            folder.mkdir(parents=True, exist_ok=True)
            self.request_path = version_file(folder, 'Job_' + action)
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
        self.segmentation_review.set_busy(busy)
        from .tile_editor import TileEditor
        for editor in self.findChildren(TileEditor):
            editor.setEnabled(not busy)
        self.model_evaluation.set_busy(busy)
        for button in self._job_buttons:
            button.setEnabled(not busy)
        self.preparation_resolution.setEnabled(not busy and self._preview_source_id is not None)
        self.combine_channels_button.setEnabled(not busy and self._preview_source_id is not None)
        self.edit_selected_tile_button.setEnabled(not busy and not self.native_view._loading
                                                   and self.native_view._tile_editor is not None)
        self.dataset_combo.setEnabled(not busy and bool(self.project.datasets))
        self.language_combo.setEnabled(not busy)
        self.classifier.setEnabled(not busy)
        self._update_result_tile_button()
        self.classifier.set_enabled_current(not busy and self._manual_report.get("current", False))
        self.classifier.export_button.setEnabled(
            not busy and self._manual_report.get("current", False)
            and self._manual_report.get("assigned", 0) > 0)
        self.source_table.setEnabled(not busy)
        self.preview_source_combo.setEnabled(not busy and bool(self.project.sources))
        self.calibration_mode_combo.setEnabled(not busy)
        for field in self._settings_fields.values():
            field.setEnabled(not busy)
        self._update_filter_controls()
        self.labels_mode.setEnabled(not busy)
        self.restore_defaults_action.setEnabled(not busy)
        self.restore_saved_action.setEnabled(not busy)
        self.database_action.setEnabled(not busy)
        self.settings_feedback_restore.setEnabled(not busy)
        self._refresh_settings_validation()
        self.cancel_button.setEnabled(busy and not self._cancel_requested)

    def _read_stdout(self):
        if self.process is None:
            return
        self._stdout_buffer += bytes(self.process.readAllStandardOutput())
        # QProcess reads arbitrary byte chunks. Frame each JSON line first so
        # a multibyte UTF-8 character can span two reads safely.
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

    def _show_preparation_previews(self, result, *, reveal=True):
        paths = result.get('paths') or result.get('summary') or result
        if not isinstance(paths, dict):
            paths = result
        caption = scale = None
        try:
            height, width = paths['source_shape']
            dh, dw = paths['display_shape']
            if any(type(value) is not int or value <= 0 for value in (height, width, dh, dw)):
                raise ValueError('Invalid saved preview dimensions')
            calibration = paths.get('calibration') or {}
            pixel_um = calibration.get('pixel_size_um')
            if type(pixel_um) not in (int, float) or not math.isfinite(pixel_um) or pixel_um <= 0:
                pixel_um = None
            scale = (width / dw, height / dh, pixel_um)
        except (AttributeError, KeyError, TypeError, ValueError, ZeroDivisionError):
            # The display PNGs remain usable without historical size metadata.
            pass
        else:
            caption = tr('Whole image · {name} · source {width} × {height} px · display {dw} × {dh} px',
                         name=paths.get('source_name', ''), width=width, height=height, dw=dw, dh=dh)
            settings = paths.get('settings') or {}
            if isinstance(settings, dict) and 'channel' in settings and 'plane' in settings:
                caption += ' · ' + tr('Channel {channel}, plane {plane}', channel=settings['channel'], plane=settings['plane'])
        self._has_preparation_cache = True
        self._quick_preview_key = None
        self.preparation_preview_note.setText(tr('Saved preview. Recalculate after changing the channel, plane or filters.'))
        for key, viewer in (('input_path', self.input_preview), ('filtered_path', self.filtered_preview),
                            ('mask_path', self.protective_preview)):
            filename = result.get(key) or paths.get(key)
            if filename and (str(filename) != viewer.filename or viewer._error):
                viewer.set_image(filename, caption, ruler_scale=scale, preserve_view=bool(viewer.filename))
        if reveal:
            self.sidebar.setCurrentRow(1)

    def _refresh_mask_job(self, previous_dataset, summary, succeeded):
        """Apply a published measurement without reloading the unchanged tile views."""
        dataset = self.selected_dataset()
        self._job_settings_draft = None
        if not succeeded and previous_dataset == dataset:
            return
        self.refresh_results(quiet=True, preferred_tile=summary.get('tile_name'))
        self.model_evaluation.refresh(self.project)
        if succeeded:
            selected = summary.get('changed_object_ids', [])
            if 'object_id' in summary:
                selected = [summary['object_id']]
                self._log(tr('Merged object #{id}. Review its type on Object labeling.', id=selected[0]))
            elif self._job_action == 'delete_objects':
                self._log(tr('Deleted masks: {count}. Undo restores the previous version.', count=summary.get('deleted_count', 0)))
            elif selected:
                self._log(tr('Edited masks: {count}. Review the updated types on Object labeling.', count=len(selected)))
            self.segmentation_review.select_ids(selected)
            self.sidebar.setCurrentRow(3)

    def _process_finished(self, exit_code, exit_status):
        """Drain late events and load the worker's persisted project state."""
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
        # A clean exit is insufficient by itself. The worker must also have
        # sent a terminal result confirming completion.
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
        if self._job_action == 'model_evaluation':
            if succeeded:
                self.model_evaluation.show_result(result['summary'])
            else:
                self.model_evaluation.status.setText(tr('Остановлен') if cancelled else detail)
            if self._close_requested:
                self.close()
            return
        if self._job_action == 'object_prediction':
            if self._close_requested:
                self.close()
            elif succeeded:
                self._show_prediction_review(result['summary']['path'])
            return
        if self._job_action in ('train_pixel_segmentation', 'apply_pixel_segmentation'):
            if succeeded:
                summary = result['summary']
                if self._job_action == 'train_pixel_segmentation':
                    self._log(tr('Pixel model saved: {path}', path=summary['path']))
                else:
                    self._log(tr('Pixel class map saved: {path}', path=summary['path']))
                    if not self._close_requested:
                        dataset, record = self.selected_dataset(), self.segmentation_review.record
                        scale = tile_ruler_scale(dataset, record, 'native') if dataset and record else None
                        dialog = ImageViewer.open_image_window(summary['overlay'], self, language=self.language,
                                                               caption=tr('Pixel segmentation overlay'),
                                                               ruler_scale=scale)
                        if dialog is not None and summary.get('overlay_colors_rgb'):
                            dialog.layout().addWidget(overlay_legend(summary['overlay_colors_rgb'], dialog))
            if self._close_requested:
                self.close()
            return
        try:
            previous_dataset = self.selected_dataset()
            self.project = self.Project.load(self.project.path)
            summary = (result or {}).get('summary', {})
            mask_change = self._job_action in ('merge_objects', 'undo_object_merge', 'correct_objects', 'delete_objects')
            edited_tile = succeeded and self._job_action == 'tile_edit' and self._manifest is not None
            scanned_unchanged = (succeeded and self._job_action == 'exclude_black'
                                 and summary.get('count') == 0 and self._manifest is not None)
            if mask_change:
                self._refresh_mask_job(previous_dataset, summary, succeeded)
            elif edited_tile:
                self._refresh_edited_tile(self.selected_dataset(), summary.get('tile_id'))
                self.model_evaluation.refresh(self.project)
                self.sidebar.setCurrentRow(2)
            elif scanned_unchanged:
                # The audit may rebuild the overview even if no tile changed
                # inclusion. Keep the current tile and update only that image.
                self._refresh_overview(self.selected_dataset(), preserve_view=True)
                self._job_settings_draft = None
            else:
                self.refresh_project()
                if self._job_settings_draft is not None:
                    self._load_settings(self._job_settings_draft)
                    self._job_settings_draft = None
            if succeeded and self._job_action == "preview":
                self._show_preparation_previews(result)
                requested, self._native_preview_request = self._native_preview_request, None
                if requested and requested[0] == self._preview_source_id:
                    source = next((item for item in self.project.sources if item['id'] == requested[0]), None)
                    if source:
                        self._open_processed_resolution(source, requested[1])
            elif succeeded and self._job_action in ("prepare", "connect", "overview", 'tile_edit','exclude_black'):
                self.sidebar.setCurrentRow(2)
                if self._job_action == 'tile_edit' and not edited_tile:
                    self._black_scan_attempts.discard(self.selected_dataset()['id'])
                    self._select_tile_id(summary.get('tile_id'))
                if self._job_action == 'exclude_black':
                    self._log(tr('Automatically excluded black tiles: {count}',count=summary.get('count',0)))
                if self._job_action == 'overview' and summary.get('full_resolution') and summary.get('path'):
                    ImageViewer.open_image_window(summary['path'], self, language=self.language,
                        caption=tr('Detailed boundary map · source-pixel resolution'), original=True)
            elif succeeded and self._job_action == 'add_sources':
                self._log(tr('Добавлено исходников: {v0}', v0=result.get('summary', {}).get('added', 0)))
            elif succeeded and self._job_action == "extract":
                self.sidebar.setCurrentRow(3)
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
        self._close_result_tile_window()
        for dialog in self.findChildren(ChannelCompositeDialog):
            dialog.close()
        # Let outstanding thumbnail readers finish before Qt objects disappear.
        image_pool().waitForDone(3000)
        self._project_lock.unlock()
        event.accept()
