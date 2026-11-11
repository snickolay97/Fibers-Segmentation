"""Display-only status and normalized YOLO polygons for both tile viewers."""

from pathlib import Path

from src.yolo_polygons import read_yolo_polygons
from .i18n import register_translations, tr
from .qt import QtCore, QtWidgets


_TEXT = {
    'No YOLO annotation file for this tile. Showing the model image.': (
        'Для этого тайла нет файла разметки YOLO. Показано модельное изображение.',
        'אין קובץ תיוג YOLO לאריח זה. מוצגת תמונת המודל.'),
    'Empty YOLO TXT. No annotated objects on this tile.': (
        'Пустой TXT разметки YOLO. На тайле нет размеченных объектов.',
        'קובץ TXT של YOLO ריק. אין עצמים מתויגים באריח זה.'),
    'Imported YOLO outlines: {count}': (
        'Импортированные контуры YOLO: {count}', 'מתארי YOLO שיובאו: {count}'),
    'Cannot display YOLO annotations: {error}': (
        'Не удалось показать разметку YOLO: {error}', 'לא ניתן להציג את תיוגי YOLO: {error}'),
}
register_translations({key: values[0] for key, values in _TEXT.items()},
                      hebrew={key: values[1] for key, values in _TEXT.items()})


def add_yolo_status(viewer):
    status = QtWidgets.QLabel()
    status.setWordWrap(True)
    status.setTextFormat(QtCore.Qt.TextFormat.PlainText)
    status.hide()
    viewer.layout().insertWidget(0, status)
    return status


def show_yolo_polygons(viewer, status, dataset, record):
    folder = dataset.get('labels_dir')
    path = Path(folder) / Path(record['filename']).with_suffix('.txt').name if folder else None
    polygons = []
    try:
        if path is None or not path.is_file():
            caption = tr('No YOLO annotation file for this tile. Showing the model image.')
        else:
            polygons = [dict(class_id=class_id, points=points.tolist())
                        for class_id, points in read_yolo_polygons(path)]
            caption = (tr('Imported YOLO outlines: {count}', count=len(polygons)) if polygons
                       else tr('Empty YOLO TXT. No annotated objects on this tile.'))
    except (OSError, ValueError) as error:
        caption = tr('Cannot display YOLO annotations: {error}', error=str(error))
    status.setText(caption)
    status.show()
    viewer.set_polygons(polygons)
