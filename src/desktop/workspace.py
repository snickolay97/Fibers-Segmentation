"""Movable, detachable stage panels with a recoverable saved layout."""
from .qt import QtCore, QtWidgets
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
        self.setObjectName('workspace_' + name)
        self.setWindowFlags(QtCore.Qt.WindowType.Widget)
        self.setDockNestingEnabled(True)
        self.setDockOptions(self.DockOption.AllowNestedDocks | self.DockOption.AllowTabbedDocks)
        self.setTabPosition(QtCore.Qt.DockWidgetArea.AllDockWidgetAreas, QtWidgets.QTabWidget.TabPosition.North)
        self.setContentsMargins(0, 0, 0, 0)

    def add_panel(self, key, title, widget, area=QtCore.Qt.DockWidgetArea.LeftDockWidgetArea):
        dock = QtWidgets.QDockWidget(tr(title), self)
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

    def finish_layout(self):
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
        self._active = False
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
