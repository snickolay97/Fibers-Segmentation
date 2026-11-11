"""Export a separate image file from saved pixels or a display frame."""

import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
from PIL import Image

from .i18n import register_translations
from .image_levels import image_samples
from .qt import QtCore, QtGui, QtWidgets, Signal


_LABELS = {
    'Save image…': ('Сохранить изображение…', 'שמירת תמונה…'),
    'Save displayed image…': ('Сохранить видимое изображение…', 'שמירת התמונה המוצגת…'),
    'Export saved file…': ('Экспортировать сохранённый файл…', 'ייצוא קובץ שמור…'),
    'Select a different file for the export.': ('Выберите другой файл для экспорта.', 'בחרו קובץ אחר לייצוא.'),
    'Replace the existing file {path}?': ('Заменить существующий файл {path}?', 'להחליף את הקובץ הקיים {path}?'),
    'Image files': ('Изображения', 'קובצי תמונה'),
    'All files': ('Все файлы', 'כל הקבצים'),
    'Could not save image: {message}': ('Не удалось сохранить изображение: {message}', 'לא ניתן לשמור את התמונה: {message}'),
    'This PNG conversion supports grayscale samples from 0 to 65535.': (
        'Преобразование в PNG поддерживает серые значения от 0 до 65535.', 'המרה ל־PNG תומכת בגוני אפור בין 0 ל־65535.'),
    'Image saved to {path}': ('Изображение сохранено в {path}', 'התמונה נשמרה בנתיב {path}'),
}
register_translations({key: value[0] for key, value in _LABELS.items()},
                      hebrew={key: value[1] for key, value in _LABELS.items()})

_FORMATS = {'TIFF (*.tif *.tiff)': ('.tif', 'TIFF'), 'PNG (*.png)': ('.png', 'PNG'),
            'JPEG (*.jpg *.jpeg)': ('.jpg', 'JPEG')}
_SUFFIXES = {'.tif': 'TIFF', '.tiff': 'TIFF', '.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG'}


def write_image_copy(destination, *, source=None, frame=None, translate=lambda message: message):
    """Write atomically. For a same-format file export preserve all original bytes."""
    destination = Path(destination)
    format_name = _SUFFIXES[destination.suffix.lower()]
    source = Path(source) if source else None
    if source is not None and (destination.resolve() == source.resolve()
            or (destination.exists() and destination.samefile(source))):
        raise ValueError(translate('Select a different file for the export.'))
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=destination.suffix, delete=False) as temporary:
        staged = Path(temporary.name)
    try:
        if source is not None:
            with Image.open(source) as image:
                if image.format == format_name:
                    shutil.copyfile(source, staged)
                else:
                    _save_frame(image, staged, format_name, translate)
        else:
            formats = QtGui.QImage.Format
            if frame.format() not in (formats.Format_Grayscale8, formats.Format_Grayscale16,
                                      formats.Format_RGB888, formats.Format_RGBA8888):
                frame = frame.convertToFormat(formats.Format_RGBA8888)
            _save_frame(Image.fromarray(image_samples(frame)), staged, format_name, translate)
        os.replace(staged, destination)
    finally:
        staged.unlink(missing_ok=True)


def _save_frame(image, staged, format_name, translate):
    if image.mode.startswith('I;16') or image.mode in ('I', 'F'):
        if format_name != 'TIFF':
            pixels = np.asarray(image)
            low, high = float(pixels.min()), float(pixels.max())
            if format_name == 'PNG' and (image.mode == 'F' or not 0 <= low <= high <= 65535):
                raise ValueError(translate('This PNG conversion supports grayscale samples from 0 to 65535.'))
            if format_name == 'PNG':
                image = Image.fromarray(pixels.astype(np.uint16))
            elif not image.mode.startswith('I;16') and high <= 255:
                image = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))
            else:
                image = Image.fromarray((np.clip(pixels, 0, 65535).astype(np.uint16) >> 8).astype(np.uint8))
    if format_name == 'JPEG' and image.mode not in ('L', 'RGB'):
        image = image.convert('RGB')
    if format_name == 'PNG' and image.mode in ('CMYK', 'YCbCr', 'LAB', 'HSV'):
        image = image.convert('RGB')
    image.save(staged, format=format_name, **({'quality': 95} if format_name == 'JPEG' else {}))


class _ExportTask(QtCore.QRunnable):
    class Signals(QtCore.QObject):
        done = Signal(str)

    def __init__(self, destination, source, frame, translate):
        super().__init__()
        self.signals = self.Signals()
        self.destination, self.source, self.frame, self.translate = destination, source, frame, translate

    def run(self):
        try:
            write_image_copy(self.destination, source=self.source, frame=self.frame, translate=self.translate)
        except Exception as error:
            self.signals.done.emit(str(error))
        else:
            self.signals.done.emit('')


def export_from_viewer(viewer, parent, *, saved_file):
    from .i18n import tr
    from .widgets import image_pool

    title = viewer._text('Export saved file…' if saved_file else 'Save displayed image…')
    stem = Path(viewer.filename).stem or 'image'
    source = viewer._export_source if saved_file else None
    protected = tuple(Path(path).resolve() for path in (viewer.filename, viewer._export_source) if path)
    frame = None if source else viewer.export_frame()
    if not source and frame is None:
        return
    filename, selected = QtWidgets.QFileDialog.getSaveFileName(
        parent, title, f'{stem}_export', ';;'.join(_FORMATS), 'PNG (*.png)')
    if not filename:
        return
    destination = Path(filename)
    if destination.suffix.lower() not in _SUFFIXES:
        destination = destination.with_name(destination.name + _FORMATS[selected or 'PNG (*.png)'][0])
    # The native dialog checks its chosen name. Check the actual path as well
    # when we appended an extension to the user's input.
    if destination != Path(filename) and destination.exists():
        answer = QtWidgets.QMessageBox.question(parent, title, viewer._text(
            'Replace the existing file {path}?', path=str(destination)))
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
    if destination.resolve() in protected:
        QtWidgets.QMessageBox.warning(parent, title, viewer._text('Select a different file for the export.'))
        return
    language = viewer.language
    task = _ExportTask(destination, source, frame, lambda key: tr(key, language=language))
    # Keep the completion connected to a living QObject when the dialog closes.
    task.signals.done.connect(viewer.image_export_finished)
    viewer._exports[task.signals] = (task, destination)
    image_pool().start(task)
