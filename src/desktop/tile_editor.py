"""Editing controls for the original-resolution tile viewer."""

from math import floor

import numpy as np

from src.default_settings import EDITOR_DEFAULTS
from .editor_tools import install_tool_shortcuts, tool_label
from .help import attach_help
from .i18n import register_translations, tr
from .image_comparison import ImageComparisonWindow
from .image_controls import DrawingCursor, editor_cursor_preference, size_action, tool_icon
from .image_levels import grayscale_image
from .parameter_inputs import ParameterSpinBox
from .qt import QtCore, QtGui, QtWidgets, Signal, show_centered_window
from .tile_edit import BACKGROUND_RADIUS, ERASE_RADIUS, PAINT_RADIUS, GAMMA_RANGE, TileEdit


_TEXT = {
    'Draw continuation': ('Дорисовать трубочку', 'ציור המשך צינורית'),
    'Compare with original…': ('Сравнить с оригиналом…', 'השוואה למקור…'),
    'Original tile': ('Исходный тайл', 'אריח מקורי'),
    'Edited tile': ('Отредактированный тайл', 'אריח ערוך'),
    'Pick intensity': ('Взять яркость пипеткой', 'דגימת בהירות'),
    'Brush radius (px)': ('Радиус кисти (px)', 'רדיוס מברשת (פיקסלים)'),
    'Intensity': ('Яркость', 'עוצמה'),
    'Click an owned pixel to sample its intensity.': ('Щёлкните по действительному пикселю трубочки, чтобы взять его яркость.', 'לחצו על פיקסל תקף בצינורית כדי לדגום את עוצמתו.'),
    'Draw with the sampled intensity. These manual pixels change the measured shape.': ('Рисуйте выбранной яркостью. Дорисованные пиксели меняют измеряемую форму.', 'ציירו בעוצמה שנדגמה. פיקסלים ידניים אלה משנים את הצורה הנמדדת.'),
    'Choose an owned pixel; padding cannot supply a sample.': ('Выберите действительный пиксель: паддинг нельзя взять за образец.', 'בחרו פיקסל תקף; לא ניתן לדגום ריפוד.'),
    'Edit tile…': ('Редактировать тайл…', 'עריכת אריח…'),
    'Tile editor': ('Редактор тайла', 'עורך אריחים'),
    'Tool': ('Инструмент', 'כלי'),
    'Pan': ('Панорама', 'הזזה'),
    'Straight erase': ('Стереть по прямой', 'מחיקה בקו ישר'),
    'Freehand erase': ('Стереть от руки', 'מחיקה ביד חופשית'),
    'Cut by line': ('Отсечь по линии', 'חיתוך לפי קו'),
    'Local background': ('Удалить фон локально', 'הסרת רקע מקומית'),
    'Brightness (gamma)': ('Яркость (гамма)', 'בהירות (גאמה)'),
    'Gamma': ('Гамма', 'גאמה'),
    'Whole tile': ('Весь тайл', 'כל האריח'),
    'Last background region': ('Последняя область фона', 'אזור הרקע האחרון'),
    'Draw rectangle': ('Выделить прямоугольник', 'בחירת מלבן'),
    'Brightness region': ('Область коррекции яркости', 'אזור תיקון הבהירות'),
    'Smaller side': ('Меньшая сторона', 'הצד הקטן יותר'),
    'Apply': ('Применить', 'החלה'),
    'Cancel preview': ('Сбросить выбор', 'איפוס הבחירה'),
    'Erase radius (px)': ('Радиус стирания (px)', 'רדיוס מחיקה (פיקסלים)'),
    'Background radius (px)': ('Радиус фильтра (px)', 'רדיוס סינון (פיקסלים)'),
    'Undo': ('Отменить', 'ביטול פעולה'),
    'Show original': ('Показать оригинал', 'הצגת המקור'),
    'Save tile': ('Сохранить тайл', 'שמירת האריח'),
    'Tile editor help': ('Справка по редактору тайлов', 'עזרה לעריכת אריחים'),
    'Drag to move the image. Choose an editing tool when ready.': (
        'Перетаскивайте изображение для просмотра. Выберите инструмент, чтобы отредактировать тайл.',
        'גררו כדי להזיז את התמונה. בחרו כלי כדי לערוך את האריח.'),
    'Drag along the pixels to replace with padding.': (
        'Проведите по пикселям, которые нужно заменить паддингом.',
        'גררו לאורך הפיקסלים שברצונכם להחליף בריפוד.'),
    'Draw a line. It will extend to the tile edges.': (
        'Проведите линию. Редактор продлит её до краёв тайла.',
        'ציירו קו. העורך יאריך אותו עד לשולי האריח.'),
    'Click the side to remove. Smaller side counts valid pixels.': (
        'Щёлкните по стороне удаления. «Меньшая сторона» учитывает только действительные пиксели.',
        'לחצו על הצד שתרצו להסיר. ״הצד הקטן יותר״ נספר לפי פיקסלים תקפים.'),
    'Review the shaded side and click Apply. Click the other side to switch.': (
        'Проверьте подсвеченную сторону и нажмите «Применить». Щелчок по другой стороне меняет выбор.',
        'בדקו את הצד המוצלל ולחצו על החלה. לחיצה על הצד השני מחליפה את הבחירה.'),
    'The smaller side is ambiguous. Click the side you want to remove.': (
        'Меньшую сторону нельзя определить однозначно. Щёлкните по стороне, которую хотите удалить.',
        'אי אפשר לקבוע באופן חד־משמעי את הצד הקטן יותר. לחצו על הצד שתרצו להסיר.'),
    'Drag a rectangle to remove the local background.': (
        'Выделите прямоугольник для локального удаления фона.',
        'גררו מלבן להסרת הרקע המקומי.'),
    'Adjust gamma. Values above 1 brighten midtones. Review the preview and click Apply.': (
        'Настройте гамму. Значения выше 1 осветляют средние тона. Проверьте предпросмотр и нажмите «Применить».',
        'כוונו את הגאמה. ערכים מעל 1 מבהירים גוני ביניים. בדקו את התצוגה המקדימה ולחצו על החלה.'),
    'Drag a rectangle for gamma, adjust the value, then review the preview and click Apply.': (
        'Выделите прямоугольник для гаммы, настройте значение, проверьте предпросмотр и нажмите «Применить».',
        'גררו מלבן לגאמה, כוונו את הערך, בדקו את התצוגה המקדימה ולחצו על החלה.'),
    'Gamma applies inside the outlined rectangle. Drag to choose another region.': (
        'Гамма применяется внутри рамки. Чтобы выбрать другую область, выделите новый прямоугольник.',
        'הגאמה חלה בתוך המסגרת. גררו כדי לבחור אזור אחר.'),
    'Gamma is outside the editor range.': (
        'Гамма выходит за диапазон редактора.', 'הגאמה מחוץ לטווח של העורך.'),
    'Edits are kept in memory until you save the tile.': (
        'Правки хранятся в памяти до сохранения тайла.', 'העריכות נשמרות בזיכרון עד לשמירת האריח.'),
    'Original for comparison. Turn off Show original to edit.': (
        'Оригинал для сравнения. Отключите «Показать оригинал», чтобы редактировать.',
        'המקור להשוואה. כבו את ״הצגת המקור״ כדי לערוך.'),
    'Unsaved edits. Save the tile to use them in the prepared dataset.': (
        'Есть несохранённые правки. Сохраните тайл, чтобы использовать их в подготовленном наборе.',
        'יש עריכות שלא נשמרו. שמרו את האריח כדי להשתמש בהן במערך המוכן.'),
    'No owned pixels changed.': ('Принадлежащие тайлу пиксели не изменились.', 'פיקסלי האריח שבבעלות לא השתנו.'),
    'Working on tile…': ('Обработка тайла…', 'האריח בעיבוד…'),
    'Saved tile version: {path}': ('Версия тайла сохранена: {path}', 'גרסת האריח נשמרה: {path}'),
    'Tile editor: {error}': ('Редактор тайлов: {error}', 'עורך אריחים: {error}'),
    'Could not encode the edited PNG.': ('Не удалось записать отредактированный PNG.', 'לא ניתן לקודד את קובץ ה־PNG הערוך.'),
    'Tile editing requires an 8-bit or 16-bit grayscale PNG.': (
        'Редактору требуется 8- или 16-битный PNG в градациях серого.',
        'עריכת אריחים דורשת PNG בגוני אפור בעומק 8 או 16 סיביות.'),
    'The tile ownership mask exceeds the 32 MP editor limit.': (
        'Маска принадлежности тайла превышает предел редактора в 32 Мп.',
        'מסכת הבעלות של האריח חורגת ממגבלת העורך של 32 מגה־פיקסל.'),
    'The tile ownership mask is unreadable.': (
        'Не удалось прочитать маску принадлежности тайла.', 'לא ניתן לקרוא את מסכת הבעלות של האריח.'),
    'The tile ownership mask does not match this canvas.': (
        'Маска принадлежности не соответствует размерам тайла.', 'מסכת הבעלות אינה מתאימה למשטח האריח.'),
}
register_translations({key: values[0] for key, values in _TEXT.items()},
                      hebrew={key: values[1] for key, values in _TEXT.items()})


class _EditTask(QtCore.QRunnable):
    class Signals(QtCore.QObject):
        done = Signal(object)
        failed = Signal(str)

    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.signals = self.Signals()

    def run(self):
        try:
            result = self.operation()
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        else:
            self.signals.done.emit(result)


class TileEditor(QtWidgets.QWidget):
    saved = Signal(object)

    def __init__(self, dialog, viewer, context):
        super().__init__(dialog)
        self.viewer, self.context = viewer, context
        defaults = getattr(context, 'editor_defaults', None) or EDITOR_DEFAULTS
        self.edit = None
        self._task = self._on_done = None
        self._points = []
        self._guides = []
        self._cut_line = None
        self._cut_side = None
        self._gamma_preview = None
        self._gamma_preview_key = None
        self._gamma_rectangle = None
        self._paint_sample = None
        self._original = None
        self._comparison = None
        self._saved_operations = None
        self._saved_directory = None
        self._available = False
        self._closing = False
        self._view = viewer.view
        self._action_buttons = []
        self.setLayoutDirection(QtCore.Qt.LayoutDirection.RightToLeft if viewer.language == 'he'
                                else QtCore.Qt.LayoutDirection.LeftToRight)
        self.setLocale(QtCore.QLocale({'en': 'en_US', 'ru': 'ru_RU', 'he': 'he_IL'}.get(viewer.language, 'en_US')))

        self.start = self._button('Edit tile…', self._load)
        self.start.setEnabled(False)
        self.start.setProperty('primary', True)
        self.start.setIcon(tool_icon(self.start, 'edit'))
        self.help = self._button('?', self._show_help)
        self.help.setFixedWidth(34)
        self.help.setAccessibleName(self._text('Tile editor help'))
        self.mode = attach_help(QtWidgets.QComboBox(), 'tile_editor')
        for label, name in (('Pan', 'pan'), ('Straight erase', 'line'),
                            ('Eraser', 'freehand'), ('Cut by line', 'cut'),
                            ('Local background', 'background'), ('Brightness (gamma)', 'gamma'),
                            ('Brush', 'paint')):
            self.mode.addItem(tool_label(self._text(label), 'erase' if name == 'freehand' else name), name)
        self.mode.setAccessibleName(self._text('Tool'))
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.erase_radius = self._radius_field('Erase radius (px)', (*ERASE_RADIUS[:2], defaults['erase_radius']))
        self.background_radius = self._radius_field('Background radius (px)',
                                                    (*BACKGROUND_RADIUS[:2], defaults['background_radius']))
        self.erase_row = self._labelled('Erase radius (px)', self.erase_radius)
        self.background_row = self._labelled('Background radius (px)', self.background_radius)
        self.paint_radius = self._radius_field('Brush radius (px)', (*PAINT_RADIUS[:2], defaults['paint_radius']))
        self.paint_intensity = self._radius_field('Intensity', (0, 65535, 0))
        self.paint_intensity.valueChanged.connect(self._paint_value_changed)
        self.pick_button = self._button('Pick intensity', self._pick_changed)
        attach_help(self.pick_button, 'tile_editor')
        self.pick_button.setCheckable(True)
        self.paint_row = QtWidgets.QWidget()
        paint_layout = QtWidgets.QHBoxLayout(self.paint_row)
        paint_layout.setContentsMargins(0, 0, 0, 0)
        paint_layout.addWidget(self.pick_button)
        paint_layout.addStretch()
        paint_layout.addWidget(self._labelled('Brush radius (px)', self.paint_radius))
        paint_layout.addWidget(self._labelled('Intensity', self.paint_intensity))
        self.undo_button = self._button('Undo', self._undo)
        self.original = attach_help(QtWidgets.QCheckBox(self._text('Show original')), 'tile_editor')
        self.original.toggled.connect(self._compare)
        self.save_button = self._button('Save tile', self._save)
        self.save_button.setProperty('primary', True)
        self.save_button.setIcon(tool_icon(self.save_button, 'save'))
        self.apply_button = self._button('Apply', self._apply_pending)
        self.apply_button.setProperty('primary', True)
        self.apply_button.setIcon(tool_icon(self.apply_button, 'apply'))
        self.cancel_button = self._button('Cancel preview', self._cancel_pending)
        self.smaller_button = self._button('Smaller side', self._select_smaller_side)
        self.gamma_scope = attach_help(QtWidgets.QComboBox(), 'tile_editor')
        self.gamma_scope.setAccessibleName(self._text('Brightness region'))
        self.gamma_scope.currentIndexChanged.connect(self._gamma_changed)
        self.gamma_slider = attach_help(QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal), 'tile_editor')
        lower, upper, _ = GAMMA_RANGE
        self._initial_gamma = round(100 * defaults['gamma'])
        self.gamma_slider.setRange(round(100 * lower), round(100 * upper))
        self.gamma_slider.setValue(self._initial_gamma)
        self.gamma_slider.setSingleStep(5)
        self.gamma_slider.setPageStep(25)
        self.gamma_slider.setTracking(False)
        self.gamma_slider.setMinimumWidth(90)
        self.gamma_slider.setAccessibleName(self._text('Gamma'))
        self.gamma_slider.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        self.gamma_value = QtWidgets.QLabel()
        self.gamma_value.setMinimumWidth(35)
        self.gamma_value.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.gamma_value.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        self.gamma_row = self._labelled('Gamma', self.gamma_slider)
        self.gamma_row.layout().addWidget(self.gamma_value)
        self.gamma_slider.sliderMoved.connect(self._show_gamma_value)
        self.gamma_slider.valueChanged.connect(self._gamma_changed)
        self._gamma_timer = QtCore.QTimer(self, singleShot=True, interval=120)
        self._gamma_timer.timeout.connect(self._preview_gamma)
        self.hint = QtWidgets.QLabel()
        self.hint.setWordWrap(True)
        self.hint.setObjectName('muted')
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.status.setObjectName('muted')
        self.status.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)

        card = QtWidgets.QFrame(self)
        card.setObjectName('tileEditorCard')
        card.setStyleSheet('QFrame#tileEditorCard { border: 1px solid palette(mid); border-radius: 7px; }')
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(10, 7, 10, 7)
        card_layout.setSpacing(6)
        self.title = QtWidgets.QLabel(self._text('Tile editor'))
        self.title.setObjectName('sectionTitle')
        header = QtWidgets.QHBoxLayout()
        for control in (self.start, self.title, self.help):
            header.addWidget(control)
        header.addStretch()
        for control in (self.undo_button, self.original, self.save_button):
            header.addWidget(control)
        card_layout.addLayout(header)

        self._controls = QtWidgets.QWidget(card)
        tools = QtWidgets.QVBoxLayout(self._controls)
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(5)
        tool_row = QtWidgets.QHBoxLayout()
        tool_row.addWidget(self._labelled('Tool', self.mode))
        tool_row.addStretch()
        for control in (self.erase_row, self.background_row, self.gamma_row):
            tool_row.addWidget(control, 1 if control is self.gamma_row else 0)
        tools.addLayout(tool_row)
        self.cursor_choice = attach_help(DrawingCursor(viewer.language), 'editor_cursor')
        self.cursor_choice.set_preference(editor_cursor_preference(dialog))
        self.cursor_choice.currentIndexChanged.connect(self._sync)
        cursor_row = QtWidgets.QHBoxLayout()
        cursor_row.addWidget(self._labelled('Drawing cursor', self.cursor_choice))
        cursor_row.addStretch()
        self.compare_button = self._button('Compare with original…', self._open_comparison)
        attach_help(self.compare_button, 'image_comparison')
        cursor_row.addWidget(self.compare_button)
        tools.addLayout(cursor_row)
        tools.addWidget(self.paint_row)
        self.action_row = QtWidgets.QWidget(self._controls)
        actions = QtWidgets.QHBoxLayout(self.action_row)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addWidget(self.smaller_button)
        actions.addWidget(self.gamma_scope)
        actions.addStretch()
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.apply_button)
        tools.addWidget(self.action_row)
        tools.addWidget(self.hint)
        card_layout.addWidget(self._controls)
        card_layout.addWidget(self.status)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(card)
        self._controls.hide()
        for control in (self.title, self.undo_button, self.original, self.save_button):
            control.hide()
        self.status.hide()
        self._view.viewport().installEventFilter(self)
        viewer.loaded.connect(self._ready)
        dialog.finished.connect(self._close)
        self._undo_shortcut = QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Undo, self)
        self._undo_shortcut.activated.connect(self._undo)
        self._cancel_shortcut = QtGui.QShortcut(QtGui.QKeySequence('Escape'), self)
        self._cancel_shortcut.setEnabled(False)
        self._cancel_shortcut.activated.connect(self._cancel_pending)
        self.viewer.ruler_button.toggled.connect(self._sync)
        self._tool_shortcuts = install_tool_shortcuts(dialog, self.mode, self.viewer, erase='freehand')

    def _text(self, value, **kwargs):
        return tr(value, language=self.viewer.language, **kwargs)

    def _button(self, label, action):
        button = attach_help(QtWidgets.QPushButton(self._text(label)), 'tile_editor')
        button.clicked.connect(action)
        button.setAutoDefault(False)
        icon = {'Edit tile…': 'edit', 'Undo': 'undo', 'Save tile': 'save', 'Apply': 'apply',
                'Cancel preview': 'close', 'Pick intensity': 'pick', 'Smaller side': 'fit',
                'Compare with original…': 'compare'}.get(label)
        if icon:
            button.setIcon(tool_icon(button, icon))
            self._action_buttons.append(button)
        return button

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for button in self._action_buttons:
            size_action(button, self.width())

    def _radius_field(self, label, limits):
        lower, upper, initial = limits
        field = attach_help(ParameterSpinBox(), 'tile_editor')
        field.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.PlusMinus)
        field.setRange(lower, upper)
        field.setValue(initial)
        field.setAccessibleName(self._text(label))
        field.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        return field

    def _labelled(self, label, field):
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QtWidgets.QLabel(self._text(label))
        label.setBuddy(field)
        layout.addWidget(label)
        layout.addWidget(field)
        return row

    def _show_help(self):
        window = self.parentWidget()
        while window is not None:
            if hasattr(window, 'show_help'):
                window.show_help('tile_editor')
                return
            window = window.parentWidget()

    def _ready(self, *_):
        self._available = True
        self.start.setEnabled(True)

    def _close(self, *_):
        self._closing = True
        if self._comparison is not None:
            self._comparison.close()
        self._gamma_timer.stop()

    def _run(self, operation, done):
        # The controls disable further edits while the single working copy is
        # in use by a worker. GUI updates return through the task signals.
        self._task, self._on_done = _EditTask(operation), done
        self._task.signals.done.connect(self._done)
        self._task.signals.failed.connect(self._failed)
        self._status('Working on tile…')
        self._sync()
        QtCore.QThreadPool.globalInstance().start(self._task)

    def _done(self, value):
        done, self._task, self._on_done = self._on_done, None, None
        if self._closing:
            return
        done(value)
        self._sync()

    def _failed(self, error):
        self._task = self._on_done = None
        if self._closing:
            return
        if self.edit is not None:
            self._gamma_preview = self._gamma_preview_key = None
            self._render()
        self._status('Tile editor: {error}', error=error)
        self._sync()

    def _status(self, message, **kwargs):
        self.status.setText(self._text(message, **kwargs))
        self.status.show()

    def _load(self):
        filename, context = self.viewer.filename, self.context
        self._run(lambda: TileEdit(filename, context), self._loaded)

    def _loaded(self, edit):
        self.edit = edit
        self.paint_intensity.setMaximum(int(np.iinfo(edit.pixels.dtype).max))
        self._original = self.viewer._base_image
        self.start.hide()
        for control in (self.title, self.undo_button, self.original, self.save_button):
            control.show()
        self._controls.show()
        self._mode_changed()

    def _sync(self):
        """Reconcile control state after a task, gesture, comparison or preview."""
        busy = self._task is not None
        mode = self.mode.currentData()
        gamma_pending = self._gamma_pending()
        pending = self._cut_line is not None or gamma_pending or (
            mode == 'gamma' and self._gamma_manual() and self._gamma_rectangle is not None)
        self.start.setEnabled(self._available and not busy)
        has_edits = bool(self.edit and self.edit.operations)
        comparing = self.original.isChecked()
        self._controls.setEnabled(not busy and not comparing)
        self.original.setEnabled(not busy and (has_edits or pending))
        self.compare_button.setEnabled(not busy and has_edits)
        self.undo_button.setEnabled(not busy and not pending and not comparing and has_edits and self.edit.can_undo)
        self.save_button.setEnabled(not busy and not pending and not comparing and has_edits
                                    and self.edit.operations != self._saved_operations)
        self.smaller_button.setVisible(mode == 'cut')
        self.smaller_button.setEnabled(self._cut_line is not None)
        self.gamma_scope.setVisible(mode == 'gamma')
        self.gamma_scope.setEnabled(self.gamma_scope.count() > 1)
        self.cancel_button.setEnabled(pending)
        gamma_ready = gamma_pending and self._gamma_scope_ready() and self._gamma_preview_key == self._gamma_request()
        self.apply_button.setEnabled(self._cut_side is not None or gamma_ready)
        self._cancel_shortcut.setEnabled(pending or bool(self._points))
        if self.viewer.measurement_active:
            return
        draw = self.edit is not None and not busy and not comparing and (
            mode in ('line', 'freehand', 'cut', 'background', 'paint') or mode == 'gamma' and self._gamma_manual())
        drag_mode = QtWidgets.QGraphicsView.DragMode
        self._view.setDragMode(drag_mode.NoDrag if draw else drag_mode.ScrollHandDrag)
        if draw:
            self._view.viewport().setCursor(self.cursor_choice.drawing_cursor())
        else:
            self._view.viewport().setCursor(QtCore.Qt.CursorShape.OpenHandCursor)

    def _update_hint(self):
        mode = self.mode.currentData()
        message = {
            'pan': 'Drag to move the image. Choose an editing tool when ready.',
            'line': 'Drag along the pixels to replace with padding.',
            'freehand': 'Drag along the pixels to replace with padding.',
            'background': 'Drag a rectangle to remove the local background.',
            'gamma': 'Adjust gamma. Values above 1 brighten midtones. Review the preview and click Apply.',
            'cut': 'Draw a line. It will extend to the tile edges.',
            'paint': ('Click an owned pixel to sample its intensity.' if self.pick_button.isChecked() or self._paint_sample is None
                      else 'Draw with the sampled intensity. These manual pixels change the measured shape.'),
        }[mode]
        if mode == 'cut' and self._cut_line is not None:
            message = ('Click the side to remove. Smaller side counts valid pixels.' if self._cut_side is None
                       else 'Review the shaded side and click Apply. Click the other side to switch.')
        elif mode == 'gamma' and self._gamma_manual():
            message = ('Drag a rectangle for gamma, adjust the value, then review the preview and click Apply.'
                       if self._gamma_rectangle is None
                       else 'Gamma applies inside the outlined rectangle. Drag to choose another region.')
        self.hint.setText(self._text(message))

    def _edit_status(self):
        if self.edit.operations == self._saved_operations:
            self._status('Saved tile version: {path}', path=self._saved_directory)
        elif self.edit.operations:
            self._status('Unsaved edits. Save the tile to use them in the prepared dataset.')
        else:
            self._status('Edits are kept in memory until you save the tile.')

    def _mode_changed(self, *_):
        self.viewer.ruler_button.setChecked(False)
        self.viewer.polygon.set_active(False)
        mode = self.mode.currentData()
        self.erase_row.setVisible(mode in ('line', 'freehand'))
        self.background_row.setVisible(mode == 'background')
        self.gamma_row.setVisible(mode == 'gamma')
        self.paint_row.setVisible(mode == 'paint')
        self.pick_button.setChecked(mode == 'paint' and self._paint_sample is None)
        self.action_row.setVisible(mode in ('cut', 'gamma'))
        self._clear_pending()
        if mode == 'gamma':
            with QtCore.QSignalBlocker(self.gamma_scope):
                self.gamma_scope.clear()
                self.gamma_scope.addItem(self._text('Whole tile'), None)
                box = next((op['bounds_ltrb'] for op in reversed(self.edit.operations)
                            if op['tool'] == 'background'), None)
                if box is not None:
                    self.gamma_scope.addItem(self._text('Last background region'), box)
                    self.gamma_scope.setCurrentIndex(1)
                self.gamma_scope.addItem(self._text('Draw rectangle'), 'rectangle')
            self.gamma_slider.setValue(self._initial_gamma)
        self._render()
        self._update_hint()
        self._edit_status()
        self._sync()

    def _pick_changed(self):
        self._cancel_gesture()
        self._update_hint()
        self._sync()

    def _paint_value_changed(self):
        self._paint_sample = []
        self.pick_button.setChecked(False)
        if self.edit is not None:
            self._update_hint()
            self._sync()

    def _compare(self, checked):
        self._cancel_gesture()
        self._render()
        if not checked and self._cut_line is not None:
            self._paint_cut(self._cut_line)
        elif not checked:
            self._paint_gamma_region()
        if checked:
            self._status('Original for comparison. Turn off Show original to edit.')
        else:
            self._edit_status()
        self._sync()

    def _open_comparison(self):
        from .widgets import ImageViewer

        if self._comparison is not None:
            self._comparison.raise_()
            self._comparison.activateWindow()
            return
        titles = self._text('Original tile'), self._text('Edited tile')
        views = (ImageViewer(maximum=None), ImageViewer(maximum=None))
        for view, frame, title in zip(views, (self._original, grayscale_image(self.edit.pixels)), titles):
            view.retranslate(self.viewer.language)
            view.view.setBackgroundBrush(self._view.backgroundBrush())
            view.set_image_frame(frame, title, ruler_scale=self.viewer.ruler.scale)
            view.set_display_levels(self.viewer._levels)
        dialog = self._comparison = ImageComparisonWindow(views, titles, self.window())
        dialog.finished.connect(lambda *_: setattr(self, '_comparison', None))
        show_centered_window(dialog)

    def _undo(self):
        if self.undo_button.isEnabled():
            self._cancel_gesture()
            self.edit.undo()
            self._mode_changed()

    def _render(self):
        if self.original.isChecked():
            image = self._original
        elif self._gamma_preview is not None:
            image = self._gamma_preview
        elif self.edit.operations:
            image = grayscale_image(self.edit.pixels)
        else:
            image = self._original
        self.viewer.replace_display_pixels(image)

    def _save(self):
        if self.save_button.isEnabled():
            self._run(self.edit.save, self._saved)

    def _saved(self, directory):
        self._saved_operations = list(self.edit.operations)
        self._saved_directory = directory
        native = directory / 'native.png'
        self.viewer.set_export_source(native if native.is_file() else directory / 'tile.png')
        self._edit_status()
        self.saved.emit(directory)

    def _applied(self, changed):
        self._render()
        if changed:
            self._edit_status()
        else:
            self._status('No owned pixels changed.')

    def _cancel_gesture(self):
        self._points = []
        self._clear_guides()

    def _clear_guides(self):
        for guide in self._guides:
            self.viewer.scene.removeItem(guide)
        self._guides.clear()

    def _add_guide(self, guide, level=2):
        guide.setZValue(level)
        self._guides.append(guide)

    def _clear_pending(self):
        self._cancel_gesture()
        self._cut_line = self._cut_side = None
        self._gamma_timer.stop()
        self._gamma_preview = self._gamma_preview_key = None
        self._gamma_rectangle = None
        neutral = round(100 * GAMMA_RANGE[2])
        with QtCore.QSignalBlocker(self.gamma_slider):
            self.gamma_slider.setValue(neutral)
        self._show_gamma_value(neutral)

    def _cancel_pending(self):
        self._clear_pending()
        if not self.edit.operations:
            with QtCore.QSignalBlocker(self.original):
                self.original.setChecked(False)
        self._render()
        self._update_hint()
        self._edit_status()
        self._sync()

    def _gamma_pending(self):
        return self.mode.currentData() == 'gamma' and self.gamma_slider.value() != round(100 * GAMMA_RANGE[2])

    def _gamma_manual(self):
        return self.gamma_scope.currentData() == 'rectangle'

    def _gamma_request(self):
        box = self.gamma_scope.currentData()
        if box == 'rectangle':
            box = self._gamma_rectangle
        return self.gamma_slider.value() / 100, tuple(box) if box is not None else None

    def _gamma_scope_ready(self):
        return not self._gamma_manual() or self._gamma_rectangle is not None

    def _show_gamma_value(self, value):
        self.gamma_value.setText(self.locale().toString(value / 100, 'f', 2))

    def _gamma_changed(self, *_):
        self._show_gamma_value(self.gamma_slider.value())
        self._gamma_timer.stop()
        self._gamma_preview_key = None
        self._gamma_preview = None
        self._clear_guides()
        self._render()
        if self._gamma_pending() and self._gamma_scope_ready():
            self._gamma_timer.start()
        else:
            self._edit_status()
        if not self.original.isChecked():
            self._paint_gamma_region()
        self._update_hint()
        self._sync()

    def _preview_gamma(self):
        if not self._gamma_pending() or not self._gamma_scope_ready() or self._task is not None:
            return
        request = self._gamma_request()
        edit = self.edit
        self._run(lambda: grayscale_image(edit.gamma_preview(*request)),
                  lambda image: self._show_gamma_preview(request, image))

    def _show_gamma_preview(self, request, image):
        # A preview belongs to one gamma and one region. Only that result can
        # enable Apply for the current request.
        if self._gamma_pending() and self._gamma_scope_ready() and self._gamma_request() == request:
            self._gamma_preview_key = request
            self._gamma_preview = image
            self._render()
            if not self.original.isChecked():
                self._paint_gamma_region()
        self._edit_status()

    def _paint_gamma_region(self):
        self._clear_guides()
        if self.mode.currentData() == 'gamma' and self._gamma_scope_ready():
            box = self._gamma_request()[1]
        else:
            box = None
        if box is not None:
            left, top, right, bottom = box
            pen = QtGui.QPen(QtGui.QColor('#49c7b7'), 2, QtCore.Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self._add_guide(self.viewer.scene.addRect(left, top, right - left, bottom - top, pen))

    def _select_smaller_side(self):
        line = self._cut_line
        if line is None or self._task is not None:
            return
        edit = self.edit
        self._run(lambda: edit.smaller_cut_side(*line), lambda side: self._show_smaller_side(line, side))

    def _show_smaller_side(self, line, side):
        if self._cut_line != line:
            return
        self._cut_side = side
        self._paint_cut(line)
        self._update_hint()
        self._edit_status()
        if side is None:
            self.hint.setText(self._text('The smaller side is ambiguous. Click the side you want to remove.'))

    def _apply_pending(self):
        if not self.apply_button.isEnabled():
            return
        edit = self.edit
        if self._cut_side is not None:
            first, last = self._cut_line
            side = self._cut_side
            operation = lambda: edit.cut_side(first, last, side)
        else:
            request = self._gamma_request()
            operation = lambda: edit.apply_gamma(*request)
        self._clear_pending()
        self._update_hint()
        self._run(operation, self._applied)

    def _point(self, event):
        """Translate a viewport event into tile pixels at the current zoom."""
        point = self._view.mapToScene(event.position().toPoint())
        return floor(point.x()), floor(point.y())

    def _append_point(self, point, mode):
        height, width = self.edit.pixels.shape
        x, y = point
        point = (min(width - 1, max(0, x)), min(height - 1, max(0, y)))
        if self._points[-1] != point:
            if mode in ('freehand', 'paint') or len(self._points) == 1:
                self._points.append(point)
            else:
                self._points[-1] = point

    def _box(self):
        # The user's two endpoints are included. The saved right and bottom
        # edges are exclusive so the bounds can be passed directly to a slice.
        x0, y0 = self._points[0]
        x1, y1 = self._points[-1]
        return min(x0, x1), min(y0, y1), max(x0, x1) + 1, max(y0, y1) + 1

    @staticmethod
    def _cut_distance(line, point):
        (x0, y0), (x1, y1) = line
        x, y = point
        return (x1 - x0) * (y - y0) - (y1 - y0) * (x - x0)

    def _paint_cut(self, line):
        self._clear_guides()
        height, width = self.edit.pixels.shape
        corners = [(0, 0), (width, 0), (width, height), (0, height)]
        side = self._cut_side or 1
        # The line passes through pixel centers; the scene origin is a pixel corner.
        distances = [side * self._cut_distance(line, (x - .5, y - .5)) for x, y in corners]
        endpoints, polygon = [], []
        for i, (x, y) in enumerate(corners):
            j = (i + 1) % len(corners)
            start, end = distances[i], distances[j]
            point = QtCore.QPointF(x, y)
            if start >= 0:
                polygon.append(point)
            if start == 0:
                endpoints.append(point)
            elif start * end < 0:
                fraction = start / (start - end)
                next_x, next_y = corners[j]
                crossing = QtCore.QPointF(x + fraction * (next_x - x), y + fraction * (next_y - y))
                polygon.append(crossing)
                endpoints.append(crossing)
        if self._cut_side is not None:
            tint = QtGui.QBrush(QtGui.QColor(237, 85, 70, 85))
            shade = self.viewer.scene.addPolygon(QtGui.QPolygonF(polygon),
                QtGui.QPen(QtCore.Qt.PenStyle.NoPen), tint)
            self._add_guide(shade)
        if len(endpoints) == 2:
            pen = QtGui.QPen(QtGui.QColor('#f7b83e'), 2)
            pen.setCosmetic(True)
            boundary = self.viewer.scene.addLine(QtCore.QLineF(*endpoints), pen)
            self._add_guide(boundary, 3)

    def _paint_guide(self, mode):
        if mode == 'cut':
            if len(self._points) == 2:
                self._paint_cut(tuple(self._points))
            return
        self._clear_guides()
        color = QtGui.QColor('#f7b83e')
        if mode in ('background', 'gamma'):
            left, top, right, bottom = self._box()
            pen = QtGui.QPen(color, 2, QtCore.Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            color.setAlpha(55)
            guide = self.viewer.scene.addRect(left, top, right - left, bottom - top, pen, QtGui.QBrush(color))
        else:
            color.setAlpha(200)
            if mode == 'paint':
                ceiling = np.iinfo(self.edit.pixels.dtype).max
                value = round(255 * self.paint_intensity.value() / ceiling)
                color = QtGui.QColor(value, value, value, 220)
            radius = self.paint_radius.value() if mode == 'paint' else self.erase_radius.value()
            pen = QtGui.QPen(color, 2 * radius + 1)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
            x, y = self._points[0]
            if len(self._points) == 1:
                diameter = pen.width()
                guide = self.viewer.scene.addEllipse(x + .5 - diameter / 2, y + .5 - diameter / 2,
                    diameter, diameter, QtGui.QPen(QtCore.Qt.PenStyle.NoPen), QtGui.QBrush(color))
            else:
                path = QtGui.QPainterPath(QtCore.QPointF(x + .5, y + .5))
                for x, y in self._points[1:]:
                    path.lineTo(x + .5, y + .5)
                guide = self.viewer.scene.addPath(path, pen)
        self._add_guide(guide)

    def _finish(self, mode):
        if mode == 'gamma':
            box = self._box()
            self._cancel_gesture()
            self._gamma_rectangle = box
            self._gamma_changed()
            return
        if mode == 'cut':
            points = tuple(self._points)
            self._cancel_gesture()
            if len(points) == 2:
                self._cut_line = points
                self._paint_cut(points)
            self._update_hint()
            self._sync()
            return
        edit = self.edit
        if mode == 'background':
            box, radius = self._box(), self.background_radius.value()
            operation = lambda: edit.remove_background(box, radius)
        elif mode == 'paint':
            points, radius = self._points, self.paint_radius.value()
            intensity, sampled_at = self.paint_intensity.value(), self._paint_sample
            operation = lambda: edit.paint(points, radius, intensity, sampled_at)
        else:
            points, radius = self._points, self.erase_radius.value()
            operation = lambda: edit.erase(points, radius, mode)
        self._cancel_gesture()
        self._run(operation, self._applied)

    def eventFilter(self, watched, event):
        if self.viewer.measurement_active:
            return False
        if self._closing or self.edit is None or self._task is not None or self.original.isChecked():
            return False
        mode = self.mode.currentData()
        if mode == 'pan' or mode == 'gamma' and not self._gamma_manual():
            return False
        kind = QtCore.QEvent.Type
        left_button = QtCore.Qt.MouseButton.LeftButton
        if self._points and event.type() in (kind.Hide, kind.UngrabMouse):
            self._cancel_gesture()
            self._sync()
        if event.type() in (kind.MouseButtonPress, kind.MouseButtonDblClick) and event.button() == left_button:
            x, y = self._point(event)
            height, width = self.edit.pixels.shape
            if 0 <= x < width and 0 <= y < height:
                if mode == 'paint' and (self.pick_button.isChecked() or self._paint_sample is None):
                    if self.edit.valid[y, x]:
                        with QtCore.QSignalBlocker(self.paint_intensity):
                            self.paint_intensity.setValue(int(self.edit.pixels[y, x]))
                        self._paint_sample = [x, y]
                        self.pick_button.setChecked(False)
                        self._update_hint()
                    else:
                        self._status('Choose an owned pixel; padding cannot supply a sample.')
                elif mode == 'cut' and self._cut_line is not None:
                    distance = self._cut_distance(self._cut_line, (x, y))
                    if distance:
                        self._cut_side = 1 if distance > 0 else -1
                        self._paint_cut(self._cut_line)
                        self._update_hint()
                else:
                    self._cancel_gesture()
                    if mode == 'gamma':
                        self._gamma_timer.stop()
                        self._gamma_preview = self._gamma_preview_key = None
                        self._gamma_rectangle = None
                        self._render()
                    self._points = [(x, y)]
                    self._paint_guide(mode)
                self._sync()
            return True
        if self._points and event.type() == kind.MouseMove:
            self._append_point(self._point(event), mode)
            self._paint_guide(mode)
            return True
        if self._points and event.type() == kind.MouseButtonRelease and event.button() == left_button:
            self._append_point(self._point(event), mode)
            self._finish(mode)
            return True
        return False
