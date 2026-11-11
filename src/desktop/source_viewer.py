"""Browse a TIFF overview and read source pixels only for the selected region."""

from pathlib import Path
import math

from src.image_io import read_tiff_region, read_tiff_view
from .help import attach_help, image_help_button, install_image_help
from .i18n import register_translations, tr
from .image_controls import size_action, tool_icon
from .image_levels import display_image, grayscale_image
from .qt import QtCore, QtGui, QtWidgets, Signal
from .widgets import ImageViewer, image_pool


_TEXT = {
    'View whole TIFF…': ('Просмотр всего TIFF…', 'תצוגת TIFF שלם…'),
    'Open TIFF file in Windows': ('Открыть файл TIFF в Windows', 'פתיחת קובץ TIFF ב־Windows'),
    'Overview · {width} × {height} source px · channel {channel}, plane {plane}': (
        'Обзор · {width} × {height} исходных px · канал {channel}, плоскость {plane}',
        'סקירה · {width} × {height} פיקסלי מקור · ערוץ {channel}, מישור {plane}'),
    'Click the overview to inspect the source pixels at that location.': (
        'Нажмите на обзор, чтобы увидеть исходные пиксели выбранного участка.',
        'לחצו על הסקירה כדי לראות את פיקסלי המקור באזור שנבחר.'),
    'Navigation overview · reduced': ('Карта навигации · уменьшена', 'מפת ניווט · מוקטנת'),
    'Drag to move through the TIFF. Use the wheel to zoom or click the navigation overview to jump.': (
        'Перетаскивайте изображение для перемещения по TIFF. Используйте колесо для масштаба или щёлкните по карте навигации.',
        'גררו לניווט ב־TIFF. השתמשו בגלגלת לזום או לחצו על מפת הניווט למעבר מהיר.'),
    'Loading original pixels…': ('Загружаются исходные пиксели…', 'פיקסלי המקור נטענים…'),
    'Reduced view · zoom in or press 1:1 for original pixels.': (
        'Уменьшенный вид · приблизьте изображение или нажмите 1:1 для просмотра исходных пикселей.',
        'תצוגה מוקטנת · הגדילו או לחצו 1:1 להצגת פיקסלי המקור.'),
    'Original pixels · x={x}, y={y} · {width} × {height} px loaded': (
        'Исходные пиксели · x={x}, y={y} · загружено {width} × {height} px',
        'פיקסלי מקור · x={x}, y={y} · נטענו {width} × {height} פיקסלים'),
    'Source region · x={x}, y={y} · {width} × {height} px': (
        'Участок исходника · x={x}, y={y} · {width} × {height} px',
        'אזור מקור · x={x}, y={y} · {width} × {height} פיקסלים'),
    'This TIFF requires decoding a large series to read a region. Open the file in Windows.': (
        'Для чтения участка этого TIFF нужно декодировать большую серию целиком. Откройте файл в Windows.',
        'קריאת אזור ב־TIFF הזה דורשת פענוח של סדרה גדולה שלמה. פתחו את הקובץ ב־Windows.'),
}
register_translations({key: pair[0] for key, pair in _TEXT.items()},
                      hebrew={key: pair[1] for key, pair in _TEXT.items()})


class _Signals(QtCore.QObject):
    ready = Signal(object)
    failed = Signal(str)


class ReadTiffViewTask(QtCore.QRunnable):
    def __init__(self, filename, channel, plane, center=None):
        super().__init__()
        self.args = filename, channel, plane, 2000 if center is None else 1200, center
        self.signals = _Signals()

    def run(self):
        try:
            view = read_tiff_view(*self.args, preserve_uint16=True)
        except BufferError:
            self.signals.failed.emit(tr('This TIFF requires decoding a large series to read a region. Open the file in Windows.'))
        except (OSError, ValueError, RuntimeError) as error:
            self.signals.failed.emit(str(error))
        else:
            self.signals.ready.emit(view)


class _RegionTask(QtCore.QRunnable):
    def __init__(self, filename, channel, plane, bounds):
        super().__init__()
        self.args = filename, channel, plane, bounds
        self.signals = _Signals()

    def run(self):
        try:
            pixels = read_tiff_region(*self.args)
        except (OSError, ValueError, RuntimeError, BufferError) as error:
            self.signals.failed.emit(str(error))
        else:
            self.signals.ready.emit(pixels)


class _TiffImageViewer(ImageViewer):
    viewport_changed = Signal()

    def export_frame(self):
        native = self.native_export()
        return native if native is not None else super().export_frame()

    def comparison_frame(self):
        native = self.native_export()
        if native is not None:
            return native, (native.width(), native.height())
        return super().comparison_frame()

    def _zoom_view(self, view, factor, anchor=None):
        super()._zoom_view(view, factor, anchor)
        self.viewport_changed.emit()

    def _apply_auto_fit(self):
        super()._apply_auto_fit()
        self.viewport_changed.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.viewport_changed.emit()


class SourceViewer(QtWidgets.QDialog):
    def __init__(self, parent, filename, channel, plane, *, pixel_um=None, title=None, binary=False):
        super().__init__(parent)
        self.filename, self.channel, self.plane = Path(filename), channel, plane
        self.pixel_um = pixel_um
        self._task = None
        self._step = 0
        self._closing = False
        self._patch = self._patch_image = self._patch_bounds = None
        self._wanted = self._loading_bounds = None
        self._export_bounds = None
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowFlag(QtCore.Qt.WindowType.WindowMinMaxButtonsHint)
        self.setWindowTitle((title or tr('View whole TIFF…')) + ' — ' + self.filename.name)
        self.resize(1200, 820)
        layout = QtWidgets.QVBoxLayout(self)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        split = QtWidgets.QSplitter()
        self.overview = ImageViewer()
        self.overview._actions.hide()
        self.detail = _TiffImageViewer(maximum=None)
        self.detail._host_window = self
        self.detail.resolution_action = self._actual_size
        self.detail.native_export = self._export_region
        self._viewport_timer = QtCore.QTimer(self, singleShot=True, interval=35)
        self._viewport_timer.timeout.connect(self._load_visible_region)
        self.detail.viewport_changed.connect(self._queue_region)
        for scrollbar in (self.detail.view.horizontalScrollBar(), self.detail.view.verticalScrollBar()):
            scrollbar.valueChanged.connect(self._queue_region)
        self.detail.display_levels_changed.connect(self._update_patch)
        if binary:
            for viewer in (self.overview, self.detail):
                viewer.view.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, False)
        split.addWidget(self.overview)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([260, 920])
        layout.addWidget(split, 1)
        self.overview.clicked.connect(self._select_region)
        actions = QtWidgets.QHBoxLayout()
        external = QtWidgets.QPushButton(tr('Open TIFF file in Windows'))
        external.clicked.connect(self._open_file)
        actions.addWidget(external)
        actions.addWidget(image_help_button(self, 'source_viewer', self.overview.language))
        actions.addStretch()
        close = QtWidgets.QPushButton(tr('Close'))
        close.clicked.connect(self.reject)
        self._action_buttons = (external, close)
        for button, icon in zip(self._action_buttons, ('open', 'close')):
            button.setIcon(tool_icon(button, icon))
            button.setAutoDefault(False)
        actions.addWidget(close)
        layout.addLayout(actions)
        attach_help(self, 'source_viewer')
        install_image_help(self, 'source_viewer', self.overview.language)
        self.finished.connect(self._clear)
        self._read(None)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for button in getattr(self, '_action_buttons', ()):
            size_action(button, self.width())

    def _read(self, center):
        self.status.setText(tr('Loading preview…'))
        self._task = ReadTiffViewTask(self.filename, self.channel, self.plane, center)
        self._task.signals.ready.connect(self._show_view)
        self._task.signals.failed.connect(self._show_error)
        image_pool().start(self._task)

    def _show_view(self, result):
        self._task = None
        if self._closing:
            return
        pixels, location, step = result
        self._step = step
        width, height = self._source_size = location
        self.overview.set_grayscale_pixels(pixels, tr('Navigation overview · reduced'))
        self.detail.set_image_frame(grayscale_image(pixels),
            tr('Drag to move through the TIFF. Use the wheel to zoom or click the navigation overview to jump.'),
            ruler_scale=(1, 1, self.pixel_um), original_size=(width, height))
        self._actual_size(center=True)

    def _source_factors(self):
        width, height = self._source_size
        rect = self.detail._pixmap_item.boundingRect()
        return width / rect.width(), height / rect.height()

    def _actual_size(self, center=False):
        view = self.detail.view
        item = self.detail._pixmap_item
        if item is None:
            return
        anchor = item.boundingRect().center() if center else view.mapToScene(view.viewport().rect().center())
        sx, sy = self._source_factors()
        dpr = view.devicePixelRatioF()
        self.detail._keep_manual_transform()
        self.detail._zoom_ceiling = 40 * max(sx, sy)
        view.setTransform(QtGui.QTransform.fromScale(sx / dpr, sy / dpr))
        view.centerOn(anchor)
        item.hide()
        self._export_bounds = None
        self._enable_image_actions(False)
        self._queue_region()

    def _queue_region(self, *_):
        if not self._closing and self._step and self.detail._pixmap_item is not None:
            self._viewport_timer.start()

    def _load_visible_region(self):
        if self._closing or self.detail._pixmap_item is None:
            return
        view = self.detail.view
        sx, sy = self._source_factors()
        width, height = self._source_size
        scene = view.mapToScene(view.viewport().rect()).boundingRect()
        x0, y0 = max(0, math.floor(scene.left() * sx)), max(0, math.floor(scene.top() * sy))
        x1, y1 = min(width, math.ceil(scene.right() * sx)), min(height, math.ceil(scene.bottom() * sy))
        if x1 <= x0 or y1 <= y0:
            return
        self.overview.set_polygons([dict(points=[(x0/width, y0/height), (x1/width, y0/height),
                                                 (x1/width, y1/height), (x0/width, y1/height)])])
        # Work in physical display pixels. At 1:1 each source sample has its
        # own display pixel even when Windows applies a per-monitor DPI scale.
        scale = view.devicePixelRatioF() * min(view.transform().m11() / sx, view.transform().m22() / sy)
        margin = 48
        bounds = max(0, x0-margin), max(0, y0-margin), min(width, x1+margin), min(height, y1+margin)
        screen = view.viewport().size() * view.devicePixelRatioF()
        area_limit = max(20_000_000, (screen.width() + 2*margin) * (screen.height() + 2*margin))
        self._export_bounds = None
        if scale < .48 or (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]) > area_limit:
            self._wanted = None
            self.detail._pixmap_item.show()
            if self._patch:
                self._patch.hide()
            self._enable_image_actions(True)
            self.status.setText(tr('Reduced view · zoom in or press 1:1 for original pixels.'))
            return
        self.detail._pixmap_item.hide()
        if self._patch_bounds:
            a, b, c, d = self._patch_bounds
            if a <= x0 and b <= y0 and c >= x1 and d >= y1:
                self._wanted = self._patch_bounds
                self._patch.show()
                self._export_bounds = x0, y0, x1, y1
                self._enable_image_actions(True)
                self._describe_patch()
                return
        self._wanted = bounds
        self._enable_image_actions(False)
        # Keep the currently loaded pixels visible while the next region loads.
        if self._patch:
            self._patch.show()
        self.status.setText(tr('Loading original pixels…'))
        if self._task is None:
            self._wanted = self._loading_bounds = bounds
            self._task = _RegionTask(self.filename, self.channel, self.plane, bounds)
            self._task.signals.ready.connect(self._show_patch)
            self._task.signals.failed.connect(self._region_error)
            image_pool().start(self._task)

    def _show_patch(self, pixels):
        bounds, self._loading_bounds = self._loading_bounds, None
        self._task = None
        if self._closing or self._wanted is None:
            return
        self._patch_bounds = bounds
        self._patch_image = grayscale_image(pixels)
        if self._patch is None:
            self._patch = self.detail.scene.addPixmap(QtGui.QPixmap())
            self._patch.setZValue(.25)
        sx, sy = self._source_factors()
        self._patch.setTransform(QtGui.QTransform.fromScale(1 / sx, 1 / sy))
        self._patch.setPos(bounds[0] / sx, bounds[1] / sy)
        self._update_patch()
        self._load_visible_region()

    def _update_patch(self, *_):
        if self._patch is not None:
            self._patch.setPixmap(QtGui.QPixmap.fromImage(display_image(self._patch_image, self.detail._levels)))

    def _describe_patch(self):
        x, y, right, bottom = self._patch_bounds
        self.status.setText(tr('Original pixels · x={x}, y={y} · {width} × {height} px loaded',
                               x=x, y=y, width=right-x, height=bottom-y))

    def _export_region(self):
        if self._export_bounds is None:
            return None
        x0, y0, x1, y1 = self._export_bounds
        sx, sy = self._source_factors()
        width, height = x1-x0, y1-y0
        scene_rect = QtCore.QRectF(x0/sx, y0/sy, width/sx, height/sy)
        return self.detail.render_image_layers(QtCore.QSize(width, height), bounds=scene_rect)

    def _enable_image_actions(self, enabled):
        self.detail.image_save_button.setEnabled(enabled)
        self.detail.compare_file_button.setEnabled(enabled)

    def _region_error(self, error):
        self._loading_bounds = None
        self._show_error(error)
        if not self._closing:
            self.detail._pixmap_item.show()
            if self._patch:
                self._patch.hide()
            self._enable_image_actions(True)

    def _show_error(self, message):
        self._task = None
        if not self._closing:
            self.status.setText(message)

    def _clear(self, _result):
        self._closing = True
        self._viewport_timer.stop()
        self._patch = None
        self.overview.clear()
        self.detail.clear()

    def _select_region(self, x, y):
        if self._step and self.detail._pixmap_item is not None:
            sx, _ = self._source_factors()
            view = self.detail.view
            if view.transform().m11() * view.devicePixelRatioF() / sx < .48:
                self._actual_size()
            self.detail._keep_manual_transform()
            self.detail.view.centerOn(x, y)
            self._queue_region()

    def _open_file(self):
        if not QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.filename.resolve()))):
            self.status.setText(tr('Could not open the original file in the system image viewer.'))
