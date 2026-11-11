"""ImageJ-style display windows on the preview's unadjusted samples."""

import math

import numpy as np

from .help import attach_help, image_help_button, install_image_help
from .i18n import register_translations
from .qt import QtCore, QtGui, QtWidgets, show_centered_window


_LABELS = {
    'Brightness and contrast': ('Яркость и контраст', 'בהירות וניגודיות'),
    'Brightness': ('Яркость', 'בהירות'),
    'Contrast': ('Контраст', 'ניגודיות'),
    'Black level': ('Уровень чёрного', 'רמת שחור'),
    'White level': ('Уровень белого', 'רמת לבן'),
    'Reset display levels': ('Сбросить уровни отображения', 'איפוס רמות תצוגה'),
    'Display adjustment · {bits}-bit input': ('Настройка просмотра · вход {bits} бит', 'התאמת תצוגה · קלט {bits} סיביות'),
}
register_translations({key: value[0] for key, value in _LABELS.items()},
                      hebrew={key: value[1] for key, value in _LABELS.items()})


def grayscale_image(pixels):
    pixels = np.ascontiguousarray(pixels)
    height, width = pixels.shape
    formats = QtGui.QImage.Format
    image_format = formats.Format_Grayscale16 if pixels.dtype == np.uint16 else formats.Format_Grayscale8
    return QtGui.QImage(pixels.tobytes(), width, height, pixels.strides[0], image_format).copy()


def image_samples(image):
    """View QImage rows including stride; the QImage must outlive the array."""
    formats = QtGui.QImage.Format
    dtype = np.uint16 if image.format() == formats.Format_Grayscale16 else np.uint8
    channels = {formats.Format_RGB888: 3, formats.Format_RGBA8888: 4}.get(image.format(), 1)
    bits = image.constBits()
    if hasattr(bits, 'setsize'):
        bits.setsize(image.sizeInBytes())
    rows = np.frombuffer(bits, dtype=dtype).reshape(image.height(), -1)
    shape = (image.height(), image.width(), channels) if channels > 1 else (image.height(), image.width())
    return rows[:, :image.width() * channels].reshape(shape)


def display_image(image, levels=None):
    """Apply a clipped linear lookup table while leaving the source buffer intact."""
    formats = QtGui.QImage.Format
    sixteen = image.format() == formats.Format_Grayscale16
    if levels is None:
        return grayscale_image((image_samples(image) >> 8).astype(np.uint8)) if sixteen else image
    if image.format() not in (formats.Format_Grayscale8, formats.Format_Grayscale16, formats.Format_RGB888):
        image = image.convertToFormat(formats.Format_RGB888)
    maximum = 65535 if sixteen else 255
    black, white = levels
    scaled = (np.arange(maximum + 1) - black) * 255 / (white - black)
    lut = np.rint(np.clip(scaled, 0, 255)).astype(np.uint8)
    adjusted = lut[image_samples(image)]
    if adjusted.ndim == 2:
        return grayscale_image(adjusted)
    height, width = adjusted.shape[:2]
    return QtGui.QImage(adjusted.tobytes(), width, height, width * 3, formats.Format_RGB888).copy()


class ImageLevelsDialog(QtWidgets.QDialog):
    def __init__(self, viewer, parent):
        super().__init__(parent)
        self.viewer = viewer
        self.maximum = 65535 if viewer._base_image.format() == QtGui.QImage.Format.Format_Grayscale16 else 255
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(viewer._text('Brightness and contrast'))
        self.setLayoutDirection(parent.layoutDirection())
        form = QtWidgets.QFormLayout(self)
        form.addRow(QtWidgets.QLabel(viewer._text('Display adjustment · {bits}-bit input',
                                                  bits=16 if self.maximum > 255 else 8)))
        self.brightness = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.contrast = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.brightness.setRange(-100, 100)
        self.contrast.setRange(-20, 100)
        for slider in (self.brightness, self.contrast):
            slider.setMinimumWidth(220)
            slider.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        self.black, self.white = QtWidgets.QSpinBox(), QtWidgets.QSpinBox()
        for field in (self.black, self.white):
            field.setRange(-2 * self.maximum, 3 * self.maximum)
        for label, field in (('Brightness', self.brightness), ('Contrast', self.contrast),
                             ('Black level', self.black), ('White level', self.white)):
            form.addRow(viewer._text(label), attach_help(field, 'image_levels'))
        self.reset = QtWidgets.QPushButton(viewer._text('Reset display levels'))
        self.reset.clicked.connect(lambda: self._set(0, self.maximum))
        actions = QtWidgets.QHBoxLayout()
        actions.addWidget(self.reset)
        actions.addWidget(image_help_button(self, 'image_levels', viewer.language))
        form.addRow(actions)
        install_image_help(self, 'image_levels', viewer.language)
        self._timer = QtCore.QTimer(self, singleShot=True, interval=35)
        self._timer.timeout.connect(self._apply)
        self.brightness.valueChanged.connect(self._shift)
        self.contrast.valueChanged.connect(self._stretch)
        self.black.valueChanged.connect(lambda value: self._set(value, max(value + 1, self.white.value())))
        self.white.valueChanged.connect(lambda value: self._set(min(value - 1, self.black.value()), value))
        self._set(*(viewer._levels or (0, self.maximum)))
        self.finished.connect(lambda *_: self._apply())
        self.resize(410, 255)

    def open_window(self):
        show_centered_window(self)

    def _set(self, black, white):
        black = max(-2 * self.maximum, min(3 * self.maximum - 1, black))
        white = max(black + 1, min(3 * self.maximum, white))
        midpoint = (black + white) / 2
        fields = ((self.black, black), (self.white, white),
                  (self.brightness, round(100 - 200 * midpoint / self.maximum)),
                  (self.contrast, round(20 * math.log2(self.maximum / (white - black)))))
        for field, value in fields:
            with QtCore.QSignalBlocker(field):
                field.setValue(value)
        self._timer.start()

    def _shift(self, value):
        span = self.white.value() - self.black.value()
        center = self.maximum * (100 - value) / 200
        black = round(center - span / 2)
        self._set(black, black + span)

    def _stretch(self, value):
        center = (self.black.value() + self.white.value()) / 2
        span = max(1, round(self.maximum * 2 ** (-value / 20)))
        black = round(center - span / 2)
        self._set(black, black + span)

    def _apply(self):
        self._timer.stop()
        levels = self.black.value(), self.white.value()
        self.viewer.set_display_levels(None if levels == (0, self.maximum) else levels)
