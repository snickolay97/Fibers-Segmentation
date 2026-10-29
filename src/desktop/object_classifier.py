"""Manual classes for already detected objects, independent of segmentation."""
import textwrap
import weakref

from .qt import QtCore, QtGui, QtWidgets, Signal
from .i18n import tr, get_language, register_translations
from .help import attach_help, help_label
from .object_labels import CANONICAL_MANUAL_CLASSES


register_translations({
    'Choose a class — save and open the next object': 'Выберите класс — сохранить и перейти к следующему объекту',
    '1–6: assign class and next · ←/→: move · U: next unclassified':
        '1–6: класс и дальше · ←/→: переход · U: следующий без класса',
    'More class controls': 'Дополнительные действия',
    '{number}: {name}. Assign this class and open the next object.':
        '{number}: {name}. Присвоить класс и открыть следующий объект.',
})


class ObjectClassifier(QtWidgets.QWidget):
    apply_class = Signal(object, bool)
    navigate = Signal(str)
    export_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.language = get_language()
        self._row = None
        self._saved_class = None
        self._current = True
        self._assigned, self._total = 0, 0
        self._shortcut_scope = self
        self._shortcuts = []
        self._disposed = False
        self._shortcut_refresh_pending = False
        self.title = QtWidgets.QLabel()
        self.title.setObjectName('sectionTitle')
        self.object_label = QtWidgets.QLabel()
        self.object_label.setWordWrap(True)
        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName('muted')
        self.class_label = QtWidgets.QLabel()
        self.quick_label = QtWidgets.QLabel()
        self.quick_label.setWordWrap(True)
        self.class_buttons = {}
        self.class_grid = QtWidgets.QGridLayout()
        self.class_grid.setSpacing(6)
        self._class_columns = None
        for definition in CANONICAL_MANUAL_CLASSES:
            button = QtWidgets.QPushButton()
            button.setObjectName('classButton_' + definition['key'])
            button.setMinimumHeight(56)
            button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Preferred)
            button.setStyleSheet('QPushButton[assigned="true"] { border: 2px solid #20a585; font-weight: bold; }')
            button.clicked.connect(lambda _checked=False, key=definition['key']: self._quick_assign(key))
            self.class_buttons[definition['key']] = button
        self.shortcut_hint = QtWidgets.QLabel()
        self.shortcut_hint.setObjectName('muted')
        self.shortcut_hint.setWordWrap(True)
        self.advanced_toggle = QtWidgets.QToolButton()
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_toggle.setArrowType(QtCore.Qt.ArrowType.RightArrow)
        self.advanced_controls = QtWidgets.QWidget()
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        self.class_combo = QtWidgets.QComboBox()
        self.class_combo.setObjectName('manualClassCombo')
        self.class_label.setBuddy(self.class_combo)
        attach_help(self.class_combo, 'manual_class')
        self.save_button = QtWidgets.QPushButton()
        self.save_button.setObjectName('saveManualClass')
        self.save_next_button = QtWidgets.QPushButton()
        self.save_next_button.setObjectName('saveManualClassNext')
        self.save_next_button.setProperty('primary', True)
        self.save_button.clicked.connect(lambda: self._apply(False))
        self.save_next_button.clicked.connect(lambda: self._apply(True))
        attach_help(self.save_button, 'manual_class')
        attach_help(self.save_next_button, 'manual_navigation')
        self.previous_button = QtWidgets.QPushButton()
        self.next_button = QtWidgets.QPushButton()
        self.previous_button.setFixedWidth(40)
        self.next_button.setFixedWidth(40)
        self.unlabeled_button = QtWidgets.QPushButton()
        for button, direction in ((self.previous_button, 'previous'),
                                  (self.next_button, 'next'),
                                  (self.unlabeled_button, 'unlabeled')):
            button.clicked.connect(lambda _checked=False, value=direction: self._navigate(value))
            attach_help(button, 'manual_navigation')
        self.progress_label = QtWidgets.QLabel()
        self.progress_label.setWordWrap(True)
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet('QProgressBar { min-height: 8px; max-height: 8px; }')
        self.progress_bar.setTextVisible(False)
        self.export_button = QtWidgets.QPushButton()
        self.export_button.setObjectName('exportTrainingCsv')
        self.export_button.clicked.connect(lambda _checked=False: self.export_requested.emit())
        attach_help(self.export_button, 'manual_export')
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(4)
        header = QtWidgets.QHBoxLayout()
        header.addWidget(self.title)
        header.addWidget(self.object_label, 1)
        layout.addLayout(header)
        layout.addWidget(self.quick_label)
        self.quick_label.hide()
        layout.addLayout(self.class_grid)
        layout.addWidget(self.shortcut_hint)
        advanced_layout = QtWidgets.QVBoxLayout(self.advanced_controls)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        form = QtWidgets.QHBoxLayout()
        form.addWidget(self.class_label)
        form.addWidget(self.class_combo, 1)
        form.addWidget(help_label('manual_class'))
        advanced_layout.addLayout(form)
        save = QtWidgets.QHBoxLayout()
        save.addWidget(self.save_button)
        save.addWidget(self.save_next_button, 1)
        advanced_layout.addLayout(save)
        self.advanced_controls.hide()
        navigation = QtWidgets.QHBoxLayout()
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.next_button)
        navigation.addWidget(self.unlabeled_button, 1)
        layout.addLayout(navigation)
        footer = QtWidgets.QHBoxLayout()
        footer.addWidget(self.progress_label, 1)
        footer.addWidget(self.advanced_toggle)
        layout.addLayout(footer)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.advanced_controls)
        layout.addWidget(self.status_label)
        layout.addWidget(self.export_button)
        for definition in CANONICAL_MANUAL_CLASSES:
            self._add_shortcut(str(definition['id']+1), 'class',
                               lambda key=definition['key']: self._quick_assign(key))
        for key, direction in (('Left', 'previous'), ('Right', 'next'), ('U', 'unlabeled')):
            self._add_shortcut(key, 'navigate', lambda value=direction: self._navigate(value))
        application = QtWidgets.QApplication.instance()
        reference = weakref.ref(self)
        def focus_handler(old, new):
            widget = reference()
            if widget is None:
                return
            try:
                widget.objectName()  # Check that its C++ widget still exists.
                widget._focus_changed(old, new)
            except RuntimeError:
                try:
                    application.focusChanged.disconnect(focus_handler)
                except (RuntimeError, TypeError):
                    pass
        def deferred_update():
            widget = reference()
            if widget is not None:
                try:
                    widget.objectName()
                    widget._shortcut_refresh_pending = False
                    widget._update_shortcuts()
                except RuntimeError:
                    pass
        def disconnect_focus(_object=None):
            try:
                application.focusChanged.disconnect(focus_handler)
            except (RuntimeError, TypeError):
                pass
        self._focus_handler, self._deferred_update = focus_handler, deferred_update
        application.focusChanged.connect(focus_handler)
        self.destroyed.connect(disconnect_focus)
        self.retranslate(self.language)
        self.set_object(None)

    def _text(self, text, **values):
        return tr(text, language=self.language, **values)

    def retranslate(self, language=None):
        self.language = language or get_language()
        chosen = self.class_combo.currentData()
        self.class_combo.blockSignals(True)
        self.class_combo.clear()
        self.class_combo.addItem(self._text('Unclassified'), None)
        for definition in CANONICAL_MANUAL_CLASSES:
            self.class_combo.addItem(self._text(definition['label_en']), definition['key'])
            self.class_combo.setItemData(self.class_combo.count()-1, definition['id'],
                                         QtCore.Qt.ItemDataRole.UserRole+1)
        index = self.class_combo.findData(chosen)
        self.class_combo.setCurrentIndex(max(0, index))
        self.class_combo.blockSignals(False)
        self.title.setText(self._text('Manual object classes'))
        self.quick_label.setText(self._text('Choose a class — save and open the next object'))
        self.title.setToolTip(self.quick_label.text())
        self.shortcut_hint.setText(self._text('1–6: assign class and next · ←/→: move · U: next unclassified'))
        self.advanced_toggle.setText(self._text('More class controls'))
        self._arrange_classes()
        for definition in CANONICAL_MANUAL_CLASSES:
            button = self.class_buttons[definition['key']]
            name = self._text(definition['label_en'])
            button.setToolTip(self._text('{number}: {name}. Assign this class and open the next object.',
                                        number=definition['id']+1, name=name))
        self.class_label.setText(self._text('Class'))
        self.save_button.setText(self._text('Save class'))
        self.save_next_button.setText(self._text('Save and next'))
        self.previous_button.setText('←')
        self.next_button.setText('→')
        self.unlabeled_button.setText('↪ ' + self._text('Unclassified'))
        for button,text in ((self.previous_button,'Previous'),(self.next_button,'Next'),
                            (self.unlabeled_button,'Next unclassified')):
            button.setToolTip(self._text(text))
            button.setAccessibleName(self._text(text))
        self.export_button.setText(self._text('Export training CSV'))
        self.set_progress(self._assigned, self._total)
        self._update_state()

    def set_object(self, row, currentlabel=None):
        self._row = dict(row) if row is not None else None
        label = currentlabel or self._row or {}
        key = label.get('Manual_Class') or label.get('class_key')
        self._saved_class = key
        index = self.class_combo.findData(key)
        self.class_combo.setCurrentIndex(max(0, index))
        self._update_state()

    def set_progress(self, assigned, total):
        self._total = max(0, int(total))
        self._assigned = max(0, min(int(assigned), self._total))
        self.progress_label.setText(self._text('{assigned} / {total} objects classified',
                                               assigned=self._assigned, total=self._total))
        self.progress_bar.setRange(0, max(1, self._total))
        self.progress_bar.setValue(self._assigned)
        self._update_state()

    def set_enabled_current(self, current):
        self._current = bool(current)
        self._update_state()

    def _update_state(self):
        enabled = self._current and self._row is not None
        for widget in (self.class_combo, self.save_button, self.save_next_button):
            widget.setEnabled(enabled)
        for key, button in self.class_buttons.items():
            button.setEnabled(enabled)
            assigned = key == self._saved_class
            if button.property('assigned') != assigned:
                button.setProperty('assigned', assigned)
                button.style().unpolish(button)
                button.style().polish(button)
                button.update()
        for button in (self.previous_button, self.next_button, self.unlabeled_button):
            button.setEnabled(self._current and self._total > 0)
        self.export_button.setEnabled(self._current and self._assigned > 0)
        if self._row is None:
            self.object_label.setText(self._text('Select an object from the results table'))
        else:
            self.object_label.setText(self._text('{tile} · Object {object}',
                                                tile=self._row.get('Tile_Name', ''),
                                                object=self._row.get('Object_ID', '')))
        if not self._current:
            self.status_label.setText(self._text('Recalculate current results before assigning classes'))
            self.status_label.show()
        else:
            self.status_label.setText(self._text('Manual classes are saved separately from segmentation labels'))
            self.status_label.hide()
        self._update_shortcuts()

    def _arrange_classes(self):
        columns = 3 if self.width() >= 480 else 2
        if columns != self._class_columns:
            while self.class_grid.count():
                self.class_grid.takeAt(0)
            for definition in CANONICAL_MANUAL_CLASSES:
                self.class_grid.addWidget(self.class_buttons[definition['key']],
                                           definition['id']//columns, definition['id']%columns)
            for column in range(3):
                self.class_grid.setColumnStretch(column, 1 if column < columns else 0)
            self._class_columns = columns
        cell_width = max(80, (self.width() - 6*(columns-1))//columns)
        metrics = self.fontMetrics()
        wrap = max(12, int((cell_width-38)/max(1, metrics.averageCharWidth())))
        for definition in CANONICAL_MANUAL_CLASSES:
            name = self._text(definition['label_en'])
            self.class_buttons[definition['key']].setText(str(definition['id']+1) + '  ' +
                textwrap.fill(name, width=wrap, break_long_words=False))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'class_grid'):
            self._arrange_classes()

    def _toggle_advanced(self, expanded):
        self.advanced_controls.setVisible(expanded)
        self.advanced_toggle.setArrowType(QtCore.Qt.ArrowType.DownArrow if expanded else QtCore.Qt.ArrowType.RightArrow)

    def _add_shortcut(self, key, kind, callback):
        shortcut = QtGui.QShortcut(QtGui.QKeySequence(key), self._shortcut_scope)
        shortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(callback)
        self._shortcuts.append((shortcut, kind))

    def set_shortcut_scope(self, widget):
        """Keep shortcuts inside the review workspace, including floating docks."""
        self._shortcut_scope = widget or self
        for shortcut, _kind in self._shortcuts:
            shortcut.setParent(self._shortcut_scope)
        self._update_shortcuts()

    def _focus_changed(self, _old, _new):
        self._update_shortcuts(reparent=False)
        if not self._disposed and not self._shortcut_refresh_pending:
            self._shortcut_refresh_pending = True
            QtCore.QTimer.singleShot(0, self._deferred_update)

    def _update_shortcuts(self, reparent=True):
        if self._disposed:
            return
        focus = QtWidgets.QApplication.focusWidget()
        # Floating docks are separate Qt windows even while they retain their
        # workspace parent. Scope shortcuts to that window only while it has
        # focus, then move them back to the review workspace.
        scope = self._shortcut_scope
        current = focus
        within = False
        try:
            while current is not None:
                if current is scope:
                    within = True
                    break
                current = current.parent()
            shortcut_parent = focus.window() if within and focus.window() is not scope.window() else scope
        except RuntimeError:
            self.dispose()
            return
        editing = isinstance(focus, (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox,
                                    QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit, QtWidgets.QComboBox))
        for shortcut, kind in self._shortcuts:
            try:
                if reparent and shortcut.parent() is not shortcut_parent:
                    shortcut.setParent(shortcut_parent)
                available = self._row is not None if kind == 'class' else self._total > 0
                shortcut.setEnabled(self._current and available and not editing)
            except RuntimeError:
                # A workspace being destroyed can own shortcuts independently
                # of a floating classifier. Ignore its deleted Qt children.
                continue

    def dispose(self):
        if self._disposed:
            return
        self._disposed = True
        application = QtWidgets.QApplication.instance()
        if application is not None:
            try:
                application.focusChanged.disconnect(self._focus_handler)
            except (RuntimeError, TypeError):
                pass
        for shortcut, _kind in self._shortcuts:
            try:
                shortcut.setEnabled(False)
                shortcut.activated.disconnect()
                shortcut.deleteLater()
            except (RuntimeError, TypeError):
                pass
        self._shortcuts.clear()

    def closeEvent(self, event):
        self.dispose()
        super().closeEvent(event)

    def _quick_assign(self, key):
        if self._current and self._row is not None:
            self.class_combo.setCurrentIndex(self.class_combo.findData(key))
            self.apply_class.emit(key, True)

    def _apply(self, next_object):
        if self._current and self._row is not None:
            self.apply_class.emit(self.class_combo.currentData(), bool(next_object))

    def _navigate(self, direction):
        if self._current and self._total > 0:
            self.navigate.emit(direction)
