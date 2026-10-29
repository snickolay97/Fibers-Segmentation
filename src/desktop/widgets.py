"""Reusable, responsive image and CSV widgets for the local desktop UI."""

import csv
import os
from pathlib import Path
import tempfile

from .qt import QtCore, QtGui, QtWidgets, Signal
from .i18n import tr, get_language
from .help import attach_help, help_label
from .object_labels import CANONICAL_MANUAL_CLASSES


_IMAGE_POOL = QtCore.QThreadPool()
_IMAGE_POOL.setMaxThreadCount(1)


def image_pool():
    """Serialize native preview decoding to keep memory use bounded."""
    return _IMAGE_POOL


class _ImageSignals(QtCore.QObject):
    ready = Signal(int, object, object)
    failed = Signal(int, str)


class _ImageTask(QtCore.QRunnable):
    def __init__(self, token, filename, maximum=2400):
        super().__init__()
        self.token, self.filename, self.maximum = token, filename, maximum
        self.signals = _ImageSignals()
        self.cancelled = False

    def run(self):
        try:
            if self.cancelled:
                self.signals.failed.emit(self.token, "Cancelled")
                return
            from PIL import Image
            import numpy as np
            # These are user-selected scientific outputs. Native canvases can
            # legitimately exceed Pillow's generic web-image size threshold.
            Image.MAX_IMAGE_PIXELS = None
            # Images remain on disk; only a bounded preview enters the Qt scene.
            with Image.open(self.filename) as source:
                original_size = source.size
                if source.mode in ("I", "I;16", "I;16L", "I;16B"):
                    pixels = np.asarray(source)
                    source = Image.fromarray((pixels >> 8).astype(np.uint8))
                source.thumbnail((self.maximum, self.maximum), Image.Resampling.LANCZOS)
                rgb = source.convert("RGB")
                width, height = rgb.size
                data = rgb.tobytes()
                image = QtGui.QImage(
                    data, width, height, width * 3, QtGui.QImage.Format.Format_RGB888
                ).copy()
            if self.cancelled:
                self.signals.failed.emit(self.token, "Cancelled")
            else:
                self.signals.ready.emit(self.token, image, original_size)
        except Exception as exc:
            self.signals.failed.emit(self.token, str(exc))


class _FullscreenImageDialog(QtWidgets.QDialog):
    """A second view of an existing scene; never owns or decodes the image."""

    def __init__(self, owner):
        super().__init__(owner)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(owner._text('Full screen') + ' — ' + Path(owner.filename).name)
        self.view = QtWidgets.QGraphicsView(owner.scene, self)
        owner._configure_view(self.view)
        self.caption = QtWidgets.QLabel(owner.caption.text())
        self.caption.setWordWrap(True)
        self.caption.setObjectName('muted')
        controls = QtWidgets.QHBoxLayout()
        self.zoom_out_button = QtWidgets.QPushButton('−')
        self.zoom_in_button = QtWidgets.QPushButton('+')
        self.fit_button = QtWidgets.QPushButton(owner._text('Fit to window'))
        self.exit_button = QtWidgets.QPushButton(owner._text('Exit full screen') + ' · Esc')
        self.zoom_out_button.clicked.connect(lambda: owner._zoom_view(self.view, 1 / 1.3))
        self.zoom_in_button.clicked.connect(lambda: owner._zoom_view(self.view, 1.3))
        self.fit_button.clicked.connect(self.fit)
        self.exit_button.clicked.connect(self.close)
        for button, key in ((self.zoom_out_button, 'image_zoom'), (self.zoom_in_button, 'image_zoom'),
                            (self.fit_button, 'image_fit'), (self.exit_button, 'image_fullscreen')):
            attach_help(button, key)
            controls.addWidget(button)
        controls.addWidget(help_label('image_fullscreen'))
        controls.addStretch()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.caption)
        layout.addLayout(controls)
        self.f11_shortcut = QtGui.QShortcut(QtGui.QKeySequence('F11'), self)
        self.f11_shortcut.activated.connect(self.close)
        self.escape_shortcut = QtGui.QShortcut(QtGui.QKeySequence('Esc'), self)
        self.escape_shortcut.activated.connect(self.close)
        self.fit_timer = QtCore.QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self.fit)
        self.finished.connect(lambda _result: self.view.setScene(None))

    def fit(self):
        scene = self.view.scene()
        if scene is not None:
            self.view.fitInView(scene.sceneRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_timer.start(0)
        self.view.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)

    def closeEvent(self, event):
        self.fit_timer.stop()
        self.view.setScene(None)
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'fit_timer'):
            self.fit_timer.start(0)


class ImageViewer(QtWidgets.QWidget):
    """Pan/zoom preview; clicked coordinates refer to the original image."""

    clicked = Signal(float, float)
    loaded = Signal(str, object)
    failed = Signal(str)

    def __init__(self, parent=None, empty_text="Select an image to preview"):
        super().__init__(parent)
        self.language = get_language()
        self._empty_message = empty_text
        self._loading, self._error = False, None
        self._token = 0
        self._tasks = {}
        self._filename = ""
        self._original_size = (0, 0)
        self._press_position = None
        self._fit_pending = False
        self._auto_fit = True
        self._fit_timer = QtCore.QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.timeout.connect(self._apply_auto_fit)
        self._polygons = []
        self._overlay_items = []
        self._fullscreen_dialog = None
        self._press_positions = {}
        self._pending_click = None
        self._click_timer = QtCore.QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._deliver_click)
        self.scene = QtWidgets.QGraphicsScene(self)
        self.view = QtWidgets.QGraphicsView(self.scene, self)
        self._configure_view(self.view)
        self.view.setMinimumSize(230, 160)
        self.caption = QtWidgets.QLabel(self._text(empty_text))
        self.caption.setWordWrap(True)
        self.caption.setObjectName("muted")
        caption_row = QtWidgets.QHBoxLayout()
        caption_row.addWidget(self.caption, 1)
        self.fullscreen_button = QtWidgets.QToolButton()
        self.fullscreen_button.setObjectName('imageFullScreen')
        self.fullscreen_button.setIcon(self._fullscreen_icon())
        self.fullscreen_button.setFixedSize(28, 26)
        self.fullscreen_button.setEnabled(False)
        self.fullscreen_button.setAccessibleName(self._text('Full screen'))
        attach_help(self.fullscreen_button, 'image_fullscreen')
        self.fullscreen_button.setToolTip(self._text('Full screen · double-click or F11; Esc to close'))
        self.fullscreen_button.clicked.connect(self.open_fullscreen)
        caption_row.addWidget(self.fullscreen_button)
        controls = QtWidgets.QHBoxLayout()
        for label, callback in (("−", lambda: self.zoom(1 / 1.3)),
                                ("+", lambda: self.zoom(1.3)),
                                (self._text("Fit to window"), self.fit)):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(callback)
            attach_help(button, 'image_fit' if callback == self.fit else 'image_zoom')
            if callback == self.fit:
                self.fit_button = button
            controls.addWidget(button)
        controls.addWidget(help_label('image_viewer'))
        attach_help(self.view, 'image_viewer')
        controls.addStretch()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 1)
        layout.addLayout(caption_row)
        layout.addLayout(controls)
        self._pixmap_item = None
        self.f11_shortcut = QtGui.QShortcut(QtGui.QKeySequence('F11'), self)
        self.f11_shortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.f11_shortcut.activated.connect(self.open_fullscreen)
        # Qt can deliver viewport callbacks during construction/destruction.
        # Subscribe only after every handler attribute exists.
        self.view.viewport().installEventFilter(self)

    def _configure_view(self, view):
        view.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        view.setRenderHints(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        view.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        view.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        view.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter)
        attach_help(view, 'image_viewer')

    def _fullscreen_icon(self):
        pixmap = QtGui.QPixmap(18, 18)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        pen = QtGui.QPen(self.palette().color(QtGui.QPalette.ColorRole.WindowText), 1.7)
        painter.setPen(pen)
        for x, y, dx, dy in ((3, 3, 1, 1), (15, 3, -1, 1), (3, 15, 1, -1), (15, 15, -1, -1)):
            painter.drawLine(QtCore.QPointF(x, y), QtCore.QPointF(x + dx * 4, y))
            painter.drawLine(QtCore.QPointF(x, y), QtCore.QPointF(x, y + dy * 4))
        painter.end()
        return QtGui.QIcon(pixmap)

    def open_fullscreen(self):
        if self._pixmap_item is None or self._loading:
            return None
        self._cancel_click()
        if self._fullscreen_dialog is not None:
            self._fullscreen_dialog.raise_()
            self._fullscreen_dialog.activateWindow()
            return self._fullscreen_dialog
        dialog = _FullscreenImageDialog(self)
        self._fullscreen_dialog = dialog
        dialog.view.viewport().installEventFilter(self)
        dialog.finished.connect(lambda _result, current=dialog: self._fullscreen_finished(current))
        dialog.showFullScreen()
        return dialog

    def close_fullscreen(self):
        dialog = getattr(self, '_fullscreen_dialog', None)
        if dialog is not None:
            try:
                dialog.close()
            except RuntimeError:
                self._fullscreen_dialog = None

    def _fullscreen_finished(self, dialog):
        self._cancel_click()
        try:
            dialog.view.viewport().removeEventFilter(self)
        except RuntimeError:
            pass
        if self._fullscreen_dialog is dialog:
            self._fullscreen_dialog = None
        try:
            if self.view.isVisible():
                self.view.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
        except RuntimeError:
            pass

    def _cancel_click(self):
        timer = getattr(self, '_click_timer', None)
        if timer is not None:
            try:
                timer.stop()
            except RuntimeError:
                pass
        self._pending_click = None
        positions = getattr(self, '_press_positions', None)
        if positions is not None:
            positions.clear()

    def _deliver_click(self):
        pending, self._pending_click = self._pending_click, None
        if pending is not None and pending[0] == self._token and self._pixmap_item is not None:
            self.clicked.emit(pending[1], pending[2])

    def _text(self, text, **values):
        return tr(text, language=self.language, **values)

    def retranslate(self, language=None):
        self.close_fullscreen()
        self.language = language or get_language()
        self.fit_button.setText(self._text('Fit to window'))
        self.fullscreen_button.setAccessibleName(self._text('Full screen'))
        self.fullscreen_button.setToolTip(tr('Full screen · double-click or F11; Esc to close', language=self.language))
        if self._loading:
            self.caption.setText(self._text('Loading preview…'))
        elif self._error:
            self.caption.setText(self._text('Could not open image: {message}', message=self._error))
        elif self._pixmap_item is None:
            self.caption.setText(self._text(self._empty_message))
        self._draw_polygons()

    @property
    def original_size(self):
        return self._original_size

    @property
    def filename(self):
        return self._filename

    def clear(self, message="Select an image to preview"):
        self.close_fullscreen()
        self._cancel_click()
        self._auto_fit = True
        self._fit_pending = False
        self._stop_fit_timer()
        self.fullscreen_button.setEnabled(False)
        for task, _ in self._tasks.values():
            task.cancelled = True
        self._token += 1
        self.scene.clear()
        self._pixmap_item = None
        self._overlay_items = []
        self._polygons = []
        self._original_size = (0, 0)
        self._filename = ""
        self._empty_message, self._loading, self._error = message, False, None
        self.caption.setText(self._text(message))

    def set_image(self, filename, caption=None):
        self.close_fullscreen()
        self._cancel_click()
        self._auto_fit = True
        self._stop_fit_timer()
        self.fullscreen_button.setEnabled(False)
        for task, _ in self._tasks.values():
            task.cancelled = True
        if not filename or not Path(filename).is_file():
            self.clear("Image is missing")
            return
        self._token += 1
        self._filename = str(filename)
        self.scene.clear()
        self._pixmap_item = None
        self._original_size = (0, 0)
        self._polygons = []
        self._overlay_items = []
        self._loading, self._error = True, None
        self.caption.setText(self._text("Loading preview…"))
        task = _ImageTask(self._token, str(filename))
        task.signals.ready.connect(self._image_ready)
        task.signals.failed.connect(self._image_failed)
        self._tasks[self._token] = (task, caption)
        image_pool().start(task)

    def _image_ready(self, token, image, original_size):
        task, caption = self._tasks.pop(token, (None, None))
        if token != self._token:
            return
        self.scene.clear()
        self._loading, self._error = False, None
        self._pixmap_item = self.scene.addPixmap(QtGui.QPixmap.fromImage(image))
        self._original_size = original_size
        self.scene.setSceneRect(self._pixmap_item.boundingRect())
        self._draw_polygons()
        self.caption.setText(caption or f"{Path(self._filename).name}  ·  {original_size[0]} × {original_size[1]} px")
        self.fullscreen_button.setEnabled(True)
        self.fit()
        self.loaded.emit(self._filename, original_size)

    def _image_failed(self, token, message):
        self._tasks.pop(token, None)
        if token != self._token:
            return
        self.close_fullscreen()
        self.fullscreen_button.setEnabled(False)
        self.scene.clear()
        self._pixmap_item = None
        self._loading, self._error = False, message
        self.caption.setText(self._text("Could not open image: {message}", message=message))
        self.failed.emit(message)

    def set_polygons(self, polygons):
        """Each polygon has class_id and normalized model-canvas points."""
        self._polygons = list(polygons)
        self._draw_polygons()

    def _draw_polygons(self):
        for item in self._overlay_items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self._overlay_items = []
        if self._pixmap_item is None:
            return
        bounds = self._pixmap_item.boundingRect()
        colors = ["#3be2b9", "#ffce55", "#cf99ff", "#ff8e8e", "#7fc8ff"]
        for polygon in self._polygons:
            class_id = int(polygon.get("class_id", -1))
            color = QtGui.QColor(colors[class_id % len(colors)])
            points = QtGui.QPolygonF([
                QtCore.QPointF(float(x) * bounds.width(), float(y) * bounds.height())
                for x, y in polygon.get("points", [])
            ])
            pen = QtGui.QPen(color, 2)
            pen.setCosmetic(True)
            fill = QtGui.QColor(color)
            fill.setAlpha(25)
            item = self.scene.addPolygon(points, pen, QtGui.QBrush(fill))
            item.setToolTip(self._text('Class {id}', id=class_id))
            item.setZValue(1)
            self._overlay_items.append(item)

    def fit(self):
        self._auto_fit = True
        self._fit_pending = True
        self._apply_auto_fit()
        self._queue_auto_fit()

    def _queue_auto_fit(self):
        timer = getattr(self, '_fit_timer', None)
        if timer is not None and getattr(self, '_auto_fit', False) and getattr(self, '_pixmap_item', None) is not None:
            self._fit_pending = True
            try:
                timer.start(0)
            except RuntimeError:
                pass

    def _apply_auto_fit(self):
        view, item = getattr(self, 'view', None), getattr(self, '_pixmap_item', None)
        if not getattr(self, '_auto_fit', False) or view is None or item is None:
            return
        try:
            if view.isVisible():
                view.fitInView(item.boundingRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
                self._fit_pending = False
        except RuntimeError:
            pass

    def _stop_fit_timer(self):
        timer = getattr(self, '_fit_timer', None)
        if timer is not None:
            try:
                timer.stop()
            except RuntimeError:
                pass

    def _keep_manual_transform(self):
        self._auto_fit = False
        self._fit_pending = False
        self._stop_fit_timer()

    def zoom(self, factor):
        self._zoom_view(self.view, factor)

    def _zoom_view(self, view, factor):
        if self._pixmap_item is not None:
            scale = view.transform().m11()
            if 0.02 <= scale * factor <= max(40, scale if factor < 1 else 40):
                if view is self.view:
                    self._keep_manual_transform()
                view.scale(factor, factor)

    def eventFilter(self, watched, event):
        embedded = getattr(self, 'view', None)
        if embedded is None:
            return False
        dialog = getattr(self, '_fullscreen_dialog', None)
        try:
            view = embedded if watched is embedded.viewport() else None
            fullscreen = getattr(dialog, 'view', None)
            if fullscreen is not None and watched is fullscreen.viewport():
                view = fullscreen
        except RuntimeError:
            # A native viewport can outlive its Python wrapper during deferred
            # deletion. An exception escaping a Qt callback aborts PyQt apps.
            return False
        if view is not None:
            if view is embedded and event.type() in (QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show):
                self._queue_auto_fit()
            if event.type() == QtCore.QEvent.Type.Wheel and getattr(self, '_pixmap_item', None) is not None:
                self._zoom_view(view, 1.18 if event.angleDelta().y() > 0 else 1 / 1.18)
                return True
            if event.type() == QtCore.QEvent.Type.MouseButtonDblClick and event.button() == QtCore.Qt.MouseButton.LeftButton:
                self._cancel_click()
                if view is self.view:
                    self.open_fullscreen()
                else:
                    self.close_fullscreen()
                return True
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                if event.button() == QtCore.Qt.MouseButton.LeftButton:
                    self._press_positions[view] = event.position().toPoint()
            elif event.type() == QtCore.QEvent.Type.MouseMove and view is embedded:
                origin = self._press_positions.get(view)
                if origin is not None and (event.position().toPoint() - origin).manhattanLength() >= 5:
                    self._keep_manual_transform()
            elif event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton:
                press_position = self._press_positions.pop(view, None)
                position = event.position().toPoint()
                if press_position is not None and (position - press_position).manhattanLength() < 5 and self._pixmap_item is not None:
                    point = view.mapToScene(position)
                    rect = self._pixmap_item.boundingRect()
                    if rect.contains(point):
                        self._pending_click = (self._token,
                            point.x() * self._original_size[0] / rect.width(),
                            point.y() * self._original_size[1] / rect.height())
                        # Distinguish a selection from the first half of a
                        # double-click, which opens the image instead.
                        self._click_timer.start(QtWidgets.QApplication.doubleClickInterval())
        return super().eventFilter(watched, event)

    def hideEvent(self, event):
        self.close_fullscreen()
        self._cancel_click()
        self._stop_fit_timer()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.close_fullscreen()
        self._cancel_click()
        self._stop_fit_timer()
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._queue_auto_fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._queue_auto_fit()

    def changeEvent(self, event):
        if event.type() in (QtCore.QEvent.Type.PaletteChange, QtCore.QEvent.Type.StyleChange) and hasattr(self, 'fullscreen_button'):
            self.fullscreen_button.setIcon(self._fullscreen_icon())
        super().changeEvent(event)


class _FilterComboBox(QtWidgets.QComboBox):
    def findData(self, data, role=QtCore.Qt.ItemDataRole.UserRole, flags=None):
        # Qt's QVariant search cannot compare Python tuple payloads on every
        # binding. Keep the source/manual filter identity portable.
        if isinstance(data, (tuple, list)):
            for index in range(self.count()):
                value = self.itemData(index, role)
                if isinstance(value, (tuple, list)) and tuple(value) == tuple(data):
                    return index
            return -1
        return super().findData(data, role) if flags is None else super().findData(data, role, flags)


class CsvTable(QtWidgets.QWidget):
    """Read-only scientific features with a separate overlay of manual targets."""

    row_selected = Signal(object)
    MANUAL_HEADERS = ('Manual_Class_ID', 'Manual_Class', 'Reviewed')
    HEADER_LABELS = {
        'Class_Name':'Source class', 'Class_ID':'Source class ID', 'Tile_Name':'Tile',
        'Object_ID':'Object', 'Large_Image':'Source dataset', 'Area':'Area, px²',
        'Aspect_Ratio':'AR (major / minor axis)', 'Solidity':'Solidity',
        'Euler_Number':'Euler number', 'Endpoints':'Skeleton endpoints',
        'Branch_Points':'Branch pixels', 'Measurement_Space':'Measurement space',
        'Source_Pixels_Per_Output_Pixel':'Source px / model px', 'Area_um2':'Area, µm²',
        'Manual_Class_ID':'Manual class ID', 'Manual_Class':'Manual class', 'Reviewed':'Reviewed'}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.language = get_language()
        self.headers, self.rows, self.visible_rows = [], [], []
        self._source_headers, self._source_rows = [], []
        self._manual_enabled = False
        self.source_path = None
        self.class_filter = _FilterComboBox()
        self.search = QtWidgets.QLineEdit()
        self.count = QtWidgets.QLabel()
        attach_help(self.class_filter, 'result_class_filter')
        attach_help(self.search, 'result_search')
        self.table = QtWidgets.QTableWidget()
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.class_filter.currentIndexChanged.connect(self.apply_filter)
        self.search.textChanged.connect(self.apply_filter)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.class_filter)
        top.addWidget(help_label('result_class_filter'))
        top.addWidget(self.search, 1)
        top.addWidget(help_label('result_search'))
        top.addWidget(self.count)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        self.retranslate(self.language)

    def _text(self, text, **values):
        return tr(text, language=self.language, **values)

    def retranslate(self, language=None):
        self.language = language or get_language()
        self.search.setPlaceholderText(self._text('Search by tile, object or class'))
        self._refresh_classes()
        self.apply_filter()

    @staticmethod
    def _object_key(row):
        return str(row.get('Tile_Name', '')) + '/' + str(row.get('Object_ID', ''))

    def _manual_name(self, key):
        if not key:
            return self._text('Unclassified')
        entry = next((item for item in CANONICAL_MANUAL_CLASSES if item['key'] == key), None)
        return self._text(entry['label_en']) if entry else str(key)

    def _refresh_classes(self):
        selected = self.class_filter.currentData()
        self.class_filter.blockSignals(True)
        self.class_filter.clear()
        self.class_filter.addItem(self._text('All classes'), None)
        for name in sorted({str(row.get('Class_Name') or 'Unknown') for row in self.rows}):
            label = self._text('Source: {class_name}', class_name=self._text(name)) if self._manual_enabled else self._text(name)
            self.class_filter.addItem(label, name)
        if self._manual_enabled:
            self.class_filter.addItem(self._text('Unclassified'), ('manual', None))
            for definition in CANONICAL_MANUAL_CLASSES:
                self.class_filter.addItem(self._text('Manual: {class_name}',
                    class_name=self._manual_name(definition['key'])), ('manual', definition['key']))
        found = self.class_filter.findData(selected)
        self.class_filter.setCurrentIndex(max(0, found))
        self.class_filter.blockSignals(False)

    def clear(self):
        self.headers, self.rows, self.visible_rows = [], [], []
        self._source_headers, self._source_rows = [], []
        self._manual_enabled = False
        self.source_path = None
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._refresh_classes()
        self.apply_filter()

    def load_csv(self, filename):
        with open(filename, encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            self._source_headers = reader.fieldnames or []
            self._source_rows = list(reader)
        self.headers = list(self._source_headers)
        self.rows = [dict(row) for row in self._source_rows]
        self._manual_enabled = 'Manual_Class' in self.headers
        self.source_path = str(filename)
        self._refresh_classes()
        self.apply_filter()

    def set_manual_labels(self, report_or_labels):
        """Add persisted targets to the view without changing scientific data."""
        selected = self.selected_row()
        report = report_or_labels or {}
        labels = report.get('labels', report)
        self._manual_enabled = True
        self.headers = [name for name in self._source_headers if name not in self.MANUAL_HEADERS]
        position = self.headers.index('Object_ID')+1 if 'Object_ID' in self.headers else len(self.headers)
        self.headers[position:position] = ['Manual_Class', 'Manual_Class_ID', 'Reviewed']
        self.rows = []
        for source in self._source_rows:
            row = dict(source)
            row.update(Manual_Class_ID='', Manual_Class='', Reviewed=False)
            label = labels.get(self._object_key(row), {})
            row.update({name:label[name] for name in self.MANUAL_HEADERS if name in label})
            self.rows.append(row)
        self._refresh_classes()
        self.apply_filter()
        if selected:
            self.select_object(selected.get('Tile_Name'), selected.get('Object_ID'))

    apply_manual_labels = set_manual_labels

    def selected_row(self):
        selected = self.table.selectedItems()
        return selected[0].data(QtCore.Qt.ItemDataRole.UserRole) if selected else None

    def select_object(self, tile_name, object_id):
        key = str(tile_name) + '/' + str(object_id)
        for index, row in enumerate(self.visible_rows):
            if self._object_key(row) == key:
                self.table.selectRow(index)
                self.table.scrollToItem(self.table.item(index, 0))
                return True
        return False

    def navigate(self, direction):
        if direction not in ('previous', 'next', 'unlabeled'):
            raise ValueError('Unknown object navigation direction')
        if not self.visible_rows:
            return None
        current = self.selected_row()
        position = next((i for i, row in enumerate(self.visible_rows)
                         if current and self._object_key(row) == self._object_key(current)), -1)
        if direction == 'unlabeled':
            order = list(range(position+1, len(self.visible_rows))) + list(range(0, position+1))
            target = next((i for i in order if not self.visible_rows[i].get('Manual_Class')), None)
            if target is None:
                return None
        else:
            target = 0 if position < 0 else max(0, min(len(self.visible_rows)-1,
                                                     position + (-1 if direction == 'previous' else 1)))
        row = self.visible_rows[target]
        self.select_object(row.get('Tile_Name'), row.get('Object_ID'))
        return row

    def apply_filter(self, *_):
        selected = self.selected_row()
        chosen = self.class_filter.currentData()
        query = self.search.text().strip().casefold()
        def matches(row):
            if isinstance(chosen, (list, tuple)) and len(chosen) == 2 and chosen[0] == 'manual':
                if (row.get('Manual_Class') or None) != chosen[1]:
                    return False
            elif chosen is not None and row.get('Class_Name') != chosen:
                return False
            values = ' '.join(str(value) for value in row.values())
            values += ' ' + self._manual_name(row.get('Manual_Class')) + ' ' + self._text(str(row.get('Class_Name', '')))
            return not query or query in values.casefold()
        self.visible_rows = [row for row in self.rows if matches(row)]
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(self.headers))
        self.table.setHorizontalHeaderLabels([self._text(self.HEADER_LABELS.get(name, name)) for name in self.headers])
        self.table.setRowCount(len(self.visible_rows))
        for row_index, row in enumerate(self.visible_rows):
            for column, name in enumerate(self.headers):
                value = row.get(name, '')
                if name == 'Manual_Class':
                    value = self._manual_name(value)
                elif name == 'Reviewed':
                    value = self._text('Yes') if str(value).casefold() in ('true','1','yes') else ''
                elif name == 'Class_Name':
                    value = self._text(str(value))
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setData(QtCore.Qt.ItemDataRole.UserRole, row)
                if name == 'Manual_Class' and row.get('Manual_Class'):
                    item.setForeground(QtGui.QColor('#20a585'))
                    font=item.font(); font.setBold(True); item.setFont(font)
                self.table.setItem(row_index, column, item)
        self.table.resizeColumnsToContents()
        self.count.setText(self._text('Objects: {visible} / {total}', visible=len(self.visible_rows), total=len(self.rows)))
        if selected:
            self.select_object(selected.get('Tile_Name'), selected.get('Object_ID'))

    def _selection_changed(self):
        selected = self.selected_row()
        if selected is not None:
            self.row_selected.emit(selected)

    def export_filtered(self, filename):
        destination = Path(filename).resolve()
        if self.source_path:
            from .object_labels import validate_export_destination
            destination = validate_export_destination(
                dict(results_dir=str(Path(self.source_path).resolve().parent), last_csv=self.source_path),
                destination)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8-sig', newline='',
                                             prefix='.csv_export_', suffix='.tmp',
                                             dir=destination.parent, delete=False) as handle:
                temporary = Path(handle.name).resolve()
                if temporary.parent != destination.parent:
                    raise ValueError('CSV export must stay inside its selected destination directory')
                writer = csv.DictWriter(handle, fieldnames=self.headers)
                writer.writeheader()
                writer.writerows(self.visible_rows)
            os.replace(temporary, destination)
        finally:
            if temporary is not None and temporary.is_file():
                temporary.unlink()
        return len(self.visible_rows)
