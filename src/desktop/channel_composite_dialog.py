"""Choose TIFF channels, preview their colors and export the native-size blend."""

from pathlib import Path
from threading import Event

from src.channel_composite import composite
from .help import attach_help, image_help_button, install_image_help
from .i18n import register_translations, tr
from .image_controls import tool_icon
from .qt import QtCore, QtGui, QtWidgets, Signal
from .widgets import ImageViewer


_TEXT = {
    'Combine TIFF channels…': ('Объединить каналы TIFF…', 'שילוב ערוצי TIFF…'),
    'TIFF channel composite': ('Наложение каналов TIFF', 'תמונה משולבת מערוצי TIFF'),
    'Channel {index}': ('Канал {index}', 'ערוץ {index}'),
    'Channel color': ('Цвет канала', 'צבע הערוץ'),
    'Brightness gain (%)': ('Усиление яркости (%)', 'הגברת בהירות (%)'),
    'Opacity (%)': ('Непрозрачность (%)', 'אטימות (%)'),
    'Save full-resolution composite…': ('Сохранить наложение в исходном разрешении…', 'שמירת תמונה משולבת ברזולוציית המקור…'),
    'Additive RGB · {width} × {height} source px · preview step {step}': (
        'Сумма RGB · {width} × {height} исходных px · шаг предпросмотра {step}',
        'חיבור RGB · {width} × {height} פיקסלי מקור · צעד תצוגה {step}'),
    'Saving the full-resolution composite…': ('Сохраняется наложение в исходном разрешении…', 'התמונה המשולבת נשמרת ברזולוציית המקור…'),
    'Choose a different file from the source TIFF.': ('Выберите имя, отличное от исходного TIFF.', 'בחרו קובץ שונה מקובץ ה־TIFF המקורי.'),
    'Choose TIFF, PNG or JPEG.': ('Выберите TIFF, PNG или JPEG.', 'בחרו TIFF, PNG או JPEG.'),
    'Choose TIFF for images over 32 megapixels.': ('Для изображений больше 32 Мп выберите TIFF.', 'לתמונות מעל 32 מגה־פיקסל בחרו TIFF.'),
    'Select at least one channel.': ('Выберите хотя бы один канал.', 'בחרו לפחות ערוץ אחד.'),
    'TIFF cannot be mapped without decoding the entire series': (
        'Для чтения нужно декодировать слишком большую серию TIFF целиком. Сохраните её без сжатия.',
        'קריאה דורשת פענוח של סדרת TIFF גדולה מדי. שמרו אותה ללא דחיסה.'),
}
register_translations({key: value[0] for key, value in _TEXT.items()},
                      hebrew={key: value[1] for key, value in _TEXT.items()})

_FORMATS = {'TIFF (*.tif *.tiff)': '.tif', 'PNG (*.png)': '.png', 'JPEG (*.jpg *.jpeg)': '.jpg'}
_COLORS = ('#ff0000', '#00ff00', '#0000ff', '#00ffff', '#ff00ff', '#ffff00')
_POOL = QtCore.QThreadPool()
_POOL.setMaxThreadCount(1)


class _Task(QtCore.QRunnable):
    class Signals(QtCore.QObject):
        done = Signal(object, str)

    def __init__(self, filename, plane, layers, destination):
        super().__init__()
        self.args = filename, plane, layers
        self.destination = destination
        self.cancel = Event()
        self.signals = self.Signals()

    def run(self):
        try:
            result = None if self.cancel.is_set() else composite(
                *self.args, destination=self.destination, cancelled=self.cancel.is_set)
        except Exception as error:
            self.signals.done.emit(None, str(error))
        else:
            self.signals.done.emit(result, '')


class ChannelCompositeDialog(QtWidgets.QDialog):
    def __init__(self, parent, info, plane=0):
        super().__init__(parent)
        self.info = info
        self._task = None
        self._pending = False
        self._closing = False
        self._layers = []
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(tr('TIFF channel composite') + ' — ' + info['name'])
        self.resize(1120, 850)
        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        self.plane = QtWidgets.QSpinBox()
        self.plane.setRange(0, info['plane_count'] - 1)
        self.plane.setValue(plane)
        self.plane.setEnabled(info['plane_count'] > 1)
        header.addWidget(QtWidgets.QLabel(tr('TIFF slice / frame (0-based)')))
        header.addWidget(attach_help(self.plane, 'channel_composite'))
        header.addStretch()
        self.save = QtWidgets.QPushButton(tr('Save full-resolution composite…'))
        self.save.setIcon(tool_icon(self.save, 'save'))
        self.save.clicked.connect(self._save)
        header.addWidget(attach_help(self.save, 'channel_composite'))
        header.addWidget(image_help_button(self, 'channel_composite', parent.language))
        layout.addLayout(header)
        self.controls = QtWidgets.QScrollArea()
        self.controls.setWidgetResizable(True)
        self.controls.setMaximumHeight(255)
        grid = QtWidgets.QGridLayout()
        panel = QtWidgets.QWidget()
        panel.setLayout(grid)
        self.controls.setWidget(panel)
        for column, label in enumerate(('Source channel', 'Channel color', 'Brightness gain (%)', 'Opacity (%)')):
            grid.addWidget(QtWidgets.QLabel(tr(label)), 0, column)
        for index in range(info['channels']):
            toggle = QtWidgets.QCheckBox(tr('Channel {index}', index=index))
            toggle.setChecked(index < 3)
            swatch = QtWidgets.QPushButton()
            gain, opacity = QtWidgets.QSpinBox(), QtWidgets.QSpinBox()
            for spin, limit, label in ((gain, 1600, 'Brightness gain (%)'), (opacity, 100, 'Opacity (%)')):
                spin.setRange(0, limit)
                spin.setValue(100)
                spin.setSingleStep(5)
                spin.setSuffix('%')
                spin.setAccessibleName(tr(label) + ' · ' + toggle.text())
                spin.valueChanged.connect(self._schedule)
            self._layers.append((toggle, swatch, gain, opacity))
            self._set_color(index, QtGui.QColor(_COLORS[index % len(_COLORS)]))
            swatch.clicked.connect(lambda _, i=index: self._pick_color(i))
            toggle.toggled.connect(self._schedule)
            for column, widget in enumerate(self._layers[-1]):
                grid.addWidget(attach_help(widget, 'channel_composite'), index + 1, column)
        layout.addWidget(self.controls)
        self.viewer = ImageViewer(self, maximum=None)
        self.viewer._host_window = self
        self.viewer.image_save_button.hide()  # The dedicated export always uses native dimensions.
        self.viewer.levels_button.hide()  # The saved tones come from the per-channel controls.
        layout.addWidget(self.viewer, 1)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._timer = QtCore.QTimer(self, singleShot=True, interval=100)
        self._timer.timeout.connect(self._preview)
        self.plane.valueChanged.connect(self._schedule)
        self.finished.connect(self._close)
        install_image_help(self, 'channel_composite', parent.language)
        self._schedule()

    def _set_color(self, index, color):
        toggle, button, _, _ = self._layers[index]
        button.setProperty('channelColor', color)
        button.setText(color.name().upper())
        button.setAccessibleName(tr('Channel color') + ' · ' + toggle.text())
        foreground = '#000000' if color.lightness() > 130 else '#ffffff'
        button.setStyleSheet(f'background: {color.name()}; color: {foreground};')

    def _pick_color(self, index):
        color = QtWidgets.QColorDialog.getColor(self._layers[index][1].property('channelColor'), self, tr('Channel color'))
        if color.isValid():
            self._set_color(index, color)
            self._schedule()

    def _snapshot(self):
        return [(i, button.property('channelColor').getRgb()[:3], gain.value() / 100, opacity.value() / 100)
                for i, (toggle, button, gain, opacity) in enumerate(self._layers) if toggle.isChecked()]

    def _schedule(self, *_):
        self._pending = True
        self._timer.start()

    def _preview(self):
        if self._task is None:
            self._start()

    def _start(self, destination=None):
        self._pending = False
        self.save.setEnabled(False)
        if destination:
            self.controls.setEnabled(False)
            self.plane.setEnabled(False)
            self.status.setText(tr('Saving the full-resolution composite…'))
        task = self._task = _Task(self.info['path'], self.plane.value(), self._snapshot(), destination)
        task.signals.done.connect(self._done)
        _POOL.start(task)

    def _done(self, result, error):
        task, self._task = self._task, None
        if self._closing:
            return
        self.controls.setEnabled(True)
        self.plane.setEnabled(self.info['plane_count'] > 1)
        self.save.setEnabled(bool(self._snapshot()))
        if error:
            self.status.setText(tr('Could not save image: {message}' if task.destination else
                                   'Could not open image: {message}', message=tr(error)))
        elif task.destination:
            self.status.setText(tr('Image saved to {path}', path=str(result)))
        elif not self._pending:
            pixels, step = result
            h, w = pixels.shape[:2]
            frame = QtGui.QImage(pixels.tobytes(), w, h, w * 3, QtGui.QImage.Format.Format_RGB888).copy()
            if self.viewer._base_image is not None and self.viewer._base_image.size() == frame.size():
                self.viewer.replace_display_pixels(frame)
            else:
                self.viewer.set_image_frame(frame, tr('TIFF channel composite'),
                                            original_size=(self.info['width'], self.info['height']))
            self.status.setText(tr('Additive RGB · {width} × {height} source px · preview step {step}',
                                   width=self.info['width'], height=self.info['height'], step=step))
        if self._pending:
            self._timer.start()

    def _save(self):
        if self._task is not None or not self._snapshot():
            return
        self._timer.stop()
        path, selected = QtWidgets.QFileDialog.getSaveFileName(
            self, tr('Save full-resolution composite…'), Path(self.info['path']).stem + '_composite', ';;'.join(_FORMATS))
        if not path:
            if self._pending:
                self._timer.start()
            return
        destination = Path(path)
        if not destination.suffix:
            destination = destination.with_suffix(_FORMATS.get(selected, '.tif'))
        if destination != Path(path) and destination.exists() and QtWidgets.QMessageBox.question(
                self, self.windowTitle(), tr('Replace the existing file {path}?', path=str(destination))
        ) != QtWidgets.QMessageBox.StandardButton.Yes:
            if self._pending:
                self._timer.start()
            return
        pending = self._pending
        self._start(destination)
        self._pending = pending

    def _close(self, *_):
        self._closing = True
        self._timer.stop()
        if self._task:
            self._task.cancel.set()
