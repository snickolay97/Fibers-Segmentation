"""Movable, detachable stage panels with a recoverable saved layout."""
from .qt import QtCore, QtGui, QtWidgets
from .i18n import register_translations, tr

register_translations({
    'Panels': 'Панели',
    'Reset panel layout': 'Восстановить расположение панелей',
    'Drag panel headers to rearrange them; double-click a header to detach or dock it.':
        'Перетаскивайте заголовки панелей для перестановки; двойной щелчок выносит панель в отдельное окно или возвращает её.',
    'Source images': 'Исходные изображения',
    'Processing settings': 'Настройки обработки',
    'Image previews': 'Предпросмотр изображений',
    'Tile browser': 'Список тайлов',
    'Tile images': 'Изображения тайлов',
    'Tile actions': 'Действия с тайлами',
    'Segmentation settings': 'Настройки сегментации',
    'Segmentation preview': 'Просмотр сегментации',
    'Detected objects': 'Выделенные объекты',
    'Object preview': 'Просмотр объекта',
    'Assign object type': 'Тип объекта',
    'Feature table': 'Таблица признаков',
    'Object gallery': 'Галерея объектов',
    'Detect objects and assign types': 'Выделить объекты и назначить типы',
    'Review detected objects': 'Разметить выделенные объекты',
    'Choose filters': 'Выбор фильтров',
    'Protective mask': 'Защитная маска',
    'Changes apply to new preparation. Existing tiles keep their saved filtering settings.':
        'Изменения применяются при новой подготовке. Готовые тайлы сохраняют прежние настройки фильтрации.',
    'Classify objects from their image crops. Choose a type with buttons 1–6; the next object opens automatically.':
        'Размечайте объекты по их изображениям. Выбирайте тип кнопками 1–6; следующий объект откроется автоматически.',
    'No detected objects yet. Run automatic detection on the Segmentation page.':
        'Выделенных объектов пока нет. Запустите автоматическое выделение на странице сегментации.',
    'Area: source pixels · AR: major / minor mask axis':
        'Площадь: исходные пиксели · AR: отношение осей маски',
})


class _PanelTitle(QtWidgets.QWidget):
    """Shared title controls for a docked panel and its floating window."""

    def __init__(self, dock):
        super().__init__(dock)
        self.dock = dock
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(7, 2, 3, 2)
        label = QtWidgets.QLabel(dock.windowTitle())
        label.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(label, 1)
        self.dock_button = QtWidgets.QToolButton()
        self.dock_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TitleBarNormalButton))
        self.dock_button.setToolTip(tr('Detach or return panel'))
        self.dock_button.clicked.connect(self.toggle_floating)
        self.maximize_button = QtWidgets.QToolButton()
        self.maximize_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TitleBarMaxButton))
        self.maximize_button.setToolTip(tr('Maximize or restore window'))
        self.maximize_button.clicked.connect(self.toggle_maximized)
        self.close_button = QtWidgets.QToolButton()
        self.close_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TitleBarCloseButton))
        self.close_button.setToolTip(tr('Close'))
        self.close_button.clicked.connect(dock.close)
        for button in (self.dock_button, self.maximize_button, self.close_button):
            button.setFixedSize(26, 24)
            button.setStyleSheet('QToolButton { padding: 0px; }')
            row.addWidget(button)
        self.maximize_button.hide()
        dock.topLevelChanged.connect(self.maximize_button.setVisible)

    def toggle_floating(self):
        if self.dock.isFloating():
            self.dock.showNormal()
            self.dock.setFloating(False)
        else:
            self.dock.setFloating(True)

    def toggle_maximized(self):
        self.dock._drag_start = None
        self.dock._drag_timer.stop()
        if self.dock.isMaximized():
            self.dock.showNormal()
        else:
            self.dock.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.dock._drag_start = event.globalPosition().toPoint()
            self.dock._drag_moved = False
        event.ignore()  # Let QDockWidget handle its usual client-title drag.


class _PanelDock(QtWidgets.QDockWidget):
    """Native floating windows with a fallback for docking into nested stages."""

    def __init__(self, title, workspace):
        super().__init__(title, workspace)
        self.workspace = workspace
        self._drag_start = None
        self._drag_moved = False
        self._drag_timer = QtCore.QTimer(self)
        self._drag_timer.setInterval(30)
        self._drag_timer.timeout.connect(self._track_drag)
        self._help_shortcut = QtGui.QShortcut(QtGui.QKeySequence('F1'), self)
        self._help_shortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._help_shortcut.setEnabled(False)
        self._help_shortcut.activated.connect(self._contextual_help)
        self.topLevelChanged.connect(self._floating_changed)
        self.setTitleBarWidget(_PanelTitle(self))

    def _contextual_help(self):
        callback = getattr(self.workspace.window(), '_contextual_help', None)
        if callback is not None:
            callback()

    def _floating_changed(self, floating):
        self._help_shortcut.setEnabled(floating)
        if floating:
            QtCore.QTimer.singleShot(0, self._configure_float_window)
        else:
            self._drag_timer.stop()
            self._drag_start = None
            self.workspace.hide_drop_preview()

    def _configure_float_window(self):
        if not self.isFloating():
            return
        # Do not replace a native frame in the middle of the detach gesture.
        if QtWidgets.QApplication.mouseButtons() & QtCore.Qt.MouseButton.LeftButton:
            QtCore.QTimer.singleShot(50, self._configure_float_window)
            return
        flags = QtCore.Qt.WindowType.Window | QtCore.Qt.WindowType.FramelessWindowHint
        if self.windowType() == QtCore.Qt.WindowType.Window and self.windowFlags() & QtCore.Qt.WindowType.FramelessWindowHint:
            return
        geometry, state, visible = self.geometry(), self.windowState(), not self.isHidden()
        self.setWindowFlags(flags)
        self.setGeometry(geometry)
        self.setWindowState(state)
        if visible and self.workspace._active:
            self.show()

    def event(self, event):
        if event.type() == QtCore.QEvent.Type.WindowStateChange:
            title = self.titleBarWidget()
            if isinstance(title, _PanelTitle):
                icon = (QtWidgets.QStyle.StandardPixmap.SP_TitleBarNormalButton if self.isMaximized()
                        else QtWidgets.QStyle.StandardPixmap.SP_TitleBarMaxButton)
                title.maximize_button.setIcon(self.style().standardIcon(icon))
        timer = getattr(self, '_drag_timer', None)
        if timer is not None and self.isFloating():
            if (event.type() == QtCore.QEvent.Type.NonClientAreaMouseButtonPress
                    and event.button() == QtCore.Qt.MouseButton.LeftButton):
                self._drag_start = event.globalPosition().toPoint()
                self._drag_moved = False
                timer.start()
            elif event.type() == QtCore.QEvent.Type.NonClientAreaMouseButtonDblClick:
                if event.button() == QtCore.Qt.MouseButton.LeftButton:
                    self.showNormal()
                    self.setFloating(False)
                    return True
        return super().event(event)

    def moveEvent(self, event):
        super().moveEvent(event)
        if (getattr(self, '_drag_timer', None) is not None and self._drag_start is not None and self.isFloating()
                and QtWidgets.QApplication.mouseButtons() & QtCore.Qt.MouseButton.LeftButton):
            self._drag_moved = True
            self._drag_timer.start()

    def _track_drag(self):
        """Track drag and release when the panel floats above the workspace."""
        if not self.isFloating() or self._drag_start is None:
            self._drag_timer.stop()
            self.workspace.hide_drop_preview()
            return
        point = QtGui.QCursor.pos()
        self._drag_moved |= (point - self._drag_start).manhattanLength() >= QtWidgets.QApplication.startDragDistance()
        if QtWidgets.QApplication.mouseButtons() & QtCore.Qt.MouseButton.LeftButton:
            if self._drag_moved:
                self.workspace.preview_drop(self, point)
            return
        self._drag_timer.stop()
        self.workspace.hide_drop_preview()
        moved, self._drag_moved = self._drag_moved, False
        self._drag_start = None
        if moved:
            self.workspace.dock_from_drop(self, point)


class DockWorkspace(QtWidgets.QMainWindow):
    """A stage owns its docks, including when they float outside the main window."""
    def __init__(self, name, preferences, parent=None):
        super().__init__(parent)
        self.name, self.preferences = name, preferences
        self.panels = {}
        self._default_state = None
        self._suspended_state = None
        self._suspended_floating = []
        self._active = False
        self._drop_preview = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Shape.Rectangle, self)
        self.setObjectName('workspace_' + name)
        self.setWindowFlags(QtCore.Qt.WindowType.Widget)
        self.setDockNestingEnabled(True)
        self.setDockOptions(self.DockOption.AllowNestedDocks | self.DockOption.AllowTabbedDocks)
        self.setTabPosition(QtCore.Qt.DockWidgetArea.AllDockWidgetAreas, QtWidgets.QTabWidget.TabPosition.North)
        self.setContentsMargins(0, 0, 0, 0)

    def add_panel(self, key, title, widget, area=QtCore.Qt.DockWidgetArea.LeftDockWidgetArea):
        dock = _PanelDock(tr(title), self)
        dock.setObjectName(self.name + '_' + key)
        dock.setFeatures(dock.DockWidgetFeature.DockWidgetMovable |
                         dock.DockWidgetFeature.DockWidgetFloatable |
                         dock.DockWidgetFeature.DockWidgetClosable)
        dock.setAllowedAreas(QtCore.Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setToolTip(tr('Drag panel headers to rearrange them; double-click a header to detach or dock it.'))
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        self.panels[key] = dock
        return dock

    def _drop_target(self, moving, global_point):
        """Choose a split in this stage, independently of the outer main window."""
        if not self._active or not self.isVisible():
            return None
        point = self.mapFromGlobal(global_point)
        if not self.rect().contains(point):
            return None
        candidates = [dock for dock in self.panels.values()
                      if dock is not moving and not dock.isFloating() and not dock.isHidden()]
        target = next((dock for dock in candidates if dock.geometry().contains(point)), None)
        rect = target.geometry() if target is not None else self.rect()
        # Use relative distances so a long panel remains equally targetable
        # from its short and long edges.
        distances = ((abs(point.x() - rect.left()) / max(rect.width(), 1), 'left'),
                     (abs(rect.right() - point.x()) / max(rect.width(), 1), 'right'),
                     (abs(point.y() - rect.top()) / max(rect.height(), 1), 'top'),
                     (abs(rect.bottom() - point.y()) / max(rect.height(), 1), 'bottom'))
        edge = min(distances)[1]
        preview = QtCore.QRect(rect)
        if edge == 'left': preview.setWidth(rect.width() // 2)
        elif edge == 'right': preview.setLeft(rect.center().x())
        elif edge == 'top': preview.setHeight(rect.height() // 2)
        else: preview.setTop(rect.center().y())
        return target, edge, preview

    def preview_drop(self, moving, global_point):
        target = self._drop_target(moving, global_point)
        if target is None:
            self.hide_drop_preview()
        else:
            self._drop_preview.setGeometry(target[2])
            self._drop_preview.show()
            self._drop_preview.raise_()

    def hide_drop_preview(self):
        self._drop_preview.hide()

    def dock_from_drop(self, moving, global_point):
        result = self._drop_target(moving, global_point)
        if result is None:
            return False
        target, edge, _preview = result
        area = {'left': QtCore.Qt.DockWidgetArea.LeftDockWidgetArea,
                'right': QtCore.Qt.DockWidgetArea.RightDockWidgetArea,
                'top': QtCore.Qt.DockWidgetArea.TopDockWidgetArea,
                'bottom': QtCore.Qt.DockWidgetArea.BottomDockWidgetArea}[edge]
        moving.showNormal()
        moving.setFloating(False)
        if target is None:
            self.addDockWidget(area, moving)
        else:
            orientation = (QtCore.Qt.Orientation.Horizontal if edge in ('left', 'right')
                           else QtCore.Qt.Orientation.Vertical)
            self.splitDockWidget(target, moving, orientation)
            if edge in ('left', 'top'):
                self.splitDockWidget(moving, target, orientation)
        moving.show()
        moving.raise_()
        self.save_layout()
        return True

    def finish_layout(self):
        """Capture the reset layout before applying the user's saved positions."""
        self._default_state = self.saveState(1)
        saved = self.preferences.value('workspaces/' + self.name)
        if isinstance(saved, QtCore.QByteArray):
            self.restoreState(saved, 1)
        # Prevent restored floating docks appearing on an inactive stage.
        self.deactivate()

    def save_layout(self):
        if self._default_state is not None:
            self.preferences.setValue('workspaces/' + self.name,
                                      self._suspended_state if self._suspended_state is not None else self.saveState(1))

    def activate(self):
        self._active = True
        for dock in self._suspended_floating:
            dock.show()
        self._suspended_floating = []
        self._suspended_state = None

    def deactivate(self):
        """Hide a stage's floating windows while retaining their visible layout."""
        self._active = False
        self.hide_drop_preview()
        if self._suspended_state is not None:
            return
        floating = [dock for dock in self.panels.values() if dock.isFloating() and not dock.isHidden()]
        if floating:
            self._suspended_state = self.saveState(1)
            self._suspended_floating = floating
            for dock in floating:
                dock.hide()

    def reset_layout(self):
        self._suspended_state, self._suspended_floating = None, []
        if self._default_state is not None:
            self.restoreState(self._default_state, 1)
            for dock in self.panels.values():
                dock.show()
            callback = getattr(self, 'after_reset', None)
            if callback is not None:
                callback()
        self.save_layout()

    def populate_menu(self, menu):
        menu.clear()
        for dock in self.panels.values():
            menu.addAction(dock.toggleViewAction())
        menu.addSeparator()
        menu.addAction(tr('Reset panel layout'), self.reset_layout)

    def dispose(self):
        self.save_layout()
        for dock in self.panels.values():
            dock.hide()
