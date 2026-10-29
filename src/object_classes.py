"""Shared semantic classes for object review and YOLO segmentation.

IDs 0–4 preserve the project's original YOLO numbering. Display names and
CSV keys can differ from the original names without changing their meaning.
Catalog 2 adds adhered objects and aligns manual IDs with the YOLO IDs.
"""

CLASS_CATALOG_VERSION = 2

OBJECT_CLASS_CATALOG = (
    dict(id=0, key='particle', label_en='Particle', label_ru='Частица',
         source_label='Sphere'),
    dict(id=1, key='fiber', label_en='Fiber', label_ru='Волокно',
         source_label='Curve'),
    dict(id=2, key='self_crossed_tube', label_en='Self-crossed tube',
         label_ru='Пересечение трубочки самой собой', source_label='Self-intersecting curve'),
    dict(id=3, key='crossed_tubes', label_en='Crossed tubes',
         label_ru='Перекрещенные трубочки', source_label='Intersecting curves'),
    dict(id=4, key='agglomeration', label_en='Agglomeration', label_ru='Агломерация',
         source_label='Agglomeration'),
    dict(id=5, key='adhered_objects', label_en='Adhered objects',
         label_ru='Несколько слипшихся объектов', source_label='Adhered objects'),
)
