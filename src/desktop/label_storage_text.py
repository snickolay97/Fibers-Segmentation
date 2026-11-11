"""Messages for durable manual targets and explicit compatibility exports."""
from .i18n import register_translations


TEXT = {
    'Manual label database operation failed: {error}': (
        'Не удалось выполнить операцию с базой ручных меток. Проверьте её доступность; сохраняйте файл для восстановления: {error}',
        'פעולת מסד התוויות הידניות נכשלה. בדקו את זמינותו ושמרו את הקובץ לשחזור: {error}'),
    'Export label snapshot (JSON)…': ('Экспорт снимка меток (JSON)…', 'ייצוא תמונת מצב של תוויות (JSON)…'),
    'Manual label snapshot saved: {path}': ('Снимок меток сохранён: {path}', 'תמונת מצב התוויות נשמרה: {path}'),
    'Manual labels changed while being read. Reload the measurement.': (
        'Ручные метки изменились во время чтения. Заново откройте измерение.',
        'התוויות הידניות השתנו בזמן הקריאה. פתחו מחדש את המדידה.'),
    'Measurement CSV changed while being read. Reload measurements.': (
        'CSV измерений изменился во время чтения. Заново откройте измерения.',
        'קובץ CSV של המדידות השתנה בזמן הקריאה. טענו את המדידות מחדש.'),
    'The manual-label database is missing. Restore it from a full project backup.': (
        'Отсутствует база ручных меток. Восстановите её из полной резервной копии проекта.',
        'מסד התוויות הידניות חסר. שחזרו אותו מגיבוי מלא של הפרויקט.'),
    'The manual-label database cannot be read. Restore it from a full project backup.': (
        'База ручных меток не читается. Восстановите её из полной резервной копии проекта.',
        'לא ניתן לקרוא את מסד התוויות הידניות. שחזרו אותו מגיבוי מלא של הפרויקט.'),
    'The legacy label JSON changed after conversion. Resolve the two copies before editing.': (
        'Старый JSON меток изменился после переноса в базу. Сначала согласуйте две версии разметки.',
        'קובץ JSON הישן השתנה לאחר ההמרה. יש ליישב את שתי גרסאות התיוג לפני עריכה.'),
}
register_translations({key: value[0] for key,value in TEXT.items()},
                      hebrew={key: value[1] for key,value in TEXT.items()})
