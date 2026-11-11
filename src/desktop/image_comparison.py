"""Side-by-side and same-grid overlay comparisons."""

from pathlib import Path

from .help import attach_help, image_help_button, install_image_help
from .i18n import register_translations, tr
from .image_controls import describe, size_action, tool_icon
from .image_levels import display_image
from .qt import QtCore, QtGui, QtWidgets, show_centered_window


_LABELS = {
    'Compare side by side': ('Сравнить рядом', 'השוואה זו לצד זו'),
    'Side by side': ('Рядом', 'זו לצד זו'),
    'Open comparison window': ('Открыть окно сравнения', 'פתיחת חלון השוואה'),
    'Compare with file…': ('Сравнить с файлом…', 'השוואה לקובץ…'),
    'Overlay': ('Наложение', 'שכבה חופפת'),
    'Top image opacity': ('Непрозрачность верхнего изображения', 'אטימות התמונה העליונה'),
    'Overlay requires two loaded images with the same width and height.': (
        'Для наложения загрузите два изображения одинаковой ширины и высоты.',
        'לחפיפה דרושות שתי תמונות טעונות ברוחב ובגובה זהים.'),
    'Pixel-aligned overlay · {width} × {height} px': (
        'Наложение по пикселям · {width} × {height} px', 'חפיפה לפי פיקסלים · {width} × {height} פיקסלים'),
    'Current image': ('Текущее изображение', 'תמונה נוכחית'),
}
register_translations({key: value[0] for key, value in _LABELS.items()},
                      hebrew={key: value[1] for key, value in _LABELS.items()})


def _add_panes(splitter, titles):
    panes = []
    for title in titles:
        pane = QtWidgets.QGroupBox(title)
        pane_layout = QtWidgets.QVBoxLayout(pane)
        pane_layout.setContentsMargins(4, 8, 4, 4)
        splitter.addWidget(pane)
        panes.append(pane_layout)
    splitter.setChildrenCollapsible(False)
    splitter.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
    splitter.setSizes([1, 1])
    return panes


class ImageComparisonWindow(QtWidgets.QDialog):
    def __init__(self, viewers, titles, parent):
        from .widgets import ImageViewer

        super().__init__(parent)
        self.viewers = viewers
        self._old_hosts = [viewer._host_window for viewer in viewers]
        self.language = viewers[0].language
        self.setLayoutDirection(parent.layoutDirection())
        self.setWindowTitle(self._text('Compare side by side') + ' — ' + ' / '.join(titles))
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(1360, 880)
        layout = QtWidgets.QVBoxLayout(self)
        actions = QtWidgets.QHBoxLayout()
        self.side_button = QtWidgets.QPushButton(self._text('Side by side'))
        self.side_button.setIcon(tool_icon(self.side_button, 'fit'))
        self.overlay_button = QtWidgets.QPushButton(self._text('Overlay'))
        self.overlay_button.setIcon(tool_icon(self.overlay_button, 'compare'))
        group = QtWidgets.QButtonGroup(self)
        for button in (self.side_button, self.overlay_button):
            button.setObjectName('imageComparisonMode')
            button.setCheckable(True)
            button.setAutoDefault(False)
            group.addButton(button)
            actions.addWidget(attach_help(button, 'image_comparison'))
        self.side_button.setChecked(True)
        self._opacity_controls = QtWidgets.QWidget()
        opacity_row = QtWidgets.QHBoxLayout(self._opacity_controls)
        opacity_row.setContentsMargins(5, 0, 0, 0)
        self.opacity = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.setValue(50)
        self.opacity.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        opacity_title = self._text('Top image opacity')
        self.opacity_label = QtWidgets.QLabel(opacity_title)
        self.opacity.setAccessibleName(opacity_title)
        self.opacity_value = QtWidgets.QLabel('50%')
        opacity_row.addWidget(self.opacity_label)
        opacity_row.addWidget(attach_help(self.opacity, 'image_comparison'), 1)
        opacity_row.addWidget(self.opacity_value)
        actions.addWidget(self._opacity_controls, 1)
        actions.addWidget(image_help_button(self, 'image_comparison', self.language))
        install_image_help(self, 'image_comparison', self.language)
        layout.addLayout(actions)
        self.hint = QtWidgets.QLabel()
        self.hint.setObjectName('muted')
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.stack = QtWidgets.QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.splitter = QtWidgets.QSplitter()
        self.panes = _add_panes(self.splitter, titles)
        self.stack.addWidget(self.splitter)
        self.overlay_view = ImageViewer(self, maximum=None)
        self.overlay_view.retranslate(self.language)
        self.overlay_view._host_window = self
        self.overlay_view.compare_file_button.hide()
        self.overlay_view.display_levels_changed.connect(self._tone_top_layer)
        self.stack.addWidget(self.overlay_view)
        self._top_item = None
        self._top_frame = None
        self._overlay_key = None
        self._timer = QtCore.QTimer(self, singleShot=True, interval=45)
        self._timer.timeout.connect(self._sync)
        self.overlay_button.toggled.connect(self._sync)
        self.opacity.valueChanged.connect(self._opacity_changed)
        for viewer, pane in zip(viewers, self.panes):
            pane.addWidget(viewer)
            viewer.show()
            viewer._host_window = self
            viewer.scene.changed.connect(self._schedule_sync)
            viewer.loaded.connect(self._sync)
            viewer.failed.connect(self._sync)
        self.finished.connect(self._release_hosts)
        self._sync()

    def _text(self, message, **values):
        return tr(message, language=self.language, **values)

    def _release_hosts(self, *_):
        self._timer.stop()
        self.overlay_view._close_levels()
        for viewer, host in zip(self.viewers, self._old_hosts):
            viewer._close_levels()
            viewer._host_window = host
            viewer.scene.changed.disconnect(self._schedule_sync)
            viewer.loaded.disconnect(self._sync)
            viewer.failed.disconnect(self._sync)

    def _schedule_sync(self, *_):
        if not self._timer.isActive():
            self._timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for button in (self.side_button, self.overlay_button):
            size_action(button, self.width())

    def _opacity_changed(self, value):
        self.opacity_value.setText(f'{value}%')
        if self._top_item is not None:
            self._top_item.setOpacity(value / 100)

    def _tone_top_layer(self, levels):
        if self._top_item is not None:
            self._top_item.setPixmap(QtGui.QPixmap.fromImage(display_image(self._top_frame, levels)))

    def _sync(self, *_):
        first, second = self.viewers
        can_overlay = (not first._loading and not second._loading and first._pixmap_item is not None
                       and second._pixmap_item is not None and first.original_size == second.original_size)
        self.overlay_button.setEnabled(can_overlay)
        if not can_overlay:
            with QtCore.QSignalBlocker(self.overlay_button):
                self.side_button.setChecked(True)
        active = self.overlay_button.isChecked()
        for widget in (self.opacity, self.opacity_label, self.opacity_value):
            widget.setVisible(active)
        self.hint.setVisible(active or not can_overlay)
        self.stack.setCurrentWidget(self.overlay_view if active else self.splitter)
        if not active:
            self.hint.setText(self._text('Overlay requires two loaded images with the same width and height.'))
            if not can_overlay and self._overlay_key is not None:
                self._top_item = self._overlay_key = None
                self._top_frame = None
                self.overlay_view.clear()
            return
        width, height = first.original_size
        caption = self._text('Pixel-aligned overlay · {width} × {height} px', width=width, height=height)
        self.hint.setText(caption)
        # Use the smaller decoded grid, keeping the true file dimensions for
        # ruler coordinates. Both scenes are mapped from the same origin.
        size = min((viewer._pixmap_item.pixmap().size() for viewer in self.viewers), key=lambda value: value.width())
        left, right = (viewer.render_image_layers(size) for viewer in self.viewers)
        key = first._token, second._token, width, height, size.width(), size.height()
        if self._overlay_key != key:
            self._top_item = None
            scale = first.ruler.scale if first.ruler.scale == second.ruler.scale else None
            self.overlay_view.set_image_frame(left, self._text('Overlay'), ruler_scale=scale, original_size=(width, height))
            self._top_item = self.overlay_view.scene.addPixmap(QtGui.QPixmap.fromImage(right))
            self._top_item.setZValue(1)
            self._overlay_key = key
        else:
            self.overlay_view.replace_display_pixels(left)
        self._top_frame = right
        self._tone_top_layer(self.overlay_view._levels)
        self._opacity_changed(self.opacity.value())


def compare_with_file(viewer, parent):
    from .widgets import ImageViewer

    if viewer._pixmap_item is None or viewer._loading:
        return None
    if viewer._comparison_window is not None:
        viewer._comparison_window.raise_()
        viewer._comparison_window.activateWindow()
        return viewer._comparison_window
    formats = viewer._text('Image files') + ' (*.tif *.tiff *.png *.jpg *.jpeg *.bmp *.gif)'
    formats += ';;' + viewer._text('All files') + ' (*)'
    path, _ = QtWidgets.QFileDialog.getOpenFileName(parent, viewer._text('Compare with file…'), '', formats)
    if not path or viewer._pixmap_item is None or viewer._loading:
        return None
    frame, original_size = viewer.comparison_frame()
    if frame is None:
        return None
    left, right = ImageViewer(), ImageViewer()
    for view in (left, right):
        view.retranslate(viewer.language)
        view.view.setBackgroundBrush(viewer.view.backgroundBrush())
    title = Path(viewer.filename).name or viewer._text('Current image')
    left.set_image_frame(frame, title, ruler_scale=viewer.ruler.scale, original_size=original_size)
    right.set_image(path)
    dialog = ImageComparisonWindow((left, right), (title, Path(path).name), parent)
    viewer._comparison_window = dialog
    dialog.finished.connect(lambda *_: setattr(viewer, '_comparison_window', None))
    show_centered_window(dialog)
    return dialog


def add_comparison(tabs, left_index, right_index, help_key):
    """Place two existing tabs in a splitter while the comparison is open.

    Keep the original indices and move the viewers instead of decoding their
    files again. The same zoom, ruler, and overlay state follows each view.
    """
    current = tabs.currentIndex()
    pair = [(index, tabs.widget(index), tabs.tabText(index)) for index in (left_index, right_index)]
    slots = {}
    for index, viewer, title in sorted(pair, reverse=True):
        tabs.removeTab(index)
        slot = QtWidgets.QWidget()
        slot_layout = QtWidgets.QVBoxLayout(slot)
        slot_layout.setContentsMargins(0, 0, 0, 0)
        slot_layout.addWidget(viewer)
        tabs.insertTab(index, slot, title)
        slots[index] = slot_layout

    splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
    attach_help(splitter, help_key)
    titles = [title for _, _, title in pair]
    panes = _add_panes(splitter, titles)
    compare_index = tabs.addTab(splitter, tr('Compare side by side'))
    popup = None
    open_button = QtWidgets.QToolButton(tabs)
    open_button.setIcon(tool_icon(open_button, 'enlarge'))
    title = tr('Open comparison window')
    open_button.setText(title)
    describe(open_button, title)
    size_action(open_button, tabs.width())
    tabs.setCornerWidget(attach_help(open_button, 'image_comparison'))

    def move_views(index):
        open_button.setVisible(index == compare_index)
        if popup is not None:
            if index != compare_index:
                popup.close()
            return
        for (tab_index, viewer, _), pane in zip(pair, panes):
            target = pane if index == compare_index else slots[tab_index]
            if target.indexOf(viewer) < 0:
                target.addWidget(viewer)
            # Removing a Qt tab can explicitly hide its page. Clear that
            # state even for a viewer already in its single-view slot.
            viewer.show()

    def return_views(*_):
        nonlocal popup
        popup = None
        move_views(tabs.currentIndex())

    def open_window():
        nonlocal popup
        if popup is None:
            popup = ImageComparisonWindow([viewer for _, viewer, _ in pair], titles, tabs)
            popup.finished.connect(return_views)
            show_centered_window(popup)
        else:
            popup.raise_()
            popup.activateWindow()

    open_button.clicked.connect(open_window)
    tabs.currentChanged.connect(move_views)
    tabs.setCurrentIndex(current)
    move_views(tabs.currentIndex())
    return splitter
