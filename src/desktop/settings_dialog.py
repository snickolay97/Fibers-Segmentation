"""Searchable settings and personal editor defaults in one validated form."""

from dataclasses import fields
from typing import get_args

from src.app_settings import PipelineSettings, inspect_settings
from src.default_settings import FACTORY_DEFAULTS
from .editor_preferences import EDITOR_LIMITS, editor_factory, editor_value
from .help import attach_help
from .i18n import register_translations, tr
from .image_controls import DrawingCursor, editor_cursor_preference
from .input_safety import install_parameter_wheel_guard
from .parameter_reference import parameter_entry
from .qt import QtCore, QtGui, QtWidgets


_TEXT = {
    'Appearance': ('Внешний вид', 'מראה'),
    'Interface scale': ('Масштаб интерфейса', 'קנה מידה של הממשק'),
    'Automatic · follow window size': ('Автоматически · по размеру окна', 'אוטומטי · לפי גודל החלון'),
    'Settings…': ('Настройки…', 'הגדרות…'),
    'Processing': ('Обработка', 'עיבוד'),
    'Tile editor': ('Редактор тайлов', 'עורך האריחים'),
    'Mask editor': ('Редактор масок', 'עורך המסכות'),
    'Search by parameter name or key': ('Поиск по названию или ключу', 'חיפוש לפי שם פרמטר או מפתח'),
    'Value to apply': ('Новое значение', 'ערך להחלה'),
    'Default for new projects': ('Для новых проектов', 'ברירת מחדל לפרויקטים חדשים'),
    'Also use these processing settings for new projects': (
        'Использовать эти параметры обработки и в новых проектах',
        'השתמשו גם בהגדרות עיבוד אלו בפרויקטים חדשים'),
    'Reset selected setting': ('Сбросить выбранное поле', 'איפוס ההגדרה שנבחרה'),
    'Reset this tab': ('Сбросить вкладку', 'איפוס הלשונית'),
    'Calibration mode': ('Режим калибровки', 'מצב כיול'),
    'Manual / pixels': ('Вручную / пиксели', 'ידני / פיקסלים'),
    'Automatic from TIFF': ('Автоматически из TIFF', 'אוטומטי מ־TIFF'),
    'Tile eraser radius': ('Радиус ластика тайла', 'רדיוס מחק האריח'),
    'Tile brush radius': ('Радиус кисти тайла', 'רדיוס מברשת האריח'),
    'Local background radius': ('Радиус локального фона', 'רדיוס הרקע המקומי'),
    'Tile editor gamma': ('Гамма редактора тайлов', 'גאמה של עורך האריחים'),
    'Mask bridge width': ('Толщина моста маски', 'רוחב גשר המסכה'),
    'Mask brush width': ('Толщина кисти маски', 'רוחב מברשת המסכה'),
    'Mask route search margin': ('Запас поиска моста', 'שוליים לחיפוש מסלול'),
    'Odd integer from 1 to 101 source px': ('Нечётное целое от 1 до 101 пикс. исходника', 'מספר שלם אי־זוגי מ־1 עד 101 פיקסלים במקור'),
    'From {low} to {high}': ('От {low} до {high}', 'מ־{low} עד {high}'),
    'Check {name}. {rule}': ('Проверьте «{name}». {rule}', 'בדקו את {name}. {rule}'),
    'Editor values apply when you open an editor. Processing applies to future runs.': (
        'Начальные значения редакторов применяются при их открытии. Параметры обработки действуют в новых запусках.',
        'ערכי העורכים מוחלים בפתיחת העורכים. הגדרות העיבוד חלות בהרצות הבאות.'),
}
register_translations({key: val[0] for key, val in _TEXT.items()}, hebrew={key: val[1] for key, val in _TEXT.items()})

_INTEGER = {field.name for field in fields(PipelineSettings)
            if field.type is int or int in get_args(field.type)}
_OPTIONAL = {key for key, value in FACTORY_DEFAULTS.items() if value is None}
_EDITOR_TITLES = {
    'erase_radius': 'Tile eraser radius', 'paint_radius': 'Tile brush radius',
    'background_radius': 'Local background radius', 'gamma': 'Tile editor gamma',
    'connection_width': 'Mask bridge width', 'brush_width': 'Mask brush width',
    'search_margin': 'Mask route search margin',
}
_CHOICES = {'oversized_policy': ('preserve', 'error'), 'calibration_mode': ('auto', 'manual')}
_LABELS = {'auto': 'Automatic from TIFF', 'manual': 'Manual / pixels', 'preserve': 'Preserve', 'error': 'Error'}


class SettingsDialog(QtWidgets.QDialog):
    """Edit a draft and return one complete validated snapshot."""

    def __init__(self, parent, settings, calibration, profile):
        super().__init__(parent)
        self.setWindowTitle(tr('Settings…'))
        self.resize(960, 680)
        self.result_values = None
        self._tabs = {}
        self._rows = {}
        layout = QtWidgets.QVBoxLayout(self)
        search = QtWidgets.QLineEdit()
        search.setPlaceholderText(tr('Search by parameter name or key'))
        search.setClearButtonEnabled(True)
        layout.addWidget(search)
        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs, 1)
        processing = {**settings, 'calibration_mode': calibration}
        factory = {**FACTORY_DEFAULTS, 'calibration_mode': 'auto'}
        personal = {**profile['processing'], 'calibration_mode': profile['calibration_mode']}
        self._add_tab('processing', 'Processing', processing, factory, personal)
        for kind, title in (('tile', 'Tile editor'), ('mask', 'Mask editor')):
            self._add_tab(kind, title, profile[kind], editor_factory(kind))
        appearance = self.appearance = QtWidgets.QWidget()
        appearance_form = QtWidgets.QFormLayout(appearance)
        self.ui_scale = QtWidgets.QComboBox()
        self.ui_scale.addItem(tr('Automatic · follow window size'), 'auto')
        for percent in (100, 125, 150, 175, 200):
            self.ui_scale.addItem(f'{percent}%', str(percent))
        saved_scale = parent.preferences.value('appearance/scale', 'auto') if hasattr(parent, 'preferences') else 'auto'
        self.ui_scale.setCurrentIndex(max(0, self.ui_scale.findData(str(saved_scale))))
        self.drawing_cursor = DrawingCursor(getattr(parent, 'language', None))
        self.drawing_cursor.set_preference(editor_cursor_preference(parent))
        self._appearance_field = self.ui_scale
        self.ui_scale.installEventFilter(self)
        self.drawing_cursor.installEventFilter(self)
        appearance_form.addRow(tr('Interface scale'), attach_help(self.ui_scale, 'interface_scale'))
        appearance_form.addRow(tr('Drawing cursor'), attach_help(self.drawing_cursor, 'editor_cursor'))
        self.tabs.addTab(appearance, tr('Appearance'))
        search.textChanged.connect(self._filter)
        self.personal = QtWidgets.QCheckBox(tr('Also use these processing settings for new projects'))
        layout.addWidget(self.personal)
        info = QtWidgets.QLabel(tr('Editor values apply when you open an editor. Processing applies to future runs.'))
        info.setWordWrap(True)
        layout.addWidget(info)
        actions = QtWidgets.QHBoxLayout()
        for label, selected in (('Reset selected setting', True), ('Reset this tab', False)):
            button = QtWidgets.QPushButton(tr(label))
            button.clicked.connect(lambda checked=False, one=selected: self._reset(one))
            actions.addWidget(button)
        guide = QtWidgets.QPushButton('?')
        guide.setAccessibleName(tr('Settings and recovery'))
        guide.clicked.connect(lambda: self._show_help('settings'))
        actions.addWidget(guide)
        actions.addStretch()
        layout.addLayout(actions)
        self.issue = QtWidgets.QLabel()
        self.issue.setWordWrap(True)
        layout.addWidget(self.issue)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok |
                                            QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        self.ok = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        help_shortcut = QtGui.QShortcut(QtGui.QKeySequence('F1'), self)
        help_shortcut.activated.connect(self._show_help)
        self._help_center = None
        install_parameter_wheel_guard(self)
        self._validate()

    def _display(self, value):
        if value is None:
            return tr('Automatic')
        if isinstance(value, bool):
            return tr('On' if value else 'Off')
        return tr(_LABELS[value]) if isinstance(value, str) else str(value)

    def _add_tab(self, kind, title, values, defaults, personal=None):
        table = QtWidgets.QTableWidget(len(defaults), 4 if personal is not None else 3)
        headers = ['Parameter', 'Value to apply', 'Factory default']
        if personal is not None:
            headers.append('Default for new projects')
        table.setHorizontalHeaderLabels([tr(label) for label in headers])
        table.verticalHeader().hide()
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.tabs.addTab(table, tr(title))
        self._tabs[kind] = table
        self._rows[kind] = {}
        for index, (key, factory) in enumerate(defaults.items()):
            article = parameter_entry(key) if kind == 'processing' else None
            if article:
                name, rule = article['title'], article['valid_range']
            elif key == 'calibration_mode':
                name, rule = tr('Calibration mode'), ''
            else:
                name = tr(_EDITOR_TITLES[key])
                lo, hi = EDITOR_LIMITS[kind][key]
                rule = tr('Odd integer from 1 to 101 source px' if key in ('connection_width', 'brush_width')
                          else 'From {low} to {high}', low=lo, high=hi)
            item = QtWidgets.QTableWidgetItem(name)
            item.setToolTip(key)
            table.setItem(index, 0, item)
            if isinstance(factory, bool):
                control = QtWidgets.QCheckBox()
                signal = control.toggled
            elif key in _CHOICES:
                control = QtWidgets.QComboBox()
                for choice in _CHOICES[key]:
                    control.addItem(tr(_LABELS[choice]), choice)
                signal = control.currentIndexChanged
            else:
                control = QtWidgets.QLineEdit()
                if key in _OPTIONAL:
                    control.setPlaceholderText(tr('Automatic'))
                signal = control.textChanged
            control.setAccessibleName(name)
            control.setToolTip(rule)
            attach_help(control, key if article else 'settings')
            self._put(control, values[key])
            signal.connect(self._validate)
            table.setCellWidget(index, 1, control)
            table.setItem(index, 2, QtWidgets.QTableWidgetItem(self._display(factory)))
            if personal is not None:
                table.setItem(index, 3, QtWidgets.QTableWidgetItem(self._display(personal[key])))
            self._rows[kind][key] = (index, name, rule, factory, control)

    def _put(self, control, value):
        if isinstance(control, QtWidgets.QCheckBox):
            control.setChecked(value)
        elif isinstance(control, QtWidgets.QComboBox):
            control.setCurrentIndex(control.findData(value))
        else:
            control.setText('' if value is None else str(value))

    def _value(self, kind, key, factory, control):
        if isinstance(control, QtWidgets.QCheckBox):
            return control.isChecked()
        if isinstance(control, QtWidgets.QComboBox):
            return control.currentData()
        raw = control.text().strip()
        if key in _OPTIONAL and not raw:
            return None
        if key in _INTEGER or (kind != 'processing' and type(factory) is int):
            return int(raw)
        return float(raw.replace(',', '.'))

    def _filter(self, query):
        words = query.casefold().split()
        matches = []
        for kind, table in self._tabs.items():
            visible = False
            for key, (row, name, _, _, _) in self._rows[kind].items():
                match = all(word in (key + ' ' + name).casefold() for word in words)
                table.setRowHidden(row, not match)
                visible |= match
            if visible:
                matches.append(table)
        if words and any(all(word in label.casefold() for word in words)
                         for label in (tr('Interface scale'), tr('Drawing cursor'), tr('Appearance'))):
            matches.append(self.appearance)
        if matches and self.tabs.currentWidget() not in matches:
            self.tabs.setCurrentWidget(matches[0])

    def _reset(self, one):
        table = self.tabs.currentWidget()
        if table is self.appearance:
            for field in (self.ui_scale, self.drawing_cursor):
                if not one or field is self._appearance_field:
                    field.setCurrentIndex(0)
            return
        kind = next(name for name, widget in self._tabs.items() if widget is table)
        for index, _, _, factory, control in self._rows[kind].values():
            if not one or index == table.currentRow():
                self._put(control, factory)

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.FocusIn and watched in (self.ui_scale, self.drawing_cursor):
            self._appearance_field = watched
        return super().eventFilter(watched, event)

    def _validate(self, *_):
        values = {kind: {} for kind in self._rows}
        invalid = []
        mode = self._rows['processing']['calibration_mode'][-1].currentData()
        calibration = self._rows['processing']['pixel_size_um'][-1]
        calibration.setEnabled(mode == 'manual')
        calibration.setPlaceholderText(tr('Source pixels' if mode == 'manual' else 'Automatic'))
        for kind, entries in self._rows.items():
            for key, (_, name, rule, factory, control) in entries.items():
                try:
                    value = (None if key == 'pixel_size_um' and mode == 'auto'
                             else self._value(kind, key, factory, control))
                    if kind != 'processing':
                        editor_value(kind, key, value)
                    values[kind][key] = value
                except (ValueError, OverflowError):
                    invalid.append((name, rule))
        values['calibration_mode'] = values['processing'].pop('calibration_mode')
        for issue in inspect_settings(values['processing']):
            _, name, rule, _, _ = self._rows['processing'][issue['field']]
            invalid.append((name, rule))
        self.result_values = values if not invalid else None
        self.ok.setEnabled(not invalid)
        self.issue.setText(tr('Check {name}. {rule}', name=invalid[0][0], rule=invalid[0][1]) if invalid else '')

    def _accept(self):
        if self.result_values is not None:
            self.accept()

    def _show_help(self, key=None):
        from .help_center import HelpCenter
        if key is None:
            widget = self.focusWidget()
            key = widget.property('helpKey') if widget is not None else None
        settings = self.result_values['processing'] if self.result_values is not None else {}
        if self._help_center is None:
            self._help_center = HelpCenter(parent=self, current_settings=settings)
        else:
            self._help_center.refresh_settings(settings)
        self._help_center.open_parameter(key or 'settings')
