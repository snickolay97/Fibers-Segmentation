"""Equivalent instructions for reviewing masks, union corrections and analysis."""

SEGMENT = (
    'In Segmentation, choose a tile directly in the preview. Native and Model show its images; Objects shows exact measured masks with object IDs; YOLO polygons shows the imported search regions. Run measurement first. It returns to Segmentation so you can inspect how each tile became objects. Open object labeling continues to the manual class gallery.',
    'В «Сегментации» выберите тайл прямо в панели просмотра. Native и «Модель» показывают изображения, «Объекты» — точные измеренные маски с номерами, «Полигоны YOLO» — импортированные области поиска. Сначала запустите измерение. После расчёта откроется «Сегментация» для проверки разделения тайла на объекты. Кнопка «Открыть разметку объектов» переводит к назначению классов.',
    'בפילוח בחרו אריח ישירות בחלונית התצוגה. מקור ומודל מציגים את התמונות; אובייקטים מציג מסכות מדידה מדויקות עם מספרים; מצולעי YOLO מציג את אזורי החיפוש שיובאו. הפעילו מדידה תחילה. לאחר החישוב נפתח שוב הפילוח לבדיקת חלוקת האריח לאובייקטים. פתיחת תיוג אובייקטים מעבירה לגלריה לשיוך סוגים.'
)
LABELING = (
    'On Object labeling, inspect the saved object crops and use the six type buttons or keys 1–6. Open the object’s tile to inspect its exact highlighted mask. Model training is the next page. The last Results page contains charts, the feature table, and CSV, Excel and ML exports.',
    'В «Разметке объектов» просмотрите сохранённые фрагменты и назначьте тип одной из шести кнопок или клавишей 1–6. Откройте тайл объекта для проверки точной подсвеченной маски. Далее находится «Обучение модели». Последняя страница «Результаты» содержит графики, таблицу признаков и экспорт CSV, Excel и набора для ML.',
    'בתיוג אובייקטים בדקו את חיתוכי האובייקטים השמורים ושייכו סוג באחד מששת הכפתורים או במקשים 1–6. פתחו את אריח האובייקט לבדיקת המסכה המדויקת המודגשת. אימון מודל הוא הדף הבא. הדף האחרון, תוצאות, מכיל תרשימים, טבלת תכונות וייצוא CSV, Excel וחבילת ML.'
)
FINAL = (
    'On the last Results page, choose Charts or Feature table. Charts use all current measured objects of the selected dataset, including unclassified objects. Export visible rows follows this page’s own table filters; Export full table and Excel export all current rows. The ML bundle includes only objects with reviewed manual types.',
    'На последней странице «Результаты» выберите «Графики» или «Таблица признаков». Графики используют все актуальные измеренные объекты выбранного набора, включая объекты без класса. Экспорт видимых строк учитывает фильтры таблицы этой страницы; вся таблица и Excel содержат все актуальные строки. Набор для ML включает только объекты с проверенными ручными типами.',
    'בדף האחרון, תוצאות, בחרו תרשימים או טבלת תכונות. התרשימים משתמשים בכל האובייקטים שנמדדו ועדכניים במערך הנבחר, גם ללא סיווג. ייצוא שורות גלויות משתמש במסנני הטבלה בדף זה; ייצוא מלא ו־Excel כוללים את כל השורות העדכניות. חבילת ML כוללת רק אובייקטים עם סוגים ידניים שנבדקו.'
)
COMPARE = (
    'Choose Compare side by side to see Native on the left and Objects on the right. Drag the divider to resize the views. The position is saved with the workspace layout. Each image has its own zoom and pan. When a mask edit finishes, Objects reloads the measurement overlays while the unchanged tile image stays in place. A saved pixel edit replaces the tile image and requires a fresh measurement before its masks can be shown.',
    'Откройте «Сравнить рядом», чтобы слева видеть Native, а справа — «Объекты». Перетащите разделитель, чтобы изменить размеры панелей. Положение сохраняется вместе с компоновкой. Масштаб и прокрутка настраиваются отдельно. После правки маски обновляются измеренные маски поверх тайла, а само изображение остаётся на месте. Сохранение правки пикселей заменяет изображение тайла и требует нового измерения для просмотра масок.',
    'בחרו השוואה זו לצד זו כדי להציג את המקור משמאל ואת האובייקטים מימין. גררו את המחיצה כדי לשנות את גודל החלוניות. המיקום נשמר עם פריסת סביבת העבודה. לכל תמונה יש הגדלה והזזה עצמאיות. לאחר עריכת מסכה שכבות המדידה מתעדכנות ותמונת האריח הקיימת נשארת במקום. שמירת עריכת פיקסלים מחליפה את תמונת האריח ודורשת מדידה חדשה להצגת המסכות.',
)
MERGE = (
    (
        'To correct a split, open Objects, click each part or check its ID in the list, then choose Merge selected parts. At least two different objects from one active tile are required. The gold preview identifies the selection. Each click toggles that part; Clear selection removes all checks.',
        'Чтобы исправить разделение, откройте «Объекты», щёлкните по каждой части или отметьте её номер в списке и нажмите «Объединить выбранные части». Нужны минимум два разных объекта одного активного тайла. Выбранные части подсвечены золотым. Повторный щелчок снимает выбор части; «Снять выбор» убирает все галочки.',
        'לתיקון פיצול פתחו אובייקטים, לחצו על כל חלק או סמנו את מספרו ברשימה ובחרו איחוד החלקים שנבחרו. נדרשים לפחות שני אובייקטים שונים מאריח פעיל אחד. הבחירה מודגשת בזהב. לחיצה חוזרת מבטלת בחירת חלק; ניקוי הבחירה מסיר את כל הסימונים.'
    ),
    (
        'Merging takes the pixelwise union of the exact saved masks. It adds no pixels in gaps and does not change tile intensities or YOLO files. Overlapping pixels count once: masks of 110 and 90 pixels sharing 20 pixels give Area=180 px². All six predictors are recomputed from the union; calibrated area uses the saved measurement calibration. Disconnected parts can remain one reviewed object with multiple components, so Euler number and skeleton endpoints can reflect those gaps.',
        'Объединение берёт поэлементное объединение точных сохранённых масок. Пиксели в промежутках не добавляются; яркости тайла и TXT YOLO сохраняются. Общие пиксели считаются один раз: маски 110 и 90 пикселей с пересечением 20 пикселей дают Area=180 px². Все шесть признаков пересчитываются по общей маске; физическая площадь использует калибровку сохранённого измерения. Несвязанные части остаются одним проверенным объектом с несколькими компонентами, поэтому число Эйлера и концы скелета могут отражать разрывы.',
        'האיחוד הוא איחוד פיקסלי של המסכות המדויקות השמורות. לא מתווספים פיקסלים ברווחים, ועוצמות האריח וקובצי YOLO אינם משתנים. פיקסלים חופפים נספרים פעם אחת: מסכות של 110 ו־90 פיקסלים עם 20 פיקסלים משותפים נותנות Area=180 px². כל שש התכונות מחושבות מחדש מהאיחוד; השטח המכויל משתמש בכיול המדידה השמורה. חלקים מנותקים נשארים אובייקט אחד שנבדק עם כמה רכיבים, ולכן מספר אוילר וקצות השלד יכולים לשקף את הפערים.'
    ),
    (
        'A merge publishes another Measurement version with masks, crops, CSV and a source-object record. Previous measurements remain intact. Unchanged objects retain their manual types; the new merged ID starts unclassified and needs review on Object labeling. Undo last mask change reactivates the complete parent measurement, including its manual types; the merged version stays on disk. Further full measurement runs start fresh segmentation. Stale measurements or older results without exact binary masks require recalculation before merging.',
        'Объединение создаёт следующую версию Measurement с масками, фрагментами, CSV и записью исходных объектов. Предыдущие измерения сохраняются. Метки неизменённых объектов переносятся; новый номер объединённого объекта остаётся без класса до проверки в «Разметке объектов». «Отменить изменение масок» возвращает родительское измерение целиком, включая его ручные типы; объединённая версия остаётся на диске. Полный новый расчёт начинает сегментацию заново. Для устаревших измерений и старых результатов без точных бинарных масок перед объединением нужен пересчёт.',
        'האיחוד מפרסם גרסת Measurement נוספת עם מסכות, חיתוכים, CSV ורישום אובייקטי המקור. המדידות הקודמות נשמרות. הסוגים הידניים של אובייקטים שלא השתנו מועתקים; המזהה המאוחד החדש מתחיל ללא סיווג ודורש בדיקה בתיוג אובייקטים. ביטול שינוי המסכות האחרון מפעיל מחדש את מדידת האב המלאה, כולל הסוגים הידניים שלה; הגרסה המאוחדת נשארת בדיסק. חישוב מדידה מלא נוסף מתחיל פילוח חדש. מדידות מיושנות או תוצאות ישנות ללא מסכות בינריות מדויקות דורשות חישוב מחדש לפני איחוד.'
    ),
)


def install(topics, register, russian, hebrew):
    """Replace the former combined-page route and retain the scientific reference."""
    def relabel(text):
        return register(text.replace('Results','Object labeling'),
                        russian.get(text,text).replace('Результаты','Разметка объектов').replace('Результатах','Разметке объектов'),
                        hebrew.get(text,text).replace('תוצאות','תיוג אובייקטים'))
    manual = topics['manual_types']
    manual['title'] = register('Object labeling', 'Разметка объектов', 'תיוג אובייקטים')
    manual['paragraphs'] = (register(*LABELING),) + tuple(relabel(p) for p in manual['paragraphs'])
    segment = topics['segmentation']
    segment['paragraphs'] = (register(*SEGMENT), register(*COMPARE)) + tuple(
        relabel(p) if 'Results gallery' in p else p for p in segment['paragraphs'][1:]) + tuple(register(*p) for p in MERGE)
    topics['results']['paragraphs'] = (register(*FINAL),) + tuple(
        relabel(p) if "Open object's tile" in p or 'Results → Open' in p else p for p in topics['results']['paragraphs'])
    topics['segmentation_review'] = dict(title=register('Tile images and measured masks','Изображения тайлов и измеренные маски','תמונות אריחים ומסכות מדידה'),
        paragraphs=(register(*SEGMENT), register(*COMPARE)) + tuple(register(*p) for p in MERGE),parameters=())
    topics['merge_objects'] = dict(title=register('Merge split objects','Объединение разделённых объектов','איחוד אובייקטים שפוצלו'),
        paragraphs=tuple(register(*p) for p in MERGE),parameters=())


FIRST_STEPS = (
    ('In Segmentation, measure using YOLO files or automatic fallback. Inspect Objects on the selected native tile. Merge any parts you have verified belong to one object.',
     'В «Сегментации» запустите измерение по YOLO или с автопоиском. Проверьте вкладку «Объекты» на выбранном native-тайле. Объедините части, которые после проверки относятся к одному объекту.',
     'בפילוח הפעילו מדידה לפי YOLO או זיהוי אוטומטי כשחסרים קבצים. בדקו אובייקטים על אריח המקור הנבחר. אחדו חלקים שבדקתם ושייכים לאותו אובייקט.'),
    LABELING, FINAL,
)
