"""Searchable, modeless application help with immutable factory references."""

from copy import deepcopy
from html import escape
import re

from src.default_settings import (DEFAULTS_VERSION, EDITOR_DEFAULTS, EDITOR_DEFAULTS_VERSION,
                                  MODEL_DEFAULTS, MODEL_DEFAULTS_VERSION)
from .i18n import get_language, register_translations, tr
from .help_walkthrough import FIRST_RUN, GUIDED_SECTIONS
from .parameter_guidance import GUIDANCE
from .parameter_reference import FILTERS, MASK, MEASURE, SOURCES, TILING, PARAMETER_REFERENCE, parameter_entry, reference_rows
from .qt import QtCore, QtGui, QtWidgets


_RU, _HE = {}, {}


def _t(english, russian, hebrew):
    _RU[english], _HE[english] = russian, hebrew
    return english


_t('SoLoData help', 'Справка SoLoData', 'עזרה של SoLoData')
_t('Search application help or a parameter key', 'Поиск по справке или ключу параметра', 'חיפוש בעזרה או לפי מפתח פרמטר')
_t('Parameter', 'Параметр', 'פרמטר')
_t('Factory default', 'Заводское значение', 'ערך ברירת מחדל מקורי')
_t('Current value', 'Текущее значение', 'ערך נוכחי')
_t('Valid range', 'Допустимые значения', 'טווח תקין')
_t('Purpose', 'Назначение', 'מטרה')
_t('Units', 'Единицы', 'יחידות')
_t('Increase / enable', 'Увеличение / включение', 'הגדלה / הפעלה')
_t('Decrease / disable', 'Уменьшение / выключение', 'הקטנה / כיבוי')
_t('Example', 'Пример', 'דוגמה')
_t('Important', 'Важно', 'חשוב')
_t('Related parameters', 'Связанные параметры', 'פרמטרים קשורים')
_t('Related guides', 'Связанные разделы', 'מדריכים קשורים')
_t('First run, step by step', 'Первый запуск по шагам', 'הפעלה ראשונה, צעד אחר צעד')
_t('Details and reference', 'Подробности и справочные сведения', 'פרטים ומידע לעיון')
_t('Start', 'К началу', 'להתחלה')
_t('All parameters', 'Все параметры', 'כל הפרמטרים')
_t('Select a row in the table to read its detailed guide here.',
   'Выберите строку в таблице, чтобы открыть здесь подробное описание параметра.',
   'בחרו שורה בטבלה כדי לפתוח כאן את ההסבר המפורט לפרמטר.')
_t('Where to find it', 'Где находится настройка', 'היכן נמצאת ההגדרה')
_t('Try it and check the result', 'Что попробовать и как проверить результат', 'מה לנסות ואיך לבדוק את התוצאה')
_t('How it works', 'Как работает параметр', 'איך הפרמטר פועל')
_t('Pipeline validation and units', 'Правила проверки и единицы', 'כללי אימות ויחידות')
_t('Preparation → Processing settings', 'Подготовка → Настройки обработки', 'הכנה ← הגדרות עיבוד')
_t('Preparation → Choose filters', 'Подготовка → Выбор фильтров', 'הכנה ← בחירת מסננים')
_t('Preparation → Protective mask', 'Подготовка → Защитная маска', 'הכנה ← מסכת הגנה')
_t('Segmentation → Object selection and measurement', 'Сегментация → Выбор объектов и измерение', 'פילוח ← בחירת עצמים ומדידה')
_t('Advanced pipeline setting with no dedicated desktop control.', 'Расширенная настройка пайплайна. Отдельного поля в приложении нет.', 'הגדרת עיבוד מתקדמת ללא בקרה ייעודית בממשק.')
_t('Choose a parameter by the stage where you use it. You can also search by name or key, or click the question mark beside a control in the main window.',
   'Выберите параметр по этапу работы. Можно также найти его по названию или ключу либо нажать на знак вопроса рядом с полем в главном окне.',
   'בחרו פרמטר לפי שלב העבודה. אפשר גם לחפש לפי שם או מפתח, או ללחוץ על סימן השאלה ליד הבקרה בחלון הראשי.')
_t('Factory default is the value shipped with the application. Current value is a snapshot of the control when Help reads it, and may include unsaved edits. For automatic calibration it can show the selected TIFF’s scale.',
   'Заводское значение поставляется с приложением. Текущее значение — снимок поля в момент чтения справкой. В нём могут быть несохранённые правки. При автоматической калибровке справка может показать масштаб выбранного TIFF.',
   'ברירת המחדל היא הערך שסופק עם היישום. הערך הנוכחי הוא תמונת מצב של הבקרה בזמן הקריאה, ויכול לכלול עריכות שלא נשמרו. בכיול אוטומטי אפשר לראות את קנה המידה של ה־TIFF שנבחר.')
_t('Example: gamma is 1.2 at the factory, 1.1 in the last saved settings and 1.3 in the form. Restore saved settings brings back 1.1. Use factory default on the gamma field brings back 1.2.',
   'Пример: заводская гамма равна 1,2, в проекте сохранено 1,1, а в поле сейчас 1,3. «Вернуть сохранённые настройки» вернёт 1,1. Команда возврата заводского значения в контекстном меню поля гаммы вернёт 1,2.',
   'דוגמה: גאמה היא 1.2 כברירת מחדל, 1.1 בהגדרות שנשמרו ו־1.3 בטופס. שחזור הגדרות שמורות מחזיר 1.1. החזרת ברירת המחדל בתפריט השדה מחזירה 1.2.')
_t('Make a comparison with one parameter changed at a time. Use the same image and region. Preview filters before preparing tiles, and inspect verification crops after changing measurement controls.',
   'Для сравнения меняйте по одному параметру на одном изображении и участке. Перед нарезкой используйте предпросмотр фильтров. После изменения параметров измерения проверьте фрагменты объектов.',
   'להשוואה שנו פרמטר אחד בכל פעם באותה תמונה ובאותו אזור. בדקו מסננים בתצוגה מקדימה לפני חלוקה, ופרגמנטי אימות לאחר שינוי בקרות מדידה.')
_t('Desktop fields can have narrower limits than the pipeline rules. Available channels and slices depend on the TIFF.',
   'Поля приложения могут иметь более узкие пределы, чем правила пайплайна. Доступные каналы и срезы зависят от TIFF.',
   'לבקרות בממשק עשויים להיות גבולות צרים יותר מכללי העיבוד. הערוצים והחתכים תלויים בקובץ TIFF.')
_t('Not supplied', 'Не передано', 'לא נמסר')
_t('Not set', 'Не задано', 'לא מוגדר')
_t('Automatic', 'Автоматически', 'אוטומטי')
_t('On', 'Включено', 'פעיל')
_t('Off', 'Выключено', 'כבוי')
_t('Close', 'Закрыть', 'סגירה')
_t('Parameter: {title}', 'Параметр: {title}', 'פרמטר: {title}')
_t('No matching help. Try a shorter term or a technical key such as gamma.', 'Ничего не найдено. Попробуйте короткое слово или ключ, например gamma.', 'לא נמצאה עזרה מתאימה. נסו מילה קצרה יותר או מפתח טכני כגון gamma.')
_t('Reference version {version}. Help is read-only; factory defaults are independent of the current project.',
   'Версия справочника {version}. Справка только для чтения; фиксированные значения не зависят от проекта.',
   'גרסת מדריך {version}. העזרה מיועדת לקריאה בלבד; ברירות המחדל המקוריות אינן תלויות בפרויקט הנוכחי.')


TOPICS = {
    'getting_started': dict(title=_t('Getting started', 'Начало работы', 'צעדים ראשונים'), paragraphs=(
        _t('SoLoData reopens the last project that was opened successfully. If it is missing, unreadable or locked, the application opens the default project and reports the reason. The launcher argument --project takes precedence.',
           'SoLoData открывает последний успешно открытый проект. Если файл недоступен или проект занят другим окном, приложение открывает проект по умолчанию и сообщает причину. Аргумент запуска --project имеет приоритет.',
           'SoLoData פותח את הפרויקט האחרון שנפתח בהצלחה. אם הקובץ חסר, אינו קריא או נעול, היישום פותח את פרויקט ברירת המחדל ומציג את הסיבה. לארגומנט ההפעלה --project יש עדיפות.'),
        _t('SoLoData prepares microscopy images, measures object masks, and lets you assign reviewed types. Model training compares classifiers on those labels.',
           'SoLoData подготавливает микроскопические изображения, измеряет маски и позволяет вручную назначать типы объектов. Страница «Обучение модели» сравнивает классификаторы по этим меткам.',
           'SoLoData מכין תמונות מיקרוסקופיה, מודד מסכות ומאפשר לסווג עצמים ידנית. דף אימון מודל משווה מסווגים לפי התוויות האלה.'),
        _t('Create or open a project → add and check TIFFs → preview filters → prepare tiles → review or exclude tiles → import YOLO polygons or detect objects → inspect object crops and assign types → export scientific or training CSV.',
           'Создайте или откройте проект → добавьте и отметьте TIFF → проверьте фильтры → подготовьте тайлы → проверьте и исключите лишние тайлы → импортируйте YOLO-полигоны или выделите объекты → проверьте фрагменты и назначьте типы → экспортируйте CSV измерений или обучения.',
           'צרו או פתחו פרויקט ← הוסיפו וסמנו TIFF ← בדקו את המסננים ← הכינו אריחים ← בדקו או החריגו אריחים ← ייבאו מצולעי YOLO או זהו עצמים ← בדקו פרגמנטים ושייכו סוגים ← ייצאו CSV מדעי או לאימון.'),
        _t('The Dataset selector contains prepared runs, not raw TIFFs. It stays empty until preparation completes or Open prepared tiles connects one existing v3 dataset folder.',
           'Список «Набор» содержит готовые запуски, а не исходные TIFF. Он пуст, пока не завершена подготовка или не открыта папка существующего набора v3.',
           'בורר מערך הנתונים מכיל ריצות מוכנות, לא קובצי TIFF גולמיים. הוא נשאר ריק עד סיום ההכנה או פתיחת תיקייה של מערך v3 קיים.'),
    ), parameters=('channel', 'target_size', 'pixel_size_um')),
    'sources': dict(title=_t('Sources and projects', 'Исходники и проекты', 'מקורות ופרויקטים'), paragraphs=(
        _t('Add TIFF reads image headers. Checkboxes select the processing batch; selecting a row chooses the preview source. TIFF axes determine X/Y, channel and an optional Z/I/T plane. RGB indices are 0 red, 1 green, 2 blue; grayscale and 2D images use index 0.',
           '«Добавить TIFF» читает заголовки. Галочки выбирают пакет обработки, выделенная строка — исходник предпросмотра. Оси TIFF определяют X/Y, канал и плоскость Z/I/T. Для RGB: 0 красный, 1 зелёный, 2 синий; для серого и 2D изображения — 0.',
           'הוספת TIFF קוראת כותרות. תיבות הסימון בוחרות את אצוות העיבוד; בחירת שורה קובעת את מקור התצוגה המקדימה. צירי TIFF מגדירים X/Y, ערוץ ומישור Z/I/T אופציונלי. ב־RGB: אדום 0, ירוק 1 וכחול 2; בתמונה אפורה או דו־ממדית משתמשים ב־0.'),
        _t('Only uint8 and uint16 are supported. uint16 processing uses its high byte (value >> 8), not percentile normalization. Optional raw native export preserves the original bit depth. Ambiguous multi-series or multi-stack-axis TIFFs must be exported explicitly before use.',
           'Поддерживаются uint8 и uint16. Для обработки uint16 берётся старший байт (value >> 8), без процентильной нормализации. Raw native сохраняет исходную разрядность. Неоднозначные TIFF с несколькими сериями или осями стека нужно явно экспортировать.',
           'נתמכים uint8 ו־uint16. עיבוד uint16 משתמש בבית הגבוה (value >> 8), ולא בנרמול אחוזונים. ייצוא מקור גולמי שומר את עומק הסיביות המקורי. יש לייצא במפורש קובצי TIFF לא חד־משמעיים בעלי כמה סדרות או כמה צירי ערימה.'),
        _t('The project remembers sources, prepared versions, annotations, measurements and history. New preparation settings create another run. Choose the run by its name, short ID and status. Keep source paths available; opening the app does not regenerate full TIFF datasets.',
           'Проект хранит исходники, версии подготовки, разметку, измерения и историю. Новые настройки создают отдельный запуск. Выбирайте его по имени, короткому ID и статусу. Сохраняйте доступ к исходным путям; открытие приложения не пересоздаёт TIFF-наборы.',
           'הפרויקט זוכר מקורות, גרסאות הכנה, תיוגים, מדידות והיסטוריה. הגדרות הכנה חדשות יוצרות ריצה נוספת. בחרו ריצה לפי שם, מזהה קצר ומצב. שמרו על זמינות נתיבי המקור; פתיחת היישום אינה מפיקה מחדש מערכי TIFF שלמים.'),
    ), parameters=('channel', 'plane', 'pixel_size_um', 'save_raw_tiles')),
    'preparation': dict(title=_t('Preparation and filters', 'Подготовка и фильтры', 'הכנה ומסננים'), paragraphs=(
        _t('Changing the selected TIFF clears images from the previous source. Click Preview selected TIFF to load the comparison for the new source. The caption distinguishes source dimensions from the reduced display dimensions.',
           'Смена выбранного TIFF очищает изображения предыдущего исходника. Нажмите предпросмотр, чтобы загрузить сравнение для нового файла. Подпись различает размеры исходника и уменьшенной экранной копии.',
           'שינוי ה־TIFF הנבחר מנקה תמונות של המקור הקודם. לחצו על תצוגה מקדימה כדי לטעון השוואה למקור החדש. הכיתוב מבדיל בין ממדי המקור לממדי עותק התצוגה המוקטן.'),
        _t('Enabled grayscale steps run in order: bilateral denoising → white top-hat plus min–max normalization → reciprocal-gamma LUT. Switching a step off bypasses it while keeping its parameter values. Turning top-hat off also bypasses its normalization.',
           'Включённые фильтры идут по порядку: bilateral → white top-hat с min–max нормализацией → LUT с показателем 1/gamma. Выключенная стадия пропускается с сохранением параметров. Отключение top-hat пропускает и его нормализацию.',
           'שלבי האפור הפעילים פועלים לפי הסדר: החלקה בילטרלית ← white top-hat עם נרמול מינימום–מקסימום ← טבלת גאמה הפוכה. כיבוי שלב מדלג עליו ושומר את ערכיו. כיבוי top-hat מדלג גם על הנרמול שלו.'),
        _t('Gamma uses x^(1/gamma). Gamma 1 is identity; gamma above 1 brightens faint background as well as faint signal. Min–max normalization changes a value range, not a distribution into a Gaussian. A brighter image is not evidence of greater segmentation accuracy.',
           'Гамма использует x^(1/gamma). Гамма 1 — без изменения; выше 1 осветляются и слабый фон, и сигнал. Min–max меняет диапазон значений, а не превращает распределение в гауссово. Более яркая картинка не доказывает точность сегментации.',
           'גאמה משתמשת ב־x^(1/gamma). גאמה 1 היא זהות; מעל 1 מובהרים גם רקע חלש וגם אות חלש. נרמול מינימום–מקסימום משנה טווח ערכים, לא יוצר התפלגות גאוסית. תמונה בהירה יותר אינה ראיה לדיוק פילוח גבוה יותר.'),
        _t('A separate protective mask uses modified global Otsu ignoring zero intensity, threshold max(10, int(T × factor)), optional elliptical closing and dilation. Closing and dilation change mask dimensions. This routing mask is not the grayscale image, the annotation polygon or the thresholded measurement mask.',
           'Отдельная защитная маска использует глобальный Otsu без нулевой яркости, порог max(10, int(T × коэффициент)), замыкание и расширение эллипсом. Морфология меняет размеры маски. Она не равна серому изображению, полигону разметки или пороговой маске измерений.',
           'מסכת הגנה נפרדת משתמשת ב־Otsu גלובלי המתעלם מעוצמה אפס, בסף max(10, int(T × מקדם)) ובסגירה והרחבה אליפטיות אופציונליות. המורפולוגיה משנה את ממדי המסכה. מסכת הניתוב אינה תמונת האפור, מצולע התיוג או מסכת הסף למדידה.'),
        _t('Choose a TIFF and inspect Source channel. Then run Preview selected TIFF and inspect Filtering and Protective mask in that order. Filters, normalization and Otsu run on the whole native plane before the display is reduced to at most 2400 pixels. Use 1:1 or View at source resolution to inspect a native-pixel region.',
           'Выберите TIFF и проверьте «Исходный канал». Затем запустите предпросмотр и проверьте по порядку «Фильтрацию» и «Защитную маску». Фильтры, нормализация и Otsu считаются по всей исходной плоскости, после чего экранная копия уменьшается до 2400 пикселей. Для просмотра участка в исходных пикселях используйте 1:1 или «Просмотр в исходном разрешении».',
           'בחרו TIFF ובדקו ערוץ מקור. לאחר מכן הפעילו תצוגת TIFF נבחר ובדקו לפי הסדר סינון ומסכת הגנה. המסננים, הנרמול ו־Otsu מחושבים לכל מישור המקור לפני הקטנת התצוגה לעד 2400 פיקסלים. השתמשו ב־1:1 או בתצוגה ברזולוציית המקור לבדיקת אזור בפיקסלי המקור.'),
        _t('Choose Compare side by side to show the source channel on the left and the filtered image on the right. Drag the divider to resize the views. The position is saved with the workspace layout. Each image has independent zoom, pan and fit controls.',
           'Откройте «Сравнить рядом», чтобы слева видеть исходный канал, а справа — отфильтрованное изображение. Перетащите разделитель для изменения размера панелей. Положение сохраняется вместе с компоновкой. Масштаб, перемещение и подгонка изображения настраиваются отдельно.',
           'בחרו השוואה זו לצד זו להצגת ערוץ המקור משמאל והתמונה המסוננת מימין. גררו את המחיצה לשינוי גודל החלוניות. המיקום נשמר עם פריסת סביבת העבודה. לכל תמונה יש הגדלה, הזזה והתאמה עצמאיות.'),
        _t('Full-image preview can take as long as filtering during preparation and runs in the cancellable worker. A completed preview is reused only when source size/time, channel, plane and all resolved settings match. Changed settings create another Preview version; previous tiles and measurements remain intact. Earlier versions of the application displayed only a central 1200×1200 crop, which was not a slicing tile.',
           'Предпросмотр всего изображения может занимать столько же времени, сколько фильтрация при подготовке; он идёт в обработчике с отменой. Готовый результат используется повторно только при совпадении размера/времени исходника, канала, среза и всех итоговых настроек. Изменения создают новую версию Preview; готовые тайлы и измерения сохраняются. Раньше показывался только центральный фрагмент 1200×1200 — это был не тайл нарезки.',
           'תצוגה מקדימה מלאה עשויה להימשך כמו סינון בהכנה ופועלת בעובד שניתן לביטול. תוצאה מוכנה משמשת שוב רק כשגודל/זמן המקור, הערוץ, החתך וכל ההגדרות שנפתרו תואמים. שינוי יוצר גרסת Preview נוספת; האריחים והמדידות הקודמים נשמרים. גרסאות קודמות הציגו רק פרגמנט מרכזי של 1200×1200, שלא היה אריח חלוקה.'),
    ), parameters=('enable_bilateral', 'enable_tophat', 'enable_gamma', 'gamma', 'otsu_safety_factor', 'bridge_kernel_size', 'buffer_kernel_size')),
    'tiles': dict(title=_t('Tiles, native scale and review', 'Тайлы, native-масштаб и проверка', 'אריחים, קנה מידה מקורי ובדיקה'), paragraphs=(
        _t('Each v3 tile has a fixed square model PNG, a native crop, an exact valid ownership mask and scale metadata. Large complete crops can be reduced into the model canvas while retaining native pixels for measurement. Padding is added on the right and bottom.',
           'У v3-тайла есть квадратный модельный PNG, native-фрагмент, точная маска принадлежности и масштаб. Большой целый фрагмент может уменьшаться в модельное поле; измерения сохраняют native-пиксели. Поля добавляются справа и снизу.',
           'לכל אריח v3 יש PNG ריבועי קבוע למודל, פרגמנט מקור, מסכת שיוך מדויקת ומטא־נתוני קנה מידה. פרגמנטים גדולים ושלמים יכולים להיות מוקטנים לתמונת המודל תוך שמירת פיקסלי המקור למדידה. ריפוד נוסף מימין ומלמטה.'),
        _t('Final ownership assigns every source pixel once and keeps whole 8-connected components of the supplied protective mask. Rectangular crops can overlap; valid_masks determines ownership. This does not prove that all biological objects were detected. The route alone may cross a diagonal corner; later component allocation repairs ownership.',
           'Итоговая принадлежность назначает каждый пиксель один раз и сохраняет целые 8-связные компоненты защитной маски. Прямоугольники могут пересекаться; принадлежность задаёт valid_masks. Это не доказывает нахождение всех биологических объектов. Маршрут может пройти между диагональными углами; затем распределение компонент исправляет принадлежность.',
           'השיוך הסופי מקצה כל פיקסל מקור פעם אחת ושומר רכיבים שלמים בקישוריות 8 במסכת ההגנה שסופקה. מלבני הפרגמנטים יכולים לחפוף; valid_masks קובע את השיוך. אין בכך הוכחה שכל העצמים הביולוגיים זוהו. המסלול עצמו עשוי לעבור בין פינות אלכסוניות; שיוך הרכיבים בהמשך מתקן את הבעלות על הפיקסלים.'),
        _t('In Preparation, set the left/up and right/down search-window limits with the sliders or enter exact source pixels beside them. The straight search tries the initial window first, then moves the same-width window within those limits. At equal distances it tries left or up first. If no trial finds a corridor, Dijkstra searches the initial window. For a 1500 px model side, the initial window is [1125, 1462), with a 22 px shift step. The factory settings are Automatic left/up and 0 px right/down. Set both limits to 0 to try only the initial window before Dijkstra.',
           'В «Подготовке» задайте пределы сдвига влево/вверх и вправо/вниз ползунками или введите точное число исходных пикселей рядом. Прямой поиск сначала проверяет первое окно, затем сдвигает окно той же ширины в заданных пределах. При равных расстояниях сначала проверяется сдвиг влево или вверх. Если коридор не найден, Дейкстра ищет путь в первом окне. При стороне модели 1500 px первое окно — [1125, 1462), шаг сдвига — 22 px. Заводские значения — «Автоматически» влево/вверх и 0 px вправо/вниз. При двух нулях перед Дейкстрой проверяется только первое окно.',
           'בהכנה קבעו את גבולות ההזזה שמאלה/למעלה וימינה/למטה באמצעות המחוונים או הזינו לידם מספר מדויק של פיקסלי מקור. חיפוש המסדרון הישר בודק תחילה את החלון הראשון ואז מזיז חלון ברוחב קבוע בתוך הגבולות. במרחקים שווים הוא בודק קודם שמאלה או למעלה. אם אין מסדרון, דייקסטרה מחפש בחלון הראשון. עבור צלע מודל של 1500 פיקסלים החלון הראשון הוא [1125, 1462) והצעד הוא 22 פיקסלים. ברירת המחדל היא אוטומטי שמאלה/למעלה ו־0 ימינה/למטה. כששני הגבולות הם 0 נבדק רק החלון הראשון לפני דייקסטרה.'),
        _t('Open prepared tiles expects one dataset folder containing model PNGs, native, valid_masks and overview JSON, not the parent of many datasets. Click the overview to select exact pixel ownership. Search and display filters only change the list; explicit Exclude or Restore changes active model PNGs while retaining native files and metadata.',
           '«Открыть тайлы» ожидает папку одного набора с модельными PNG, native, valid_masks и overview JSON, а не общий каталог. Нажатие на обзор выбирает точную принадлежность. Поиск меняет список; «Исключить»/«Вернуть» меняют активные PNG, сохраняя native и метаданные.',
           'פתיחת אריחים מוכנים דורשת תיקייה של מערך אחד עם PNG למודל, native, valid_masks ו־JSON של הסקירה, לא את תיקיית האב של כמה מערכים. לחיצה בסקירה בוחרת לפי שיוך מדויק. חיפוש ומסנני תצוגה משנים רק את הרשימה; החרגה או שחזור משנים את אריחי המודל הפעילים ושומרים את קובצי המקור והמטא־נתונים.'),
        _t('Inspect bright-region flags and boundary areas before marking the review complete. Flags are review hints, not predicted biological classes. Changed exclusions invalidate current measurements; new slicing runs must not reuse old tile IDs or annotations automatically.',
           'Проверьте яркие области и границы перед завершением проверки. Флаги — подсказки, а не биологические классы. Изменение исключений делает измерения неактуальными; новая нарезка не должна автоматически наследовать старые ID и разметку.',
           'בדקו אזורים בהירים וגבולות לפני סימון הבדיקה כהושלמה. הדגלים הם רמזי בדיקה, לא מחלקות ביולוגיות חזויות. שינוי החרגות מבטל את עדכניות המדידות; חלוקה חדשה אינה אמורה להשתמש אוטומטית במזהים ובתיוגים ישנים.'),
        _t('Use Initial search window end to set the right/bottom edge in source pixels. At tile size 1500, entering 1400 gives [1125, 1400) and up to 100 px right/down travel. The left/up limit remains 750 px. Automatic restores the end at 1462 and allows up to 38 px right/down.',
           'Поле «Конец исходного окна поиска» задаёт правую или нижнюю границу в исходных пикселях. При тайле 1500 значение 1400 даёт окно [1125, 1400) и до 100 px сдвига вправо или вниз. Предел влево или вверх остаётся 750 px. «Автоматически» возвращает границу 1462 и предел сдвига вправо или вниз 38 px.',
           'השדה «קצה חלון החיפוש הראשון» מגדיר את הקצה הימני או התחתון בפיקסלי מקור. באריח בגודל 1500, ערך 1400 יוצר חלון [1125, 1400) עם הזזה של עד 100 פיקסלים ימינה או למטה. הגבול שמאלה או למעלה נשאר 750 פיקסלים. מצב אוטומטי מחזיר את הקצה ל־1462 ומאפשר הזזה של עד 38 פיקסלים ימינה או למטה.'),
    ), parameters=('target_size', 'search_window_end', 'straight_shift_left', 'straight_shift_right', 'oversized_policy', 'min_corridor_width', 'seam_repulsion_power', 'overview_size')),
    'segmentation': dict(title=_t('Segmentation and annotations', 'Сегментация и разметка', 'פילוח ותיוגים'), paragraphs=(
        _t("Choose a prepared dataset first. With no YOLO annotations, click Measure with automatic fallback. With YOLO annotations, import the folder, check the report, choose a mode, and click Measure using selected mode. Select a tile on the Tiles page to preview its polygons. Open existing results switches to Results without recalculating.",
           "Сначала выберите готовый набор. Без YOLO-разметки нажмите «Измерить с автопоиском при отсутствии TXT». Если разметка есть, импортируйте папку, проверьте отчёт, выберите режим и нажмите «Измерить в выбранном режиме». Для предпросмотра полигонов выберите тайл на странице «Тайлы». «Открыть готовые результаты» переключает страницу без пересчёта.",
           "תחילה בחרו מערך מוכן. בלי תיוגי YOLO לחצו על מדידה עם זיהוי אוטומטי כשחסר TXT. אם יש תיוגים, ייבאו את התיקייה, בדקו את הדוח, בחרו מצב ולחצו על מדידה במצב הנבחר. בחרו אריח בדף האריחים כדי לראות מצולעים. פתיחת תוצאות קיימות עוברת לתוצאות ללא חישוב חוזר."),
        _t("Import copies matching TXT files into a new project annotation version. Open saved annotations shows that folder in Explorer. Check annotations counts active tiles, files with polygons, empty, missing and invalid TXT files, and unknown filenames. Fix errors in the source folder and reimport. Example: tile_0123.txt matches tile_0123.png. One line 1 0.1 0.1 0.4 0.1 0.4 0.3 0.1 0.3 describes a class 1 rectangle in normalized model-tile coordinates.",
           "Импорт копирует подходящие TXT в новую версию разметки проекта. «Открыть сохранённую разметку» показывает эту папку в Проводнике. Проверка считает активные тайлы, TXT с полигонами, пустые, отсутствующие и некорректные TXT и неизвестные имена. Исправьте ошибки в исходной папке и импортируйте её заново. Например, tile_0123.txt соответствует tile_0123.png. Строка 1 0.1 0.1 0.4 0.1 0.4 0.3 0.1 0.3 описывает прямоугольник класса 1 в нормированных координатах модельного тайла.",
           "הייבוא מעתיק TXT תואמים לגרסת תיוג חדשה. פתיחת תיוגים שמורים מציגה את התיקייה בסייר. הבדיקה סופרת אריחים פעילים, TXT עם מצולעים, קבצים ריקים, חסרים או שגויים ושמות לא מוכרים. תקנו בתיקיית המקור וייבאו שוב. לדוגמה, tile_0123.txt מתאים ל־tile_0123.png. השורה 1 0.1 0.1 0.4 0.1 0.4 0.3 0.1 0.3 מתארת מלבן במחלקה 1 בקואורדינטות מנורמלות של אריח המודל."),
        _t("Example: tile A has polygons, B has an empty TXT, and C has no TXT. Existing annotations only measures A and skips C. Require all stops because C is missing. Automatic fallback measures A and detects contours on C. B yields zero objects in all modes. The automatic fallback button selects that mode and starts measurement. Assign manual types in the Results gallery after measuring.",
           "Пример: у тайла A есть полигоны, у B пустой TXT, у C нет TXT. Режим имеющейся разметки измеряет A и пропускает C. Строгий режим останавливается из-за C. Автопоиск измеряет A и ищет контуры на C. B даёт ноль объектов во всех режимах. Кнопка автопоиска выбирает этот режим и запускает измерение. Ручные типы назначаются после расчёта в галерее результатов.",
           "לדוגמה, לאריח A יש מצולעים, ל־B יש TXT ריק ול־C חסר TXT. תיוגים קיימים מודד את A ומדלג על C. דרישת כולם עוצרת בגלל C. זיהוי אוטומטי מודד את A ומזהה קווי מתאר ב־C. ‏B נותן אפס עצמים בכל מצב. כפתור הזיהוי בוחר במצב זה ומתחיל מדידה. סוגים ידניים משויכים אחר כך בגלריית התוצאות."),
        _t("Cleanup threshold (0–255, default 25) is a brightness floor in the filtered 8-bit image. On tiles without TXT it also sets the initial contour threshold before 3×3 closing. Inside a contour, for local Otsu T > 10 the final threshold is max(floor, int(T × factor)); otherwise use the floor. The factor defaults to 0.70 (control range 0.01–2). With T=80 the defaults give 56; with T=30 they give 25. Pixels strictly brighter than the threshold survive. Higher thresholds can remove dim object parts as well as background.",
           "Порог очистки (0–255, по умолчанию 25) задаёт нижнюю границу яркости на фильтрованном 8-битном изображении. На тайлах без TXT он также задаёт начальный порог поиска контуров перед замыканием 3×3. Внутри контура при локальном Otsu T > 10 итоговый порог равен max(нижняя граница, int(T × коэффициент)), иначе берётся нижняя граница. Коэффициент по умолчанию 0,70 (диапазон поля 0,01–2). При T=80 получится 56, при T=30 — 25. Сохраняются пиксели строго ярче порога. Повышение может убрать и фон, и тусклые части объектов.",
           "סף ניקוי (0–255, ברירת מחדל 25) הוא גבול תחתון לעוצמה בתמונה מסוננת של 8 ביט. באריחים ללא TXT הוא גם הסף ההתחלתי לפני סגירה 3×3. בתוך קו המתאר, אם Otsu מקומי T > 10 הסף הוא max(גבול תחתון, int(T × מקדם)), אחרת מוחל הגבול התחתון. ברירת המחדל למקדם היא 0.70 (טווח בקרה 0.01–2). עבור T=80 מתקבל 56 ועבור T=30 מתקבל 25. נשמרים פיקסלים בהירים מהסף. סף גבוה עשוי להסיר רקע וחלקי עצמים עמומים."),
        _t("Minimum area (1–100000 in the control, default 30 native px²) counts foreground pixels in each cleaned 8-connected component. At 30, a 29-pixel component is discarded and a 30-pixel component is kept. A polygon may yield zero, one or several rows. These controls affect new measurements. Recalculation starts a new set of object IDs and manual types. Export reviewed objects before recalculating if you need those labels for training.",
           "Минимальная площадь (диапазон поля 1–100000, по умолчанию 30 исходных px²) считает пиксели каждой очищенной 8-связной компоненты. При 30 компонента из 29 пикселей отбрасывается, из 30 сохраняется. Один полигон может дать ноль, одну или несколько строк. Поля действуют на новые измерения. При пересчёте создаётся новый набор ID объектов и ручных меток. Если нужны прежние метки для обучения, выгрузите проверенные объекты до пересчёта.",
           "שטח מזערי (טווח בקרה 1–100000, ברירת מחדל 30 פיקסלי מקור רבועים) סופר פיקסלים בכל רכיב נקי בקישוריות 8. בערך 30 רכיב בן 29 פיקסלים נדחה ורכיב בן 30 נשמר. מצולע עשוי לתת אפס, שורה אחת או כמה שורות. הבקרות חלות על מדידות חדשות. מדידה מחדש מתחילה מערך חדש של מזהים ותיוגים ידניים. אם התיוגים הקודמים דרושים לאימון, ייצאו אותם לפני חישוב מחדש."),
        _t('Import YOLO segmentation TXT polygons matched to exact model-tile filenames. Coordinates are normalized to the model canvas; v3 maps them back into native space. Import checks names, class IDs, vertex count and coordinate ranges. No built-in trained YOLO or SAM inference runs here.',
           'Импортируйте YOLO segmentation TXT с точными именами модельных тайлов. Координаты нормированы на модельное поле; v3 переносит их в native. Проверяются имена, ID классов, число вершин и диапазон. Обученный YOLO или SAM внутри этого этапа не запускается.',
           'ייבאו מצולעי TXT של YOLO segmentation התואמים בדיוק לשמות אריחי המודל. הקואורדינטות מנורמלות למשטח המודל; v3 ממפה אותן למקור. הייבוא בודק שמות, מזהי מחלקות, מספר קודקודים וטווחים. כאן לא מופעל חיזוי של YOLO או SAM מאומנים.'),
        _t('Existing annotations only measures available TXT files. Require all needs a TXT for every active tile. Automatic fallback detects contours only where a TXT is missing. An existing empty TXT always means zero annotated objects. Automatically detected source classes are Unknown.',
           '«Только разметка» измеряет имеющиеся TXT. «Требовать все» требует TXT для каждого активного тайла. Автоматический режим ищет контуры только при отсутствии TXT. Пустой существующий TXT всегда означает ноль объектов. Исходный класс автоматических объектов — Unknown.',
           'מצב תיוגים קיימים בלבד מודד קובצי TXT זמינים. דרישת כולם מחייבת TXT לכל אריח פעיל. גיבוי אוטומטי מזהה קווי מתאר רק כאשר TXT חסר. קובץ TXT קיים וריק תמיד מציין אפס עצמים מתויגים. מחלקת המקור של עצמים אוטומטיים היא Unknown.'),
        _t('Inside each polygon or detected contour, local thresholding produces a measurement mask. Cleaned 8-connected components are split and filtered by minimum native area. Touching fibers are not separated by an implemented Frangi/hybrid method. Components inherit their source annotation class until you review manual targets.',
           'В полигоне или контуре локальный порог формирует маску измерений. Очищенные 8-связные компоненты разделяются и фильтруются по native-площади. Разделение соприкасающихся волокон Frangi/hybrid не реализовано. Компоненты наследуют исходный класс до ручной проверки.',
           'בתוך כל מצולע או קו מתאר, סף מקומי יוצר מסכת מדידה. רכיבים נקיים בקישוריות 8 מופרדים ומסוננים לפי שטח מקור מזערי. לא ממומשת הפרדת סיבים נוגעים באמצעות Frangi/hybrid. הרכיבים יורשים את מחלקת תיוג המקור עד לבדיקת היעדים הידניים.'),
        _t('A faint middle can fall below the cleanup threshold and separate one visible fiber into two measured components. Lowering the threshold can retain the connection and also retain a halo around other objects. For a fixed local Otsu of 80, a floor of 25 and factor 0.70 give 56. With factor 0.45 the threshold is 36. A middle intensity of 40 survives the second choice, and background intensity 38 survives too. These are illustrative intensities. The two controls act on brightness and therefore cannot distinguish signal and background that share the same brightness.',
           'Слабая середина может оказаться ниже порога очистки и разделить одно видимое волокно на две измеряемые компоненты. Снижение порога сохраняет соединение и одновременно может сохранить ореол вокруг других объектов. При фиксированном локальном Otsu 80, минимуме 25 и коэффициенте 0,70 порог равен 56. При коэффициенте 0,45 порог равен 36. Середина с яркостью 40 сохраняется во втором варианте, как и фон с яркостью 38. Это учебные значения яркости. Оба поля действуют по яркости, поэтому сигнал и фон одинаковой яркости проходят одно правило.',
           'מרכז חלש עלול לרדת מתחת לסף הניקוי ולפצל סיב הנראה בתמונה לשני רכיבים נמדדים. הורדת הסף יכולה לשמור את החיבור וגם לשמור הילה סביב עצמים אחרים. עבור Otsu מקומי קבוע של 80, רצפה 25 ומקדם 0.70 מתקבל סף 56. במקדם 0.45 הסף הוא 36. מרכז בעוצמה 40 נשמר בבחירה השנייה, וגם רקע בעוצמה 38 נשמר. אלה עוצמות לצורכי הדגמה. שתי הבקרות פועלות לפי בהירות, ולכן אות ורקע בעלי אותה בהירות עוברים את אותו כלל.'),
        _t('Compare the same native region and verification crops after changing one control. For a localized dim section, select that rectangle in the tile editor and preview gamma there before measuring again. Inspect the resulting area and skeleton together. Each saved measurement keeps its own settings and input versions.',
           'После изменения одного поля сравните тот же native-участок и проверочные фрагменты. Для отдельного слабого участка выделите его прямоугольником в редакторе тайла и проверьте локальную гамму перед новым измерением. Вместе оценивайте площадь маски и её скелет. Каждая версия измерений сохраняет свои настройки и версии входных данных.',
           'אחרי שינוי בקרה אחת השוו את אותו אזור מקור ואת פרגמנטי האימות. למקטע חלש ומקומי בחרו מלבן בעורך האריחים ובדקו גאמה מקומית לפני מדידה חוזרת. בדקו יחד את שטח המסכה ואת השלד. כל גרסת מדידות שומרת הגדרות וגרסאות קלט משלה.'),
    ), parameters=('min_clean_threshold', 'tier2_threshold_factor', 'min_sub_object_area')),
    'manual_types': dict(title=_t('Object gallery and manual types', 'Галерея и ручные типы', 'גלריית עצמים וסוגים ידניים'), paragraphs=(
        _t('Results shows actual verification crops saved during measurement. Select a gallery card to inspect its larger image. Use a type button or keys 1–6 to save the type and advance. Left/Right moves between visible objects; U finds the next unclassified object. Gallery filters and feature-table filters are separate.',
           'Результаты показывают реальные проверочные фрагменты измерений. Выберите карточку для крупного просмотра. Кнопка типа или клавиши 1–6 сохраняют тип и переходят дальше. Стрелки выбирают соседние видимые объекты, U — следующий без класса. Фильтры галереи и таблицы независимы.',
           'התוצאות מציגות פרגמנטים אמיתיים שנשמרו לאימות המדידות. בחרו כרטיס בגלריה להצגה מוגדלת. כפתור סוג או המקשים 1–6 שומרים סוג ומתקדמים. חצים עוברים בין עצמים גלויים ו־U מוצא את העצם הבא ללא סיווג. מסנני הגלריה וטבלת התכונות נפרדים.'),
        _t('Shared YOLO IDs: 0 particle; 1 fiber; 2 self-crossed tube; 3 crossed tubes; 4 agglomeration; 5 adhered objects. Keyboard keys are 1–6, while stored IDs are 0–5. Under More class controls, choose Unclassified and save to remove an assigned target.',
           'Общие с YOLO ID: 0 частица; 1 волокно; 2 пересечение трубочки самой собой; 3 перекрещенные трубочки; 4 агломерация; 5 слипшиеся объекты. Клавиши — 1–6, ID — 0–5. В дополнительных настройках «Без класса» с сохранением снимает метку.',
           'מזהי YOLO המשותפים: 0 חלקיק; 1 סיב; 2 צינורית החוצה את עצמה; 3 צינוריות מצטלבות; 4 צבר; 5 עצמים צמודים. המקשים הם 1–6 והמזהים שנשמרים הם 0–5. בבקרות הסיווג הנוספות בחרו ללא סיווג ושמרו כדי להסיר יעד.'),
        _t('Manual labels are stored separately beside one measurement version; scientific CSV values and original source classes remain unchanged. Re-extraction creates new object identities and starts without manual labels. Earlier catalog-version labels are interpreted by their stable class keys and migrated on the next save.',
           'Ручные метки хранятся отдельно рядом с версией измерений; научный CSV и исходные классы не меняются. Повторный расчёт создаёт новые ID без ручных меток. Старый каталог читается по стабильным ключам классов и мигрирует при следующем сохранении.',
           'התיוגים הידניים נשמרים בנפרד לצד גרסת מדידה אחת; ערכי ה־CSV המדעיים ומחלקות המקור נשארים ללא שינוי. חישוב מחדש יוצר זהויות עצמים חדשות ללא תיוגים ידניים. תיוגים מקטלוג ישן מפורשים לפי מפתחות המחלקות הקבועים ומועברים לגרסה החדשה בשמירה הבאה.'),
    ), parameters=()),
    'results': dict(title=_t('Measurements, units and limitations', 'Измерения, единицы и ограничения', 'מדידות, יחידות ומגבלות'), paragraphs=(
        _t("Feature statistics uses all current objects of the selected dataset. Choose histogram (X and 1–200 bins, default 30), scatter (X and Y), box plot (X), sample covariance or Pearson correlation. Histogram bars count objects. A scatter point represents one object. The box shows the median and central 50%. Use the toolbar to zoom or save a plot. Only rows with finite values for all plotted features contribute. Matrices require at least two rows. Sample covariance divides by n−1 and depends on units. Pearson correlation measures linear association on −1 to 1; a constant feature gives a dash.",
           "«Статистика признаков» использует все актуальные объекты выбранного набора. Доступны гистограмма (X и 1–200 интервалов, по умолчанию 30), рассеяние (X и Y), ящик с усами (X), выборочная ковариация и корреляция Пирсона. Столбики гистограммы считают объекты, точка рассеяния представляет один объект, ящик показывает медиану и центральные 50% значений. Панель графика позволяет приблизить и сохранить изображение. Учитываются строки с конечными значениями всех признаков графика. Для матриц нужны минимум две строки. Ковариация делится на n−1 и зависит от единиц. Корреляция Пирсона измеряет линейную связь от −1 до 1. Постоянный признак даёт прочерк.",
           "סטטיסטיקת תכונות משתמשת בכל העצמים העדכניים במערך הנבחר. בחרו היסטוגרמה (X ו־1–200 תאים, ברירת מחדל 30), פיזור (X ו־Y), קופסה (X), קווריאנס מדגמי או מתאם פירסון. עמודות סופרות עצמים, נקודת פיזור מייצגת עצם, וקופסה מציגה חציון ו־50% מרכזיים. הסרגל מאפשר זום ושמירה. נכללות שורות עם ערכים סופיים בכל התכונות המוצגות. מטריצות דורשות לפחות שתי שורות. קווריאנס מדגמי מחלק ב־n−1 ותלוי ביחידות. מתאם פירסון מודד קשר ליניארי בין −1 ל־1. תכונה קבועה מסומנת במקף."),
        _t('v3 measures native source pixels. Area counts foreground pixels; with calibration s in µm/px, Area_um2=Area×s². Aspect_Ratio is equivalent-ellipse major/minor axis ratio, not curved fiber centerline length divided by thickness. A degenerate minor axis currently returns AR=1.0.',
           'v3 измеряет исходные native-пиксели. Area считает пиксели объекта; при калибровке s в µm/px Area_um2=Area×s². Aspect_Ratio — отношение осей эквивалентного эллипса, а не длина изогнутого волокна по скелету к толщине. При вырожденной малой оси сейчас AR=1.0.',
           'v3 מודד בפיקסלי המקור. Area סופר פיקסלי עצם; בכיול s במיקרומטר לפיקסל מתקבל Area_um2=Area×s². Aspect_Ratio הוא יחס צירי האליפסה השקולה, לא אורך קו המרכז של סיב מעוקל חלקי עוביו. כאשר הציר הקטן מנוון, מוחזר כיום AR=1.0.'),
        _t('Solidity is mask area divided by convex-hull area. Euler_Number describes connected components minus holes. Endpoints counts skeleton pixels with one neighbor; Branch_Points counts pixels with more than two neighbors, not merged graph junctions. A single crossing can therefore contribute several branch pixels.',
           'Solidity — площадь маски к площади выпуклой оболочки. Euler_Number — число компонент минус отверстия. Endpoints считает пиксели скелета с одним соседом; Branch_Points — с более чем двумя, а не объединённые узлы графа. Один перекрёсток может дать несколько пикселей ветвления.',
           'Solidity הוא שטח המסכה חלקי שטח המעטפת הקמורה. Euler_Number מתאר מספר רכיבים פחות חורים. Endpoints סופר פיקסלי שלד בעלי שכן אחד; Branch_Points סופר פיקסלים בעלי יותר משני שכנים, ולא צמתי גרף מאוחדים. לכן הצטלבות אחת עשויה לתרום כמה פיקסלי הסתעפות.'),
        _t('These are software-defined mask descriptors. Expert ground truth is required to assess segmentation accuracy. Model training evaluates classifiers on reviewed numerical features. Inference on new data and class-specific diameter/length measurement are future work; assigning a type does not calculate those quantities.',
           'Это программно определённые признаки маски. Для проверки точности нужна экспертная разметка. Страница обучения оценивает классификаторы по проверенным числовым признакам. Применение к новым данным и измерение длины/диаметра по классу — будущая работа; назначение типа не вычисляет эти величины.',
           'אלו מתארי מסכה המוגדרים בתוכנה. נדרש תיוג מומחה כדי להעריך דיוק פילוח. עמוד האימון מעריך מסווגים לפי תכונות מספריות שנבדקו. חיזוי על נתונים חדשים ומדידות קוטר ואורך לפי מחלקה הם עבודה עתידית; שיוך סוג אינו מחשב גדלים אלה.'),
    ), parameters=('pixel_size_um', 'min_sub_object_area', 'min_clean_threshold')),
    'export': dict(title=_t('CSV and training export', 'CSV и обучающий экспорт', 'ייצוא CSV ונתוני אימון'), paragraphs=(
        _t("Measurement automatically saves CSV with one row per measured object. Export Excel workbook saves an .xlsx copy of the full current table, with numeric features stored as numbers. Export ML bundle creates a ZIP for the selected measurement with manually typed objects only. X.csv has predictors, y.csv has Manual_Class_ID and objects.csv has traceability fields, all in matching row order. training.csv combines them and manifest.json records the class catalog and source/measurement references. For independent evaluation combine multiple source images and split by original TIFF or experiment.",
           "Расчёт автоматически сохраняет CSV с одной строкой на измеренный объект. «Сохранить Excel (.xlsx)» выгружает всю актуальную таблицу с числовыми ячейками для признаков. «Сохранить набор для ML» создаёт ZIP выбранного измерения только с объектами, которым назначен ручной тип. В X.csv — признаки, в y.csv — Manual_Class_ID, в objects.csv — служебные поля. Порядок строк совпадает. training.csv объединяет столбцы, manifest.json хранит каталог классов и ссылки на источник и измерение. Для независимой оценки объединяйте несколько источников и делите выборку по исходному TIFF или эксперименту.",
           "המדידה שומרת CSV אוטומטית עם שורה לכל עצם שנמדד. ייצוא Excel שומר xlsx של כל הטבלה העדכנית עם תכונות בתאים מספריים. ייצוא חבילת ML יוצר ZIP למדידה הנבחרת עם עצמים שסווגו ידנית בלבד. X.csv כולל תכונות, y.csv את Manual_Class_ID ו־objects.csv שדות מעקב בסדר שורות זהה. training.csv משלב עמודות ו־manifest.json מתעד את קטלוג המחלקות והפניות למקור ולמדידה. להערכה עצמאית שלבו מקורות וחלקו לפי TIFF מקורי או ניסוי."),
        _t('Export full table preserves the scientific measurement CSV. Export visible rows follows the feature table filters. Export training CSV includes classified objects by default and uses Manual_Class_ID as its target. These exports must not overwrite the canonical measurements, verification masks or manual-label sidecar.',
           'Полный экспорт сохраняет научную таблицу; экспорт видимых строк учитывает фильтры таблицы. Обучающий CSV по умолчанию включает классифицированные объекты с целью Manual_Class_ID. Экспорт не должен перезаписывать исходные измерения, маски или файл ручных меток.',
           'ייצוא הטבלה המלאה שומר את טבלת המדידות המדעית. ייצוא שורות גלויות פועל לפי מסנני טבלת התכונות. ייצוא CSV לאימון כולל כברירת מחדל עצמים מסווגים ומשתמש ב־Manual_Class_ID כיעד. אין לדרוס בייצוא מדידות מקוריות, מסכות אימות או את קובץ התיוגים הידניים.'),
        _t('Predictors are Area, Aspect_Ratio, Solidity, Euler_Number, Endpoints and Branch_Points; calibrated Area_um2 is also included. Original Class_ID/Class_Name and source/object references stay as metadata and are excluded from predictor inputs. Group any future train/test split by source image or experiment to avoid information leakage.',
           'Признаки: Area, Aspect_Ratio, Solidity, Euler_Number, Endpoints, Branch_Points; при калибровке добавляется Area_um2. Исходные Class_ID/Class_Name и ссылки на объекты остаются метаданными, не входами модели. Будущее train/test-разбиение группируйте по исходнику или эксперименту, избегая утечки.',
           'התכונות הן Area, Aspect_Ratio, Solidity, Euler_Number, Endpoints ו־Branch_Points; כשקיים כיול נכלל גם Area_um2. Class_ID/Class_Name המקוריים והפניות למקור ולעצמים נשארים כמטא־נתונים ואינם קלט למודל. בחלוקת אימון ובדיקה עתידית יש לקבץ לפי תמונת מקור או ניסוי כדי למנוע זליגת מידע.'),
        _t('Changed annotations, active tile sets or measurement files make results stale. Recalculate before assigning types or exporting training data. Recalculation creates a new version; it must not silently reuse labels from different object identities.',
           'Изменение разметки, активных тайлов или измерений делает результаты неактуальными. Перед типизацией и обучающим экспортом пересчитайте. Это новая версия: нельзя незаметно переносить метки других ID объектов.',
           'שינוי תיוגים, קבוצת האריחים הפעילה או קובצי מדידה הופך תוצאות ללא עדכניות. יש לחשב מחדש לפני שיוך סוגים או ייצוא נתוני אימון. החישוב יוצר גרסה חדשה ואסור שישתמש בשקט בתיוגים של זהויות עצמים אחרות.'),
    ), parameters=('pixel_size_um',)),
    'workspace': dict(title=_t('Workspace, languages and image viewing', 'Панели, языки и просмотр', 'סביבת עבודה, שפות וצפייה'), paragraphs=(
        _t('Drag panel headers to rearrange them. Double-click a header to detach or dock its panel. The Panels menu shows hidden panels; Reset panel layout restores the stage arrangement. Panel layout is a display preference, separate from scientific settings.',
           'Перетаскивайте заголовки панелей. Двойной щелчок выносит или возвращает панель. Меню «Панели» показывает скрытые; сброс расположения восстанавливает этап. Расположение — настройка вида, отдельная от научных параметров.',
           'גררו כותרות לוחות כדי לסדר אותם מחדש. לחיצה כפולה על כותרת מנתקת או מעגנת את הלוח. תפריט הלוחות מציג לוחות שהוסתרו; איפוס הסידור מחזיר את מבנה השלב. סידור הלוחות הוא העדפת תצוגה נפרדת מההגדרות המדעיות.'),
        _t('Use the icon beside 1:1 or double-click to open a resizable image window. The same toolbar offers zoom, fit, measurement, display and export controls. Its buttons grow with the window and wrap in narrow panes. F11 enters or leaves full screen. Esc clears an active measurement.',
           'Значок рядом с 1:1 или двойной щелчок открывает окно с изменяемым размером. На общей панели доступны масштаб, вписывание, измерения, настройка просмотра и экспорт. Кнопки растут вместе с окном и переносятся в узких панелях. F11 включает и выключает полный экран. Esc очищает активное измерение.',
           'הסמל ליד 1:1 או לחיצה כפולה פותחים חלון תמונה שניתן לשנות את גודלו. בסרגל משותף יש תקריב, התאמה, מדידה, תצוגה וייצוא. הכפתורים גדלים עם החלון ועוברים שורה בלוחות צרים. F11 מפעיל או מסיים מסך מלא. Esc מנקה מדידה פעילה.'),
        _t('Zoom in with the mouse wheel. Press the wheel as a middle mouse button and drag to pan across the image. This also works while Ruler or Contour is active. If the image fits entirely, zoom in first.',
           'Прокрутите колёсико, чтобы увеличить изображение. Нажмите и удерживайте колёсико как среднюю кнопку мыши и перетаскивайте изображение. Этот жест работает и при включённой линейке или контуре. Если изображение целиком помещается в окне, сначала увеличьте масштаб.',
           'גלגלו את גלגלת העכבר כדי להגדיל את התמונה. לחצו על הגלגלת כלחצן האמצעי וגררו כדי להזיז את התמונה. הפעולה זמינה גם כשהסרגל או המתאר פעיל. אם כל התמונה נכנסת לחלון, הגדילו אותה תחילה.'),
        _t('The language selector changes interface text, help and number entry conventions. English is the default; Hebrew uses right-to-left layout. Stable parameter keys, class IDs, CSV column names and source filenames do not change with language.',
           'Язык меняет интерфейс, справку и формат ввода чисел. По умолчанию английский; иврит использует направление справа налево. Ключи параметров, ID классов, столбцы CSV и имена исходников не меняются.',
           'בורר השפה משנה טקסטים, עזרה ומוסכמות להזנת מספרים. אנגלית היא ברירת המחדל; עברית מוצגת מימין לשמאל. מפתחות פרמטרים קבועים, מזהי מחלקות, שמות עמודות CSV ושמות קובצי מקור אינם משתנים עם השפה.'),
    ), parameters=()),
    'settings': dict(title=_t('Factory defaults and current settings', 'Исходные и текущие настройки', 'ברירות מחדל והגדרות נוכחיות'), paragraphs=(
        _t('Factory default is the versioned installation baseline, not the last values saved in a project or edited in config.py. Current value is a snapshot of the main settings form. This help window only reads them and cannot modify your project or start a job.',
           'Фиксированное значение — версия исходной установки, а не последнее сохранённое в проекте или изменённое в config.py. Текущее значение — снимок формы. Справка только читает их, не меняет проект и не запускает задачи.',
           'ברירת המחדל המקורית היא בסיס ההתקנה בעל הגרסה, לא הערך האחרון שנשמר בפרויקט או נערך ב־config.py. הערך הנוכחי הוא צילום של טופס ההגדרות הראשי. חלון העזרה קורא בלבד ואינו משנה את הפרויקט או מתחיל משימה.'),
        _t('Reset parameters in the main window restores factory values for subsequent previews and runs. It does not delete files, undo exclusions, replace annotations or rewrite completed runs. Reset panel layout changes only panel arrangement. Use the parameter reference to compare units, ranges and examples before running.',
           'Сброс параметров в главном окне возвращает исходные значения для новых запусков. Он не удаляет файлы, не отменяет исключения, не заменяет разметку или готовые запуски. Сброс панелей меняет только расположение. Перед запуском сравните единицы, диапазоны и примеры справочника.',
           'איפוס פרמטרים בחלון הראשי מחזיר ערכים מקוריים לתצוגות ולריצות הבאות. הוא אינו מוחק קבצים, מבטל החרגות, מחליף תיוגים או משכתב ריצות שהושלמו. איפוס סידור הלוחות משנה רק את הסידור. השוו יחידות, טווחים ודוגמאות במדריך לפני ההפעלה.'),
    ), parameters=tuple(PARAMETER_REFERENCE)),
    'recovery': dict(title=_t('Errors, cancellation and recovery', 'Ошибки, остановка и восстановление', 'שגיאות, עצירה ושחזור'), paragraphs=(
        _t('Saved settings are checked for wrong types, zero or negative values where prohibited, NaN/infinity, and even morphology kernels. Safe loading backs up the original project and replaces only invalid fields with their factory values, preserving valid settings, sources and datasets. Review the recovery notice before starting a new run.',
           'Сохранённые настройки проверяются на неверный тип, запрещённые ноль/отрицательные значения, NaN/бесконечность и чётные ядра. Безопасная загрузка создаёт копию проекта и заменяет только неверные поля исходными значениями, сохраняя корректные настройки, исходники и наборы. Проверьте сообщение восстановления перед запуском.',
           'הגדרות שמורות נבדקות לסוגים שגויים, אפס או ערכים שליליים במקום שאסור, NaN או אינסוף וגרעיני מורפולוגיה זוגיים. טעינה בטוחה מגבה את הפרויקט המקורי ומחליפה רק שדות לא תקינים בערכי ברירת המחדל, תוך שמירת ההגדרות התקינות, המקורות והמערכים. בדקו את הודעת השחזור לפני ריצה חדשה.'),
        _t('Stop requests cancellation at a safe checkpoint. A currently executing indivisible filter can take time to finish; wait for the stopped status. Closing during a job asks whether to stop safely. Partial outputs are not complete results, and a missing worker result is treated as an error.',
           '«Остановить» запрашивает безопасную точку остановки. Неделимый фильтр может завершаться долго: дождитесь статуса. При закрытии предлагается безопасная остановка. Частичные файлы не считаются готовыми; отсутствие ответа обработчика считается ошибкой.',
           'עצירה מבקשת ביטול בנקודת בדיקה בטוחה. מסנן בלתי־ניתן לחלוקה שכבר פועל עשוי להימשך זמן; המתינו למצב עצור. סגירה במהלך משימה שואלת אם לעצור בבטחה. תוצרים חלקיים אינם תוצאות מלאות והיעדר תוצאת עובד נחשב שגיאה.'),
        _t('Use the job status and Log to identify the source, stage and error. Check source paths, channel/plane indices, positive numbers, odd morphology kernels, free disk space and annotation geometry. Fix the cause before repeating the stage. Verified completed preparation can be reused; interrupted work must pass completeness checks.',
           'Статус и журнал показывают исходник, этап и ошибку. Проверьте пути, канал/плоскость, положительные числа, нечётные ядра, свободное место и геометрию разметки. Исправьте причину и повторите этап. Готовая проверенная подготовка может использоваться снова; частичная проходит проверку полноты.',
           'היעזרו במצב המשימה וביומן כדי לזהות מקור, שלב ושגיאה. בדקו נתיבים, אינדקסי ערוץ ומישור, מספרים חיוביים, גרעיני מורפולוגיה אי־זוגיים, מקום פנוי וגאומטריית תיוג. תקנו את הסיבה לפני חזרה על השלב. ניתן להשתמש מחדש בהכנה שלמה שאומתה; עבודה שנקטעה חייבת לעבור בדיקות שלמות.'),
        _t('A second window cannot modify the same project. If results are stale, recalculate instead of forcing export. To compare experiments, use a new run or new output directory. Preserve native crops, valid masks and metadata; do not repair a dataset by deleting arbitrary files.',
           'Второе окно не может менять тот же проект. При неактуальных результатах пересчитайте, а не обходите экспорт. Для сравнения создайте новый запуск или каталог. Сохраняйте native, valid-маски и метаданные; не чините набор удалением случайных файлов.',
           'חלון נוסף אינו יכול לשנות את אותו פרויקט. אם התוצאות אינן עדכניות, חשבו מחדש במקום לכפות ייצוא. להשוואת ניסויים השתמשו בריצה או תיקיית פלט חדשה. שמרו פרגמנטים מקוריים, מסכות שיוך ומטא־נתונים; אין לתקן מערך באמצעות מחיקת קבצים שרירותית.'),
    ), parameters=('channel', 'plane', 'bridge_kernel_size', 'buffer_kernel_size')),
    'shortcuts': dict(title=_t('Keyboard shortcuts', 'Горячие клавиши', 'קיצורי מקשים'), paragraphs=(
        _t('F1: application or contextual help. Ctrl+F in this help: focus search. F11 on an image: open or close full screen. Esc in full screen: close it. Wheel and +/−: zoom; Fit to window: return to automatic fitting.',
           'F1 — общая или контекстная справка. Ctrl+F в справке — поиск. F11 на изображении — полный экран; Esc закрывает его. Колесо и +/− — масштаб, «По размеру окна» возвращает автовписывание.',
           'F1: עזרה כללית או הקשרית. Ctrl+F בחלון העזרה: מעבר לחיפוש. F11 בתמונה: פתיחה או סגירה של מסך מלא. Esc במסך מלא: סגירה. גלגלת ו־+/−: זום; התאמה לחלון מחזירה התאמה אוטומטית.'),
        _t('While reviewing objects, keys 1–6 assign types with stored IDs 0–5 and advance. Left/Right navigates visible objects; U finds the next unclassified object. Shortcuts do not type into a focused text-editing field; finish text entry before reviewing objects.',
           'При проверке объектов 1–6 назначают типы с ID 0–5 и переходят дальше. Стрелки выбирают видимые объекты, U ищет следующий без класса. При фокусе в поле ввода клавиши не назначают классы: сначала закончите ввод.',
           'בבדיקת עצמים, המקשים 1–6 משייכים סוגים במזהים 0–5 ומתקדמים. חצים מנווטים בין עצמים גלויים; U מוצא את הבא ללא סיווג. קיצורים אינם משייכים מחלקות כאשר שדה עריכת טקסט ממוקד; סיימו את ההקלדה לפני הבדיקה.'),
    ), parameters=()),
}

TOPICS['sources']['paragraphs'] += (
    _t('Saved filenames describe the operation and version: jobs/Job_prepare_001.json, jobs/Model_plan_001.json, .recovery/Settings_recovery_001/project.json and backups/Database_catalog_001. Metadata copies use Project_metadata_YYYY-MM-DD_001. Numbered names never replace an existing file. Internal UUIDs remain in JSON; random suffixes are used only for temporary staging files that disappear after completion. Old saved paths remain compatible.',
       'Имена сохранённых файлов описывают действие и версию: jobs/Job_prepare_001.json, jobs/Model_plan_001.json, .recovery/Settings_recovery_001/project.json и backups/Database_catalog_001. Копии метаданных называются Project_metadata_YYYY-MM-DD_001. Нумерация не перезаписывает существующие файлы. Внутренние UUID остаются в JSON; случайные суффиксы нужны только временным файлам, которые удаляются после завершения. Прежние сохранённые пути совместимы.',
       'שמות קבצים שמורים מתארים פעולה וגרסה: jobs/Job_prepare_001.json, jobs/Model_plan_001.json, .recovery/Settings_recovery_001/project.json ו־backups/Database_catalog_001. גיבויי מטא־נתונים נקראים Project_metadata_YYYY-MM-DD_001. המספור אינו דורס קובץ קיים. מזהי UUID נשארים ב־JSON; סיומות אקראיות משמשות רק קובצי ביניים שנמחקים בסיום. נתיבים שמורים ישנים נשארים תואמים.'),
    _t('Folder names describe their purpose: sources/<original-name>.tif, runs/Preparation_001/tiles/<image-name>, previews/<image-name>/Preview_001, annotations/<image-name>/Labels_001 and measurements/<image-name>/Measurement_001. Internal UUIDs remain in JSON, not folder names. Native, valid_masks and overview are required v3 artifacts; raw crops and animations are optional. Temporary staging folders exist only during an operation. Old managed names are migrated with an exact project.json backup and rename journal in backups/Storage_layout_001; a failed move rolls back. Scientific files, target IDs and measurement versions are not rewritten. Historical paths in provenance remain historical; the journal records their new locations.',
       'Названия описывают назначение: sources/<имя>.tif, runs/Preparation_001/tiles/<имя>, previews/<имя>/Preview_001, annotations/<имя>/Labels_001 и measurements/<имя>/Measurement_001. Внутренние UUID остаются в JSON, а не названиях папок. Native, valid_masks и overview нужны v3; raw-фрагменты и анимации необязательны. Временные папки существуют только во время операции. Старые имена управляемых папок меняются с точной копией project.json и журналом перемещений в backups/Storage_layout_001; при ошибке выполняется откат. Научные файлы, ID классов и версии измерений не переписываются. Старые пути в происхождении остаются историческими; журнал указывает новые места.',
       'שמות התיקיות מתארים מטרה: sources/<name>.tif, runs/Preparation_001/tiles/<name>, previews/<name>/Preview_001, annotations/<name>/Labels_001 ו־measurements/<name>/Measurement_001. מזהי UUID נשארים ב־JSON ולא בשמות תיקיות. native, valid_masks ו־overview דרושים ל־v3; חיתוכים גולמיים והנפשות אופציונליים. תיקיות ביניים קיימות רק בזמן פעולה. שמות ישנים משתנים עם גיבוי מדויק של project.json ויומן העברות ב־backups/Storage_layout_001; כישלון מבצע החזרה לאחור. קבצים מדעיים, מזהי מחלקות וגרסאות מדידה אינם נכתבים מחדש. נתיבי עבר בתיעוד נשארים היסטוריים והיומן מציין מיקומים חדשים.'),
    _t('TIFF slice/frame (formerly Stack plane) is a zero-based index within a Z-depth stack, time sequence T or image sequence I. It is separate from the channel index. For example, a 10-slice Z stack accepts 0–9, and 3 selects the fourth slice. A plain YX or RGB YXS TIFF contains one 2D plane: index 0 is not used and is read-only. Selection processes one plane, without projection or merging; multiple nontrivial stack axes remain unsupported and require explicit export.',
       '«Срез/кадр TIFF» (прежнее Stack plane) — индекс с 0 в стеке глубины Z, последовательности времени T или изображений I. Это не номер канала. Например, в стеке из 10 срезов допустимы 0–9, а 3 выбирает четвёртый. Обычный YX или RGB YXS TIFF содержит одну 2D-плоскость: 0 не используется и доступен только для чтения. Выбирается одна плоскость без проекции или объединения; несколько нетривиальных осей стека по-прежнему требуют явного экспорта.',
       'חתך/פריים ב־TIFF (לשעבר Stack plane) הוא אינדקס מ־0 בערימת עומק Z, סדרת זמן T או סדרת תמונות I, בנפרד ממספר הערוץ. לדוגמה, בערימה בת 10 חתכים מותר 0–9, והערך 3 בוחר את הרביעי. TIFF רגיל מסוג YX או RGB YXS מכיל מישור דו־ממדי אחד: 0 אינו בשימוש והשדה לקריאה בלבד. מעובד מישור אחד ללא הטלה או מיזוג; כמה צירי ערימה לא־טריוויאליים עדיין דורשים ייצוא מפורש.'),
    _t('From TIFF metadata resolves calibration separately for every source and displays the selected source value as read-only. Supported evidence is OME PhysicalSizeX/Y with units (the OME default unit is µm), or ImageJ physical unit with reciprocal X/YResolution. For example, 400 nm/px becomes 0.4 µm/px. X and Y must be positive, finite and equal within relative tolerance 1e-6; unequal pixels, missing/unsupported units and generic print DPI are not used automatically. Nominal objective magnification is never pixel calibration. Unresolved sources remain in pixels. Manual/source pixels overrides metadata for the whole batch; 0 means uncalibrated. Resolved values and their origin are saved with each new run or measurement, without changing older results or factory defaults.',
       '«Из метаданных TIFF» определяет калибровку отдельно для каждого исходника и показывает выбранное значение только для чтения. Поддерживаются OME PhysicalSizeX/Y с единицами (единица OME по умолчанию — мкм) либо физическая единица ImageJ с обратными X/YResolution. Например, 400 нм/px дают 0.4 мкм/px. X и Y должны быть конечными, положительными и равными с относительным допуском 1e-6; неодинаковые пиксели, отсутствующие/неподдерживаемые единицы и обычный печатный DPI автоматически не применяются. Увеличение объектива не является калибровкой пикселя. Без надёжных данных остаются пиксели. Ручной режим заменяет метаданные для всего пакета; 0 означает отсутствие калибровки. Итоговые значения и происхождение сохраняются с новым запуском или измерением, не меняя прежние результаты и заводской справочник.',
       'ממטא־נתוני TIFF פותר כיול בנפרד לכל מקור ומציג את ערך המקור הנבחר לקריאה בלבד. נתמכים OME PhysicalSizeX/Y עם יחידות (ברירת המחדל של OME היא מיקרומטר), או יחידה פיזית של ImageJ עם X/YResolution ההפוכים. לדוגמה, 400 ננומטר לפיקסל הם 0.4 מיקרומטר לפיקסל. X ו־Y חייבים להיות סופיים, חיוביים ושווים בסבולת יחסית 1e-6; פיקסלים לא שווים, יחידות חסרות/לא נתמכות ו־DPI הדפסה רגיל אינם משמשים אוטומטית. הגדלת העדשה אינה כיול פיקסל. מקורות ללא ראיה מתאימה נשארים בפיקסלים. מצב ידני מחליף מטא־נתונים לכל האצווה; 0 משאיר ללא כיול. ערכים שנפתרו ומקורם נשמרים עם ריצה או מדידה חדשה ללא שינוי תוצאות ישנות או ברירות מחדל מקוריות.'),
    _t('Choose an unused project folder name. If a folder already exists, New project asks for another name rather than claiming its contents. Use Open project to continue an existing project.json; cancelling either creation dialog leaves the current project unchanged.',
       'Выберите свободное имя папки проекта. Если папка уже существует, «Новый проект» просит другое имя и не присваивает её содержимое. Продолжить существующий project.json можно через «Открыть проект»; отмена любого диалога создания сохраняет текущий проект.',
       'בחרו שם פנוי לתיקיית הפרויקט. אם התיקייה כבר קיימת, יצירת פרויקט מבקשת שם אחר ואינה משתלטת על תוכנה. השתמשו בפתיחת פרויקט כדי להמשיך project.json קיים; ביטול אחד מדו־שיח היצירה משאיר את הפרויקט הנוכחי ללא שינוי.'),
    _t('Open starts in data/projects. Open your project folder and select project.json. If the project is stored elsewhere, browse to that location. Cancelling the dialog keeps the current project open.',
       'Диалог «Открыть» начинается в data/projects. Откройте папку нужного проекта и выберите project.json. Если проект сохранён в другом месте, перейдите туда. Отмена диалога оставляет текущий проект открытым.',
       'החלון פתיחה נפתח בתיקייה data/projects. פתחו את תיקיית הפרויקט ובחרו project.json. אם הפרויקט שמור במקום אחר, נווטו לשם. ביטול החלון משאיר את הפרויקט הנוכחי פתוח.'),
    _t('New project asks for a folder name and a parent directory, then creates <parent>/<name>/project.json. Each project owns its sources, previews, runs (tiles, raw crops and animations), imported datasets, annotations, measurements, object crops and job logs. The initial empty project is data/projects/default/project.json; TIFFs are never added automatically.',
       '«Новый проект» запрашивает имя папки и родительский каталог, затем создаёт <каталог>/<имя>/project.json. У каждого проекта свои исходники, предпросмотры, запуски (тайлы, raw-фрагменты и анимации), импортированные наборы, разметка, измерения, фрагменты объектов и журналы. Начальный пустой проект — data/projects/default/project.json; TIFF не добавляются автоматически.',
       'פרויקט חדש מבקש שם תיקייה ותיקיית אב ויוצר <parent>/<name>/project.json. לכל פרויקט מקורות, תצוגות מקדימות, ריצות (אריחים, חיתוכים גולמיים והנפשות), מערכים מיובאים, תיוגים, מדידות, חיתוכי עצמים ויומנים משלו. הפרויקט הריק הראשוני הוא data/projects/default/project.json; קובצי TIFF אינם נוספים אוטומטית.'),
    _t('Add TIFF copies the exact source bytes into the project in a background job. This needs additional disk space and can take time for large files. Stop cancels the current copy; fully imported earlier files remain available. An incomplete copy is not registered. The original path is kept as provenance. An invalid parameter draft is preserved on screen and is never saved by importing sources.',
       '«Добавить TIFF» копирует точные исходные байты в проект фоновым заданием. Нужны дополнительное место и время для больших файлов. «Остановить» отменяет текущую копию; ранее завершённые файлы остаются. Незавершённая копия не регистрируется. Исходный путь сохраняется как происхождение. Некорректный черновик параметров остаётся на экране и не сохраняется при импорте.',
       'הוספת TIFF מעתיקה את בתי המקור בדיוק לפרויקט במשימת רקע. נדרשים מקום נוסף וזמן לקבצים גדולים. עצירה מבטלת את ההעתקה הנוכחית; קבצים שכבר יובאו נשארים זמינים. העתקה חלקית אינה נרשמת. נתיב המקור נשמר כתיעוד. טיוטת פרמטרים לא תקינה נשמרת על המסך ואינה נשמרת לפרויקט בזמן הייבוא.'),
)
TOPICS['tiles']['paragraphs'] += (
    _t('Open prepared tiles copies the selected v3 dataset into this project before review. Exclude, Restore and rebuilt maps act on that private copy, leaving the external dataset unchanged. Import needs disk space; linked folders or files are refused. The manifest and saved native pixels determine resolution, not the size of a screen preview.',
       '«Открыть тайлы» сначала копирует выбранный набор v3 в проект. Исключение, возврат и обновление карт работают с этой копией, сохраняя внешний набор. Импорт требует места; ссылки на файлы или папки не принимаются. Разрешение задаётся manifest и сохранёнными native-пикселями, а не размером предпросмотра.',
       'פתיחת אריחים מוכנים מעתיקה תחילה את מערך v3 הנבחר לפרויקט. החרגה, שחזור ובניית מפות פועלים על ההעתק הפרטי ומשאירים את המערך החיצוני ללא שינוי. הייבוא דורש מקום; קישורים לקבצים או לתיקיות נדחים. המטא־נתונים ופיקסלי המקור השמורים קובעים את הרזולוציה, לא גודל התצוגה המקדימה.'),
    _t('Individual tile tabs load the saved image grid directly up to 32 MP. In Overview, 1:1 or Detailed boundary map generates a separate filtered PNG with source dimensions and current active-tile boundaries. This can take time and substantial memory and disk space.',
       'Вкладки отдельных тайлов до 32 Мп загружают сохранённую сетку целиком. В «Карте» кнопки 1:1 и «Подробная карта границ» создают отдельный отфильтрованный PNG в размерах исходника с актуальными границами тайлов. Для этого могут потребоваться время, память и место.',
       'לשוניות אריחים בודדים עד 32 מגה־פיקסל טוענות ישירות את סריג התמונה השמור. בסקירה, 1:1 או מפת גבולות מפורטת יוצרים PNG מסונן נפרד במידות המקור עם גבולות האריחים הפעילים. ייתכן שיידרשו זמן, זיכרון ושטח דיסק.'),
)
TOPICS['tile_editor'] = dict(title=_t('Tile editor and active versions', 'Редактор тайлов и активные версии', 'עורך אריחים וגרסאות פעילות'), paragraphs=(
    _t('Open a Model or Native tile with 1:1, or choose Open object’s tile in Results. For v3 editing, the separate window opens native source pixels and labels that coordinate space. Choose Edit tile. Radius and rectangle bounds use those source pixels. The model canvas is regenerated from the edited native pixels when saving. Editing requires a grayscale PNG and a matching validity mask, each up to 32 megapixels. Use Pan to move around and the wheel to zoom.',
       'Откройте модельный или native-тайл кнопкой 1:1 либо выберите «Открыть тайл объекта» в «Результатах». Для редактирования v3 отдельное окно показывает native-пиксели исходника с явной подписью масштаба. Нажмите «Редактировать тайл…». Радиус и границы прямоугольника заданы в этих исходных пикселях. При сохранении модельное поле строится из отредактированного native. Нужен PNG в градациях серого и соответствующая маска, каждый до 32 Мп. Для перемещения выберите «Панорама», для масштаба используйте колесо.',
       'פתחו אריח מודל או מקור באמצעות 1:1, או בחרו פתיחת אריח העצם בתוצאות. לעריכת v3 החלון הנפרד מציג פיקסלי מקור עם כיתוב מפורש של קנה המידה. בחרו עריכת אריח. הרדיוס וגבולות המלבן נמדדים בפיקסלי המקור האלה. בשמירה תמונת המודל נוצרת מפיקסלי המקור הערוכים. נדרשים PNG בגוני אפור ומסכה תואמת, עד 32 מגה־פיקסל כל אחד. השתמשו במצב הזזה ובגלגלת לשינוי הזום.'),
    _t(f'Use Straight erase for a line between two points or Eraser (E) for freehand erase. Drag across the part you want to remove. Erased pixels become black padding with value 0 and are marked invalid. Erase radius is 0–150 px. The factory value is {EDITOR_DEFAULTS["erase_radius"]} px. Radius 0 gives a one-pixel stroke. Editor factory values come from catalog version {EDITOR_DEFAULTS_VERSION}.',
       f'Для отрезка между двумя точками выберите «Стереть по прямой». Чтобы стереть от руки, выберите «Ластик (E)». Проведите мышью по нужному участку. Стёртые пиксели заполняются чёрным паддингом со значением 0 и помечаются недействительными. Радиус стирания — 0–150 px, заводское значение — {EDITOR_DEFAULTS["erase_radius"]} px. При радиусе 0 ширина следа равна одному пикселю. Заводские значения редактора берутся из каталога версии {EDITOR_DEFAULTS_VERSION}.',
       f'בחרו מחיקה בקו ישר בין שתי נקודות, או מחק (E) עבור מחיקה ביד חופשית. גררו על החלק להסרה. פיקסלים שנמחקו הופכים לריפוד שחור בערך 0 ומסומנים כלא תקפים. רדיוס המחיקה הוא 0–150 פיקסלים. ערך היצרן הוא {EDITOR_DEFAULTS["erase_radius"]}. רדיוס 0 יוצר קו בעובי פיקסל אחד. ערכי היישום של העורך מגיעים מקטלוג גרסה {EDITOR_DEFAULTS_VERSION}.'),
    _t('To remove an entire side, choose Cut by line and drag a straight line. It extends to the edges of the tile. Click the side you want to remove or use Smaller side to select the side with fewer valid pixels. If the sides tie or one side is empty, choose by clicking. Check the highlighted area and choose Apply. The selected pixels become black padding and are removed from the copy’s validity mask. Pixel centers on the line belong to the retained area.',
       'Чтобы убрать целую сторону, выберите «Отсечь по линии» и проведите прямую. Она продлевается до краёв тайла. Щёлкните со стороны удаления или нажмите «Меньшая сторона», чтобы выбрать часть с меньшим числом действительных пикселей. При равенстве или пустой стороне выберите вручную. Проверьте подсвеченную область и нажмите «Применить». Выбранные пиксели станут чёрным паддингом и будут исключены из маски копии. Пиксели с центром на линии входят в сохраняемую область.',
       'כדי להסיר צד שלם, בחרו חיתוך לפי קו וגררו קו ישר. הקו מתארך עד לשולי האריח. לחצו בצד שתרצו להסיר או בחרו הצד הקטן יותר לפי מספר הפיקסלים התקפים. כשמספר הפיקסלים שווה או כשצד אחד ריק, בחרו בלחיצה. בדקו את האזור המודגש ובחרו החלה. הפיקסלים שנבחרו יהפכו לריפוד שחור ויוסרו ממסכת התקפות של העותק. פיקסלים שמרכזם על הקו שייכים לאזור הנשמר.'),
    _t('For uneven background, choose Local background and drag a rectangle. White top-hat subtracts an estimated background without normalizing intensities. The filter reads neighboring valid pixels and writes inside the rectangle. Radius is 1–85 px and starts at 12 px, which gives a 25 × 25 elliptical kernel. Wide bright structures can also become dimmer.',
       'Для неровного фона выберите «Удалить фон локально» и выделите прямоугольник. White top-hat вычитает оценку фона без нормализации яркости. Фильтр учитывает соседние действительные пиксели и записывает результат внутри прямоугольника. Радиус — 1–85 px, начальное значение — 12 px. Оно задаёт эллиптическое ядро 25 × 25. Широкие яркие структуры тоже могут потускнеть.',
       'לרקע לא אחיד בחרו הסרת רקע מקומית וגררו מלבן. מסנן white top-hat מחסר אומדן רקע ללא נרמול עוצמות. המסנן קורא פיקסלים תקפים סמוכים וכותב בתוך המלבן. הרדיוס הוא 1–85 פיקסלים ומתחיל ב־12, עבור גרעין אליפטי של 25 × 25. גם מבנים בהירים רחבים עלולים להיחלש.'),
    _t('For a dark result after background removal, choose Brightness (gamma). Adjust the slider and preview the outlined background rectangle or the whole tile, then choose Apply. The range is 0.25–4.00. At gamma 1.00 the mapping is the identity, above 1.00 it brightens, and below 1.00 it darkens. Gamma maps normalized intensity x to x^(1/gamma) over the fixed bit-depth range and rounds down to a saved integer. For example, gamma 2.00 maps 8-bit intensity 64 to 127. The correction uses valid pixels. Min–max normalization maps the darkest and brightest sampled values to the ends of the output range.',
       'Если после удаления фона участок стал слишком тёмным, выберите «Яркость (гамма)». Настройте ползунок, оцените предпросмотр для выделенного рамкой прямоугольника или всего тайла и нажмите «Применить». Диапазон — 0,25–4,00. Значение 1,00 соответствует исходной яркости, выше 1,00 изображение светлеет, ниже — темнеет. Гамма переводит яркость x на шкале от 0 до 1 в x^(1/gamma) и округляет записываемое значение вниз. Например, при гамме 2,00 яркость 64 на 8-битной шкале становится 127. Коррекция действует на действительные пиксели. При min–max-нормализации края выходной шкалы задают самая тёмная и самая яркая точки выборки.',
       'אם התוצאה כהה אחרי הסרת רקע, בחרו בהירות (גאמה). כוונו את המחוון, בדקו תצוגה מקדימה של המלבן המסומן או של האריח כולו, ובחרו החלה. הטווח הוא 0.25–4.00. גאמה 1.00 היא מיפוי זהות, ערך גבוה יותר מבהיר וערך נמוך יותר מכהה. גאמה ממפה עוצמה מנורמלת x ל־x^(1/gamma) בטווח הקבוע של עומק הסיביות ומעגלת כלפי מטה לערך השמור. לדוגמה, גאמה 2.00 ממפה עוצמה 64 ב־8 סיביות ל־127. התיקון פועל על פיקסלים תקפים. בנרמול מינימום–מקסימום הערך הכהה ביותר והבהיר ביותר במדגם קובעים את קצות טווח הפלט.'),
    _t('To brighten any rectangle directly, choose Brightness (gamma), set its region to Draw rectangle and drag across the image. A cyan frame shows the selected bounds. Adjust gamma, inspect the preview and choose Apply. You can drag a replacement rectangle before applying. Esc or Cancel preview clears the selection. Whole tile and Last background region remain available in the same region list.',
       'Для гаммы в произвольном прямоугольнике выберите «Яркость (гамма)», затем область «Выделить прямоугольник» и протяните мышью по изображению. Бирюзовая рамка показывает границы. Настройте гамму, проверьте предпросмотр и нажмите «Применить». До применения можно выделить другой прямоугольник. Esc или «Сбросить выбор» очищают выделение. В том же списке доступны «Весь тайл» и «Последняя область фона».',
       'להבהרת מלבן כלשהו בחרו בהירות (גאמה), הגדירו את האזור לבחירת מלבן וגררו על התמונה. מסגרת טורקיז מציגה את הגבולות. כוונו גאמה, בדקו תצוגה מקדימה ובחרו החלה. אפשר לגרור מלבן חלופי לפני ההחלה. Esc או איפוס הבחירה מנקים את הבחירה. באותה רשימה זמינים כל האריח ואזור הרקע האחרון.'),
    _t('Use Show original to compare with the image opened for this editing session at the same zoom, and Undo or Ctrl+Z to reverse recent operations. The in-memory undo history uses up to 128 MiB. Save tile publishes a complete native/model version, valid_mask.png and edit.json under tile_edits/<tile>/Edit_001 within the dataset. It becomes the active version displayed in Tile images and used by the next measurement.',
       'Нажмите «Показать оригинал» для сравнения с изображением при открытии редактора в том же масштабе. «Отменить» или Ctrl+Z отменяют недавние операции. История отмены занимает до 128 МиБ в памяти. «Сохранить тайл» записывает согласованную версию native/model, valid_mask.png и edit.json в tile_edits/<тайл>/Edit_001 внутри набора. Она становится активной, отображается в Tile images и используется при следующем измерении.',
       'בחרו הצגת המקור כדי להשוות באותו זום לתמונה שנפתחה בתחילת העריכה, וביטול פעולה או Ctrl+Z כדי לבטל פעולות אחרונות. היסטוריית הביטול בזיכרון מוגבלת ל־128 MiB. שמירת האריח מפרסמת גרסת מקור ומודל מלאה, valid_mask.png ו־edit.json תחת tile_edits/<tile>/Edit_001 בתוך המערך. היא הופכת לגרסה הפעילה המוצגת בתמונות האריח ומשמשת במדידה הבאה.'),
    _t('After saving an edited tile, previous measurements become stale. Run measurement again in Segmentation, inspect the new object crops in Results and assign their manual types. Export training data or train the model from that current measurement. Random Forest receives the measured numerical predictors and reviewed targets. Historical measurements, manual labels and model reports belong to their recorded versions.',
       'После сохранения правки прежние измерения становятся неактуальными. Повторите измерение в «Сегментации», проверьте новые фрагменты объектов в «Результатах» и назначьте им ручные типы. Экспортируйте обучающие данные или обучайте модель по этой актуальной версии. Random Forest получает измеренные числовые признаки и проверенные целевые метки. Исторические измерения, ручные метки и отчёты моделей относятся к своим сохранённым версиям.',
       'אחרי שמירת אריח ערוך המדידות הקודמות אינן עדכניות. מדדו שוב בפילוח, בדקו את פרגמנטי העצמים החדשים בתוצאות ושייכו להם סוגים ידניים. ייצאו נתוני אימון או אמנו מודל מתוך המדידה העדכנית. Random Forest מקבל תכונות מספריות מדודות ויעדים שנבדקו. מדידות היסטוריות, תוויות ידניות ודוחות מודלים שייכים לגרסאות שתועדו בהם.'),
    _t('For a version saved by the earlier copy-only editor, select the tile and choose Use saved edit, then select its edit.json. The app checks tile identity, source checksums, dimensions and scale before activating it. Native exports and model exports with one source pixel per model pixel can be imported. For an older reduced model export, redo the edits on native pixels. Restore prepared tile selects the prepared pixels again. Both actions require a new measurement before training.',
       'Для версии из прежнего редактора копий выберите тайл, нажмите «Использовать сохранённую правку…» и укажите её edit.json. Приложение проверяет идентичность тайла, контрольные суммы исходника, размеры и масштаб. Поддерживаются native-экспорты и модельные экспорты с одним исходным пикселем на пиксель модели. Для старого уменьшенного модельного экспорта повторите правки на native. «Вернуть подготовленный тайл» снова выбирает подготовленные пиксели. После обоих действий выполните новое измерение перед обучением.',
       'לגרסה שנשמרה בעורך הקודם לייצוא עותקים, בחרו אריח, שימוש בעריכה שמורה ואז את edit.json שלה. היישום בודק זהות אריח, סכומי ביקורת של המקור, ממדים וקנה מידה לפני ההפעלה. אפשר לייבא ייצוא מקור וייצוא מודל עם פיקסל מקור אחד לכל פיקסל מודל. לייצוא מודל מוקטן ישן בצעו שוב את העריכות בפיקסלי המקור. שחזור האריח המוכן בוחר שוב בפיקסלים שהוכנו. שתי הפעולות דורשות מדידה חדשה לפני אימון.'),
), parameters=())
TOPICS['tiles']['paragraphs'] += (
    _t('An active edited version is shown in Model, Native, Ownership and Polygons. A cached overview can still show its earlier pixels. When the map warns that it predates active edits, choose Rebuild overview. Rebuilt and detailed maps use the active edited pixels. Map selection follows the prepared geometry, so an erased region can still select its tile.',
       'Активная правка показана в «Модель», Native, «Принадлежность» и «Полигоны». Сохранённая обзорная карта может показывать прежние пиксели. Если карта сообщает, что создана до активных правок, нажмите «Обновить карту». Перестроенная и подробная карты используют активные пиксели. Нажатие на карту выбирает тайл по подготовленной геометрии, в том числе в стёртом участке.',
       'הגרסה הערוכה הפעילה מוצגת במודל, במקור, בשיוך ובמצולעים. סקירה שמורה יכולה להציג פיקסלים קודמים. כשהמפה מודיעה שנוצרה לפני העריכות הפעילות, בחרו בנייה מחדש של הסקירה. מפות שנבנות מחדש ומפות מפורטות משתמשות בפיקסלים הפעילים. הבחירה במפה פועלת לפי הגאומטריה שהוכנה, כך שגם אזור שנמחק יכול לבחור את האריח שלו.'),
)
TOPICS['results']['paragraphs'] += (
    _t('In Results → Charts → Histogram, Automatic uses logarithmic intervals for Area and Area_um2. Linear intervals have equal widths. Logarithmic intervals advance by a constant factor, so small and large objects can be viewed on the same plot. The X axis retains source px² or µm² and the Y axis counts objects. Use 1–200 bins or switch the scale explicitly. Logarithmic intervals use positive values and the summary reports any omitted values at or below zero.',
       'В «Результатах → Графики → Гистограмма» автоматическая шкала использует логарифмические интервалы для Area и Area_um2. Линейные интервалы имеют одинаковую ширину. В логарифмической шкале границы растут в одинаковое число раз, поэтому видны и мелкие, и крупные объекты. По оси X остаётся площадь в исходных px² или мкм², по оси Y — число объектов. Можно задать от 1 до 200 интервалов или выбрать шкалу вручную. На логарифмической шкале учитываются положительные значения, а сводка сообщает, сколько значений ≤ 0 пропущено.',
       'בתוצאות ← תרשימים ← היסטוגרמה, הסולם האוטומטי משתמש במרווחים לוגריתמיים עבור Area ו־Area_um2. למרווחים ליניאריים יש רוחב שווה. במרווחים לוגריתמיים הגבולות גדלים ביחס קבוע, כך שניתן לראות עצמים קטנים וגדולים יחד. ציר X נשאר בפיקסלי מקור בריבוע או במיקרומטרים רבועים וציר Y סופר עצמים. אפשר לבחור 1–200 תאים או לקבוע את הסולם במפורש. בסולם לוגריתמי נכללים ערכים חיוביים והסיכום מציין כמה ערכים שאינם חיוביים הושמטו.'),
    _t('Choose Classes by image to count manual classes for one TIFF measurement or one of its tiles. The image selector shows the measurement version when available. Multiple measurements of the same TIFF appear as separate choices. The bars show the number of objects in each saved manual class. The summary gives the number of measured objects without a manual class.',
       'Выберите «Классы по снимкам», чтобы посчитать ручные классы по одной версии измерений TIFF или по одному из её тайлов. Версия указана в списке снимков, если она доступна. Несколько измерений одного TIFF показаны отдельными пунктами. Столбцы показывают число объектов с каждой сохранённой ручной меткой. В сводке указано число измеренных объектов без ручного класса.',
       'בחרו מחלקות לפי תמונה כדי לספור מחלקות ידניות בגרסת מדידה אחת של TIFF או באריח אחד מתוכה. גרסת המדידה מוצגת בבורר התמונות כאשר היא זמינה. מדידות מרובות של אותו TIFF מוצגות כאפשרויות נפרדות. העמודות מציגות את מספר העצמים בכל מחלקה ידנית שמורה. הסיכום מציין את מספר העצמים שנמדדו ללא מחלקה ידנית.'),
    _t('In Results → Charts, click Open charts in a separate window. The new window starts with the current dataset, plot, axes and histogram bins. You can resize or maximize it and explore another plot independently. The open chart keeps the data from the moment it was opened.',
       'В «Результатах → Графики» нажмите «Открыть графики в отдельном окне…». В новом окне сохраняются выбранный набор, вид графика, оси и число интервалов гистограммы. Окно можно увеличить или развернуть и независимо менять график. Открытое окно показывает данные на момент открытия.',
       'בתוצאות ← תרשימים לחצו על פתיחת התרשימים בחלון נפרד. החלון נפתח עם מערך הנתונים, סוג התרשים, הצירים ומספר תאי ההיסטוגרמה הנוכחיים. ניתן להגדיל אותו ולבחון בו תרשים אחר באופן עצמאי. הנתונים בחלון משקפים את רגע הפתיחה.'),
    _t("Select an object and choose Open object's tile. Its exact measured mask appears in gold with an ID and frame. Highlight object toggles the overlay; zoom and full screen retain its position. New measurements save exact masks and native coordinates separately from predictors. Missing native data uses a labelled model canvas with scale mapping. Old grayscale crops can be located by a unique exact foreground-intensity match; the caption identifies this method. Missing or ambiguous matches show the whole tile and request recalculation. Viewing does not change measurements or labels.",
       'Выберите объект и нажмите «Открыть тайл объекта». Измеренная маска выделена золотым цветом с ID и рамкой. Флажок «Подсветить объект» скрывает и показывает выделение; масштаб и полный экран сохраняют его положение. Новые измерения сохраняют маски и native-координаты отдельно от признаков. При отсутствии native используется подписанное модельное поле с пересчётом масштаба. Старый серый фрагмент можно найти по единственному точному совпадению яркостей; способ указан в подписи. При неоднозначном или отсутствующем совпадении показан весь тайл с предложением пересчёта. Просмотр не меняет измерения и классы.',
       'בחרו עצם ופתחו את האריח שלו. מסכת המדידה מודגשת בזהב עם מזהה ומסגרת. תיבת הדגשת האובייקט מסתירה או מציגה אותה; המיקום נשמר בזום ובמסך מלא. מדידות חדשות שומרות מסכות וקואורדינטות מקור בנפרד מהתכונות. כשאין מקור, מוצג אריח מודל מסומן עם מיפוי קנה המידה. אפשר לאתר חיתוך אפור ישן בהתאמת עוצמות מדויקת ויחידה; השיטה מצוינת בכיתוב. אם אין התאמה יחידה, מוצג האריח המלא עם בקשה לחשב שוב. הצפייה אינה משנה מדידות או סיווגים.'),
)
TOPICS['tile_editor']['paragraphs'] += (
    _t(f'Brush (B) draws a continuation. Use the pipette to sample the intensity or enter it manually. Click Pick intensity, then a valid tube pixel. It reads the current native value: 0–255 for 8-bit or 0–65535 for 16-bit, even when the display uses 8-bit. Drag to paint, or enter Intensity manually. Brush radius is 0–150 source pixels, factory {EDITOR_DEFAULTS["paint_radius"]} px (editor catalog {EDITOR_DEFAULTS_VERSION}); radius 0 draws a one-pixel line. Only currently valid pixels can be painted. Undo restores a stroke. Show original compares with the opened version; Save tile activates the edit.',
       f'«Кисть (B)» дорисовывает трубочку. Яркость можно ввести вручную, а пипетка считывает её с пикселя. Нажмите «Взять яркость пипеткой» и щёлкните по действительному пикселю трубочки. Считывается текущая native-яркость: 0–255 для 8 бит или 0–65535 для 16 бит, даже если просмотр использует 8 бит. Рисуйте этой яркостью или введите её вручную. Радиус кисти 0–150 исходных пикселей, заводской — {EDITOR_DEFAULTS["paint_radius"]} px (каталог редактора {EDITOR_DEFAULTS_VERSION}); радиус 0 даёт линию толщиной один пиксель. Кисть действует внутри текущей действительной области. «Отменить» возвращает состояние до штриха. «Показать оригинал» сравнивает с открытой версией; «Сохранить тайл» активирует правку.',
       f'מברשת (B) מציירת המשך. אפשר להשתמש בכלי טפטפת לדגימה או להזין עוצמה ידנית. לחצו על דגימת בהירות ואז על פיקסל צינורית תקף. נקרא ערך המקור הנוכחי: 0–255 ב־8 סיביות או 0–65535 ב־16 סיביות, גם כשהתצוגה היא 8 סיביות. גררו לציור או הזינו עוצמה ידנית. רדיוס המברשת 0–150 פיקסלי מקור, ברירת המחדל {EDITOR_DEFAULTS["paint_radius"]} (קטלוג עורך {EDITOR_DEFAULTS_VERSION}); רדיוס 0 מצייר קו ברוחב פיקסל. מציירים רק בפיקסלים תקפים. ביטול פעולה משחזר את המצב לפני הקו. הצגת המקור משווה לגרסה שנפתחה; שמירת האריח מפעילה את העריכה.'),
    _t('Drawing adds manually synthesized signal and can change components, area, topology and training predictors. The history records strokes, radii, intensities, sample positions and a synthetic-signal flag, which persists in subsequent versions. Recalculate and inspect masks before assigning classes. A drawn segment is a manual correction rather than an observed biological structure.',
       'Дорисовка добавляет ручной синтетический сигнал и может изменить компоненты, площадь, топологию и признаки для обучения. История сохраняет штрихи, радиусы, яркости, точки образцов и флаг синтетического сигнала, который переходит в последующие версии. Пересчитайте и проверьте маски перед назначением классов. Дорисованный сегмент является ручной коррекцией, а не наблюдаемой биологической структурой.',
       'הציור מוסיף אות סינתטי ידני ועשוי לשנות רכיבים, שטח, טופולוגיה ותכונות אימון. התיעוד שומר קווים, רדיוסים, עוצמות, נקודות דגימה ודגל אות סינתטי שנשמר בגרסאות הבאות. חשבו מחדש ובדקו מסכות לפני שיוך מחלקות. מקטע מצויר הוא תיקון ידני ולא מבנה ביולוגי שנצפה.'),
)
TOPICS['preparation']['paragraphs'] += (
    _t('Saved previews for the selected TIFF reopen automatically. If there is no saved preview, Source channel loads a quick whole-image view of the selected channel and plane. Use Preview selected TIFF above the tabs to compute Filtering and Protective mask on the full-resolution plane. Compare side by side shows the source and filter result together after that run.',
       'Сохранённые предпросмотры выбранного TIFF открываются автоматически. Если их ещё нет, «Исходный канал» загружает быстрый обзор выбранного канала и плоскости. Нажмите «Предпросмотр выбранного TIFF» над вкладками, чтобы рассчитать «Фильтрацию» и «Защитную маску» в исходном разрешении. После расчёта «Сравнить рядом» показывает исходник и фильтрацию вместе.',
       'תצוגות שמורות של קובץ TIFF שנבחר נפתחות אוטומטית. כשאין תצוגה שמורה, ערוץ המקור טוען סקירה מהירה של הערוץ והמישור שנבחרו. לחצו על תצוגה מקדימה של TIFF מעל הלשוניות כדי לחשב סינון ומסכת הגנה ברזולוציה המקורית. לאחר החישוב השוואה זו לצד זו מציגה את המקור ואת תוצאת הסינון.'),
    _t('A flat morphology kernel specifies a neighborhood, not averaging weights. Erosion takes the minimum, dilation the maximum. Opening is erosion then dilation; white top-hat subtracts the opening from grayscale intensities. Closing is dilation then erosion. Protective closing (factory 17×17 ellipse) acts on the binary routing mask; 5×5 dilation adds clearance. Automatic detection separately uses 3×3 closing to find candidate contours. Local thresholding creates the final measurement mask.',
       'Плоское ядро морфологии задаёт окрестность, а не веса усреднения. Эрозия берёт минимум, дилатация — максимум. Открытие выполняет эрозию, затем дилатацию; white top-hat вычитает открытие из серого изображения. Замыкание выполняет дилатацию, затем эрозию. Защитное замыкание (заводской эллипс 17×17) действует на бинарную маску маршрутизации, а расширение 5×5 добавляет запас. Авто-поиск отдельно использует замыкание 3×3 для контуров кандидатов. Окончательную маску измерений создаёт локальный порог.',
       'גרעין מורפולוגי שטוח מגדיר סביבה ולא משקלי מיצוע. ארוזיה בוחרת מינימום ודילטציה מקסימום. פתיחה היא ארוזיה ואחריה דילטציה; top-hat לבן מחסר את הפתיחה מעוצמות האפור. סגירה היא דילטציה ואחריה ארוזיה. סגירת הגנה (אליפסה 17×17 כברירת מחדל) פועלת על מסכת ניתוב בינארית והרחבת 5×5 מוסיפה מרווח. זיהוי אוטומטי משתמש בנפרד בסגירת 3×3 למציאת מעטפות מועמדים. סף מקומי יוצר את מסכת המדידה הסופית.'),
)
TOPICS['workspace']['paragraphs'] += (
    _t('Mouse-wheel input never changes numeric values, dropdown selections, sliders or dials, even while focused. Numeric fields show + above −; these use the existing step and limits (for example, odd morphology kernels step by 2). Type a value, use these buttons or keyboard arrows, or choose a dropdown item explicitly. The wheel scrolls the surrounding form or an open dropdown; over an image it zooms.',
       'Колесо не меняет числа, выбранные пункты, ползунки и регуляторы даже при фокусе. У числовых полей сверху показан +, снизу −; они используют прежние шаг и пределы (например, нечётные ядра меняются на 2). Введите значение, нажмите эти кнопки или стрелки клавиатуры либо явно выберите пункт списка. Колесо прокручивает форму или раскрытый список; над изображением меняет масштаб.',
       'גלגלת העכבר אינה משנה מספרים, בחירות, מחוונים או חוגות גם כשהם ממוקדים. בשדות מספריים מופיע + מעל −; הכפתורים משתמשים בצעד ובגבולות הקיימים (למשל, גרעינים אי־זוגיים משתנים ב־2). הקלידו, השתמשו בכפתורים או בחצי המקלדת, או בחרו פריט במפורש. הגלגלת גוללת טופס או רשימה פתוחה; מעל תמונה היא משנה זום.'),
    _t('Resizing a panel is different from panning its image. Drag the separator between panels to change their width or height. In Tiles, drag the horizontal divider above the tile details/actions downward to give the image more height; drag upward to see more controls. Compressed controls can be scrolled. This divider position is saved; Reset panel layout restores it.',
       'Изменение размера панели отличается от перемещения картинки внутри неё. Тяните разделитель между панелями для изменения ширины или высоты. В «Тайлах» опускайте горизонтальный разделитель над сведениями и действиями вниз, отдавая изображению больше высоты; поднимайте для показа действий. Сжатую область действий можно прокручивать. Положение разделителя сохраняется; сброс панелей его восстанавливает.',
       'שינוי גודל הלוח שונה מהזזת התמונה בתוכו. גררו מפריד בין לוחות לשינוי רוחב או גובה. באריחים, גררו כלפי מטה את המפריד האופקי שמעל פרטי האריח והפעולות כדי לתת לתמונה יותר גובה; גררו מעלה להצגת יותר בקרות. ניתן לגלול אזור פעולות מצומצם. המיקום נשמר; איפוס סידור הלוחות משחזר אותו.'),
    _t('Drag a floating panel by its title back into the active workspace and release at the desired docking position. A highlighted area indicates the drop target; Qt may place panels side by side or in tabs. Double-click the title or use Detach or return panel to return it directly. Floating titles provide Maximize or restore window and Close buttons. Maximize fills the available screen; restore it before repositioning. Closed panels remain available in Panels. These actions preserve project settings and image data.',
       'Тяните вынесенную панель за заголовок обратно в активную рабочую область и отпускайте в нужном месте. Подсвеченная область показывает позицию; Qt может разместить панели рядом или во вкладках. Двойной щелчок по заголовку или «Вынести или вернуть панель» возвращает её напрямую. В заголовке отдельной панели есть «Развернуть или восстановить окно» и закрытие. Разворачивание занимает доступный экран; перед перестановкой восстановите размер. Закрытые панели доступны в меню «Панели». Настройки проекта и данные изображения сохраняются.',
       'גררו לוח צף באמצעות הכותרת חזרה לסביבת העבודה הפעילה ושחררו במיקום העגינה הרצוי. אזור מודגש מציין יעד; Qt עשוי להציב לוחות זה לצד זה או בלשוניות. לחיצה כפולה על הכותרת או כפתור ניתוק או החזרת הלוח מחזירים אותו ישירות. בכותרת צפה יש כפתורי הגדלה או שחזור וסגירה. הגדלה ממלאת את המסך הזמין; שחזרו גודל לפני הזזה. לוחות שנסגרו זמינים בתפריט הלוחות. הפעולות שומרות על הגדרות הפרויקט ועל נתוני התמונה.'),
    _t('Fit to window shows the entire image without scrollbars. After zooming, a scrollbar appears only on an axis whose image exceeds the available space; dragging pans those visible image pixels. No artificial blank border is added for scrolling. The full-screen image view follows the same rule. A separate original-image window also has the usual maximize/restore title-bar controls.',
       'Вписывание показывает изображение целиком без полос прокрутки. После приближения полоса появляется только по оси, по которой картинка превышает доступную область; перетаскивание перемещает её видимые пиксели. Искусственные пустые поля для прокрутки не добавляются. Полноэкранный просмотр работает так же. У отдельного окна оригинала также есть обычные кнопки разворачивания и восстановления.',
       'התאמה לחלון מציגה את התמונה כולה ללא פסי גלילה. לאחר הגדלה מופיע פס רק בציר שבו התמונה חורגת מהשטח הזמין; גרירה מזיזה את פיקסלי התמונה הנראים. לא נוספים שוליים ריקים מלאכותיים לגלילה. תצוגת מסך מלא פועלת באותו אופן. בחלון המקורי הנפרד יש גם בקרות רגילות להגדלה ולשחזור.'),
    _t('The 1:1 button opens native pixels for the current view. Preparation opens a region viewer, Overview creates a detailed map, and other file views open the saved image. For direct file opening above 32 MP, SoLoData uses the Windows image viewer. F11 enlarges the currently loaded view.',
       'Кнопка 1:1 открывает исходные пиксели текущего вида. В «Подготовке» открывается просмотр участков, в «Карте» строится подробная карта, а во вкладках файлов открывается сохранённое изображение. При прямом открытии файлов больше 32 Мп используется просмотрщик Windows. F11 разворачивает текущий загруженный вид.',
       'כפתור 1:1 פותח פיקסלי מקור של התצוגה הנוכחית. בהכנה נפתח מציג אזורים, בסקירה נוצרת מפה מפורטת, ובתצוגות קובץ נפתחת התמונה השמורה. בפתיחה ישירה של קבצים מעל 32 מגה־פיקסל נעשה שימוש במציג Windows. F11 מגדיל את התצוגה הטעונה.'),
    _t('The SoLoData icon identifies application windows and the Windows taskbar. Use the SoLoData.lnk shortcut beside launch_app.cmd. After moving the application directory, recreate the shortcut with tools/create_shortcut.ps1 so its launcher and icon paths are correct.',
       'Иконка SoLoData используется в окнах и на панели задач Windows. Для запуска используйте SoLoData.lnk рядом с launch_app.cmd. После перемещения папки программы пересоздайте ярлык командой tools/create_shortcut.ps1, чтобы пути запуска и иконки оставались правильными.',
       'סמל SoLoData מזהה את חלונות היישום ואת שורת המשימות של Windows. השתמשו בקיצור SoLoData.lnk שליד launch_app.cmd. לאחר העברת תיקיית היישום, צרו מחדש את הקיצור באמצעות tools/create_shortcut.ps1 כדי שנתיבי ההפעלה והסמל יהיו נכונים.'),
    _t('If a previously pinned Windows icon still looks generic after restarting, unpin that entry and pin the running SoLoData window launched from the current shortcut.',
       'Если ранее закреплённый значок после перезапуска выглядит стандартным, открепите его и закрепите окно SoLoData, запущенное через актуальный ярлык.',
       'אם סמל Windows שכבר הוצמד עדיין נראה כללי לאחר הפעלה מחדש, הסירו את ההצמדה והצמידו את חלון SoLoData שהופעל מהקיצור העדכני.'),
)

_FIRST_RUN = tuple(_t(*step) for step in FIRST_RUN)
_PARAMETER_GUIDANCE = {key: _t(*description) for key, description in GUIDANCE.items()}
_PARAMETER_GROUPS = {
    SOURCES: ('Preparation → Processing settings', 'sources'),
    FILTERS: ('Preparation → Choose filters', 'preparation'),
    MASK: ('Preparation → Protective mask', 'preparation'),
    TILING: ('Preparation → Processing settings', 'tiles'),
    MEASURE: ('Segmentation → Object selection and measurement', 'segmentation'),
}
_PARAMETER_LOCATIONS = {
    'min_corridor_width': 'Preparation → Protective mask',
    **dict.fromkeys(('search_window_end', 'straight_shift_left', 'straight_shift_right'),
                    _t('Preparation → Straight corridor search', 'Подготовка → Поиск прямого коридора', 'הכנה ← חיפוש מסדרון ישר')),
    **dict.fromkeys(('seam_repulsion_power', 'oversized_policy', 'animation_max_trial_frames'),
                    'Advanced pipeline setting with no dedicated desktop control.'),
}
_PARAMETER_NEIGHBORS = (
    ('channel', 'plane', 'pixel_size_um'),
    ('enable_bilateral', 'bilateral_d', 'bilateral_sigma_color', 'bilateral_sigma_space'),
    ('enable_tophat', 'tophat_radius'),
    ('enable_gamma', 'gamma'),
    ('otsu_safety_factor', 'bridge_kernel_size', 'enable_closing', 'buffer_kernel_size', 'enable_dilation'),
    ('target_size', 'search_window_end', 'straight_shift_left', 'straight_shift_right', 'min_corridor_width', 'seam_repulsion_power', 'oversized_policy'),
    ('enable_animations', 'animation_max_trial_frames'),
    ('min_clean_threshold', 'tier2_threshold_factor', 'min_sub_object_area'),
)
_GUIDED = {key: tuple((_t(*heading), _t(*paragraph)) for heading, paragraph in sections)
           for key, sections in GUIDED_SECTIONS.items()}
_RELATED = {
    'getting_started': ('sources', 'preparation', 'tiles', 'segmentation', 'results', 'recovery'),
    'sources': ('preparation', 'recovery'),
    'preparation': ('tiles', 'settings'),
    'tiles': ('tile_editor', 'segmentation', 'workspace'),
    'tile_editor': ('tiles', 'segmentation', 'results', 'manual_types', 'model_evaluation'),
    'segmentation': ('manual_types', 'results', 'recovery'),
    'manual_types': ('results', 'export', 'model_evaluation'),
    'results': ('tile_editor', 'manual_types', 'training_charts', 'export', 'recovery'),
    'export': ('manual_types', 'results', 'model_evaluation'),
    'model_evaluation': ('training_charts', 'export', 'manual_types'),
    'training_charts': ('model_evaluation', 'results'),
    'workspace': ('shortcuts', 'recovery'),
    'settings': ('parameters', 'recovery'),
    'recovery': ('sources', 'segmentation', 'settings'),
    'shortcuts': ('workspace', 'tile_editor', 'manual_types'),
}
TOPICS['shortcuts']['paragraphs'] += (
    _t('In the tile and mask editors use B for Brush, E for Eraser, H for Pan and Ctrl+Z to undo. Ctrl+A on Segmentation → Objects selects every mask on the current tile.',
       'В редакторах тайлов и масок B включает кисть, E — ластик, H — панораму, Ctrl+Z отменяет правку. Ctrl+A в «Сегментация → Объекты» выделяет все маски текущего тайла.',
       'בעורכי האריחים והמסכות, B מפעיל מברשת, E מחק, H הזזה ו־Ctrl+Z מבטל עריכה. Ctrl+A בפילוח ← אובייקטים בוחר את כל המסכות באריח הנוכחי.'),
    _t('In the tile editor, Esc cancels the pending cut or brightness preview. Ctrl+Z reverses the latest undoable edit. F1 opens the tile editing guide.',
       'В редакторе тайлов Esc отменяет черновик отсечения или яркости. Ctrl+Z отменяет последнюю доступную для отмены правку. F1 открывает руководство по редактированию.',
       'בעורך האריחים Esc מבטל את החיתוך או את תצוגת הבהירות הממתינים. Ctrl+Z מבטל את העריכה האחרונה שניתן לבטל. F1 פותח את מדריך העריכה.'),
)
TOPICS['model_evaluation'] = dict(title='Model training', paragraphs=(
    _t('Select one current measurement dataset per TIFF. Only manually classified objects are used. Double-click the Group cell to assign related TIFFs to the same experiment. For imported tiles without an original TIFF link, enter a confirmed group. Select Area in source pixels² or Area in µm² if every included dataset has valid calibrated areas.',
       'Выберите один актуальный набор измерений на TIFF. Используются только объекты с ручным классом. Дважды щёлкните ячейку «Группа», чтобы объединить связанные TIFF одного эксперимента. Для импортированных тайлов без связи с TIFF укажите подтверждённую группу. Выберите площадь в пикселях исходника² или в мкм² при наличии калиброванной площади во всех наборах.',
       'בחרו מערך מדידות עדכני אחד לכל TIFF. נכללים רק עצמים שסווגו ידנית. לחצו פעמיים על תא הקבוצה כדי לאגד קובצי TIFF של אותו ניסוי. לאריחים מיובאים ללא קישור למקור הזינו קבוצה מאומתת. בחרו שטח בפיקסלי מקור בריבוע או במיקרומטר רבוע כאשר לכל המערכים יש שטחים מכוילים תקינים.'),
    _t('Open training table accepts a reviewed SoLoData Excel workbook (.xlsx, Training sheet or first sheet) or a UTF-8 CSV. Keep the original headers Large_Image, Manual_Class_ID, the selected area column and the other five predictors. If Reviewed exists, only true or 1 is included. Use the original TIFF name in Large_Image, one measurement version per TIFF and the same optional Experiment_Group for related TIFFs. A full measurement export without manual labels needs a reviewed training export. Use project datasets returns to the project input.',
       '«Открыть обучающую таблицу» принимает размеченный Excel SoLoData (.xlsx, лист Training или первый лист) либо CSV в UTF-8. Сохраните заголовки Large_Image, Manual_Class_ID, выбранный столбец площади и остальные пять признаков. При наличии Reviewed учитываются только true или 1. Укажите исходный TIFF в Large_Image, одну версию измерений на TIFF и общий необязательный Experiment_Group для связанных TIFF. Для полного экспорта измерений без ручных меток нужен обучающий экспорт с метками. «Использовать наборы проекта» возвращает к вводу из проекта.',
       'פתיחת טבלת אימון מקבלת קובץ Excel מסווג של SoLoData ‏(.xlsx, גיליון Training או הגיליון הראשון) או CSV בקידוד UTF-8. שמרו את הכותרות Large_Image, Manual_Class_ID, עמודת השטח שנבחרה וחמש התכונות האחרות. אם קיימת עמודת Reviewed, נכללים רק true או 1. הזינו את שם ה־TIFF המקורי ב־Large_Image, גרסת מדידה אחת לכל TIFF וערך Experiment_Group משותף לפי הצורך לקובצי TIFF קשורים. לייצוא מדידות מלא ללא תוויות ידניות נדרש ייצוא אימון מסווג. שימוש במערכי הפרויקט מחזיר לקלט מהפרויקט.'),
    _t('Object classes to train filters both training and test data. To compare particles and fibers, leave only those two checked. An explicit subset needs reviewed examples of each selected class. The saved model predicts a class for an already measured mask using its numeric features. Pixel segmentation requires labeled images, including foreground and background pixels. Apply a two-class classifier only to candidate objects known to belong to those classes.',
       '«Классы объектов для обучения» отбирают строки и для обучения, и для теста. Для сравнения частиц и волокон оставьте только эти два класса. Для каждого явно выбранного класса нужны проверенные примеры. Сохранённая модель предсказывает класс уже измеренной маски по числовым признакам. Для сегментации по пикселям нужны размеченные изображения, включая пиксели объектов и фона. Применяйте двухклассовый классификатор к объектам, про которые известно, что они относятся к этим классам.',
       'מחלקות עצמים לאימון מסננות את נתוני האימון והבדיקה. להשוואת חלקיקים וסיבים סמנו רק את שתי המחלקות האלה. לכל מחלקה בתת־קבוצה מפורשת נדרשות דוגמאות מתויגות. המודל השמור חוזה מחלקה למסכה שכבר נמדדה על סמך תכונות מספריות. לפילוח פיקסלים נדרשות תמונות מתויגות, כולל פיקסלים של עצמים ורקע. הפעילו מסווג דו־מחלקתי על עצמים שידוע שהם שייכים למחלקות האלה.'),
    _t('Preview the split before training. Both methods target 80% training and 20% test objects. Whole TIFFs / experiments keeps each group intact and favors class coverage in the test. For example, five TIFFs of 50 objects each can place one TIFF in test. A rare class confined to one TIFF must remain in training. One group can fit demonstration models with tuning off.',
       'Проверьте план перед обучением. Оба режима стремятся к 80% объектов для обучения и 20% для теста. Режим «Целые TIFF / эксперименты» сохраняет группы целыми и старается охватить классы в тесте. Например, при пяти TIFF по 50 объектов один TIFF может уйти в тест. Редкий класс, который встречается на одном TIFF, остаётся в обучении. При одной группе и отключённом подборе доступны демонстрационные модели.',
       'בדקו את החלוקה לפני האימון. שתי השיטות מכוונות ל־80% מהעצמים לאימון ו־20% לבדיקה. חלוקה לפי קובצי TIFF או ניסויים שלמים שומרת כל קבוצה בשלמותה ומעדיפה כיסוי מחלקות בבדיקה. למשל, בחמישה קובצי TIFF עם 50 עצמים בכל אחד אפשר להקצות קובץ אחד לבדיקה. מחלקה נדירה המופיעה בקובץ יחיד תישאר באימון. עם קבוצה אחת וכיוונון כבוי ניתן לאמן מודלים להדגמה.'),
    _t('Stratified objects reserves roughly one fifth of each class for testing, for example 10 of 50 objects. A single example stays in training. When a class has enough examples for both parts, the planner reserves at least one test object. Small counts can move the total away from 20%. Training and test can contain different objects from the same TIFF or experiment, so the score applies to those sources. To measure generalization to new sources, use whole TIFFs or experiments.',
       'Режим «По объектам с учётом классов» отдаёт примерно пятую часть каждого класса в тест, например 10 объектов из 50. Единственный пример класса остаётся в обучении. Если примеров хватает на обе части, в тест попадает хотя бы один. Из-за малых чисел итоговая доля может отличаться от 20%. Разные объекты одного TIFF или эксперимента могут попасть и в обучение, и в тест, поэтому оценка относится к этим исходникам. Для оценки качества на новых исходниках используйте целые TIFF или эксперименты.',
       'חלוקה לפי מחלקות עצמים שומרת לבדיקה כחמישית מכל מחלקה, למשל 10 מתוך 50 עצמים. דוגמה יחידה נשארת באימון. אם יש מספיק דוגמאות לשני החלקים, לפחות עצם אחד יוקצה לבדיקה. מספרים קטנים יכולים לשנות את השיעור הכולל ביחס ל־20%. עצמים שונים מאותו TIFF או ניסוי יכולים להיכלל באימון ובבדיקה, ולכן הציון מתייחס לאותם מקורות. להערכת הכללה למקורות חדשים השתמשו בקובצי TIFF או ניסויים שלמים.'),
    _t('K-fold tuning uses only the training partition. K is 2–10 and the seed range is 0–2147483647. Every fold fit must see all classes used by the model. For grouped tuning, reserve at least K training groups and at least two training groups per class. For object tuning, reserve at least K training objects per class. Changing K can change the holdout. If the plan fails, reduce K, add reviewed data, or turn tuning off. Review the training and validation counts for each fold.',
       'Подбор по K фолдам использует только обучающую часть. Допустимо K от 2 до 10 и зерно от 0 до 2147483647. Модель каждого фолда обучается на всех используемых классах. В режиме по группам нужны минимум K обучающих групп и две обучающие группы на каждый класс. В режиме по объектам нужны минимум K обучающих объектов каждого класса. Изменение K может изменить тестовую часть. Если план не строится, уменьшите K, добавьте проверенные данные или выключите подбор. Проверьте числа для обучения и валидации каждого фолда.',
       'כיוונון עם K קפלים משתמש בחלק האימון בלבד. K בין 2 ל־10 והזרע בין 0 ל־2147483647. אימון בכל קפל דורש את כל המחלקות שמשמשות את המודל. בכיוונון לפי קבוצות נדרשות לפחות K קבוצות אימון ושתי קבוצות אימון לכל מחלקה. בכיוונון לפי עצמים נדרשים לפחות K עצמי אימון מכל מחלקה. שינוי K עשוי לשנות את חלק הבדיקה. אם התוכנית נכשלת, הקטינו את K, הוסיפו נתונים מתויגים או כבו את הכיוונון. בדקו את מספר עצמי האימון והתיקוף בכל קפל.'),
    _t(f'Trees in forest accepts 1–2000 trees. Model factory settings v{MODEL_DEFAULTS_VERSION} use {MODEL_DEFAULTS["forest_tree_count"]} trees and the whole-source split. The chosen count applies to all forest candidates and is saved with the evaluation. More trees usually increase fitting time.',
       f'«Деревьев в лесу» принимает от 1 до 2000. Заводской каталог обучения v{MODEL_DEFAULTS_VERSION} задаёт {MODEL_DEFAULTS["forest_tree_count"]} деревьев и разбиение по целым исходникам. Выбранное число используется для всех кандидатов леса и сохраняется в оценке. Большее число деревьев обычно увеличивает время обучения.',
       f'מספר עצים ביער מקבל 1–2000 עצים. ברירות המחדל של האימון v{MODEL_DEFAULTS_VERSION} הן {MODEL_DEFAULTS["forest_tree_count"]} עצים וחלוקה לפי מקורות שלמים. המספר שנבחר משמש את כל מועמדי היער ונשמר עם ההערכה. יותר עצים בדרך כלל מאריכים את האימון.'),
    _t('Open Tree depth and training time in the related guides for an example of how the app chooses model settings. The final fit uses all training objects. All models share the same test objects.',
       'В связанном разделе «Глубина дерева и время обучения» есть пример того, как программа выбирает настройки модели. Финальная модель обучается на всех обучающих объектах. Для сравнения все модели проверяются на одних и тех же тестовых объектах.',
       'במדריך המקושר עומק העץ וזמן האימון יש דוגמה לאופן שבו היישום בוחר הגדרות למודל. האימון הסופי משתמש בכל עצמי האימון. כל המודלים נבדקים על אותם עצמים.'),
    _t('Saved evaluations contains the frozen data and results. Select the tree or forest and use Save selected model to copy its fitted .joblib file, including feature order and class IDs. Older reports may have no model file. Load trusted files with the matching scikit-learn environment. Click a confusion matrix cell to inspect test objects, predictions, features and tree paths. Project inputs can also show saved crops. Preview again after changing data or settings. Stop takes effect after the current fit.',
       '«Сохранённые оценки» содержат снимок данных и результаты. Выберите дерево или лес и нажмите «Сохранить выбранную модель», чтобы скопировать обученный .joblib с порядком признаков и ID классов. У старых отчётов файл модели может отсутствовать. Открывайте доверенные файлы в соответствующем окружении scikit-learn. Нажмите ячейку матрицы ошибок, чтобы проверить тестовые объекты, прогнозы, признаки и пути дерева. Для данных проекта доступны и сохранённые фрагменты. После изменения данных или настроек обновите план. Остановка выполняется после текущего обучения.',
       'הערכות שמורות כוללות תמונת מצב של הנתונים והתוצאות. בחרו עץ או יער ושמרו את המודל הנבחר כדי להעתיק קובץ .joblib מאומן עם סדר התכונות ומזהי המחלקות. בדוחות ישנים קובץ המודל עשוי להיות חסר. טענו קבצים מהימנים בסביבת scikit-learn תואמת. לחצו על תא במטריצת הבלבול כדי לבדוק עצמים במבחן, תחזיות, תכונות ומסלולים בעץ. בנתוני פרויקט זמינים גם חיתוכי תמונה שמורים. בדקו שוב את התוכנית אחרי שינוי נתונים או הגדרות. העצירה נכנסת לתוקף אחרי האימון הנוכחי.'),
), parameters=())
TOPICS['training_charts'] = dict(title=_t('Training and performance charts', 'Графики данных и качества моделей', 'תרשימי נתונים וביצועי מודלים'), paragraphs=(
    _t('Data charts and Performance charts open in the center of the screen containing the main window. Drag the title bar to move the window, or resize or maximize it while continuing to use the model training page.',
       '«Графики данных» и «Графики качества» открываются по центру экрана, на котором находится главное окно. Перетаскивайте окно за заголовок, меняйте размер или разворачивайте его, продолжая работу на странице обучения.',
       'תרשימי נתונים ותרשימי ביצועים נפתחים במרכז המסך שבו נמצא החלון הראשי. גררו את שורת הכותרת כדי להזיז את החלון, או שנו את גודלו והגדילו אותו תוך כדי עבודה בדף האימון.'),
    _t('After previewing the split, open Data charts. Class counts show reviewed objects of the chosen classes and separate training and test bars. With whole groups, class proportions can differ. For example, 3 training and 10 test objects in a class show weak training coverage. An empty test in a one-group demonstration is expected. Scores from a stratified object test apply to the same input sources.',
       'После предпросмотра плана откройте «Графики данных». Показаны числа проверенных объектов выбранных классов, в том числе отдельно для обучения и теста. При разделении по целым группам доли классов могут отличаться. Например, 3 объекта в обучении и 10 в тесте показывают слабое покрытие класса при обучении. При демонстрации на одной группе тест пуст. Оценки теста по объектам относятся к тем же исходникам.',
       'אחרי תצוגה מקדימה של החלוקה פתחו תרשימי נתונים. מוצגות ספירות העצמים המתויגים של המחלקות שנבחרו ועמודות נפרדות לאימון ולבדיקה. בחלוקה לפי קבוצות שלמות יחסי המחלקות עשויים להשתנות. לדוגמה, 3 עצמים באימון ו־10 בבדיקה מצביעים על כיסוי חלש של המחלקה באימון. בהדגמה עם קבוצה אחת חלק הבדיקה ריק. ציוני בדיקה לפי עצמים מתייחסים לאותם מקורות קלט.'),
    _t('The Pearson correlation matrix shows linear association between pairs of selected predictors. Values near +1 and −1 indicate strong positive and negative linear association. Zero means little linear association. A constant predictor has undefined correlation. Correlation describes these rows and can miss nonlinear patterns. Feature distributions by class and group help identify overlap and group shifts.',
       'Матрица корреляции Пирсона показывает линейную связь между парами выбранных признаков. Значения около +1 и −1 означают сильную прямую и обратную линейную связь. Ноль означает слабую линейную связь. Для постоянного признака корреляция не определена. Корреляция описывает эти строки и может пропустить нелинейную связь. Распределения признаков по классам и группам помогают заметить перекрытие и различия между группами.',
       'מטריצת מתאם פירסון מציגה קשר ליניארי בין זוגות של תכונות נבחרות. ערכים ליד +1 ו־−1 מציינים קשר ליניארי חיובי ושלילי חזק. אפס מציין קשר ליניארי חלש. לתכונה קבועה המתאם אינו מוגדר. המתאם מתאר את השורות האלו ועלול להחמיץ קשרים לא ליניאריים. התפלגויות תכונה לפי מחלקה וקבוצה עוזרות לזהות חפיפה והבדלים בין קבוצות.'),
    _t('Open Performance charts after an evaluation with a test set. Use the question mark on the current chart to open its guide. The related guides above explain the impurity curves, the confusion matrix and what happens when a feature is shuffled.',
       'После оценки с тестовой выборкой откройте «Графики качества». Нажмите знак вопроса на нужной вкладке графика, чтобы открыть пояснение. Связанные разделы выше показывают на примерах, как читать кривые критериев, матрицу ошибок и результат перемешивания признака.',
       'אחרי הערכה עם קבוצת בדיקה פתחו תרשימי ביצועים. לחצו על סימן השאלה בלשונית התרשים כדי לפתוח את המדריך המתאים. המדריכים המקושרים למעלה מסבירים בעזרת דוגמאות את עקומות אי־הטוהר, את מטריצת הבלבול ואת תוצאת ערבוב התכונה.'),
), parameters=())

from .model_training_help import install as _install_model_training_help
_install_model_training_help(TOPICS, _GUIDED, _RELATED, _t)

from .segmentation_help import install as _install_segmentation_help, FIRST_STEPS, SEGMENT, LABELING, FINAL
_install_segmentation_help(TOPICS, _t, _RU, _HE)
_FIRST_RUN = _FIRST_RUN[:4] + tuple(_t(*step) for step in FIRST_STEPS)
for _key, _paragraph in (('segmentation', SEGMENT), ('manual_types', LABELING), ('results', FINAL)):
    _GUIDED[_key] = ((_t('Workflow', 'Порядок работы', 'סדר העבודה'), _t(*_paragraph)),)
_RELATED['segmentation'] = ('segmentation_review', 'merge_objects', 'manual_types', 'results')
_RELATED['segmentation_review'] = ('merge_objects', 'segmentation', 'manual_types')
_RELATED['merge_objects'] = ('segmentation_review', 'manual_types', 'results')
from .mask_correction_help import install as _install_mask_correction_help
_install_mask_correction_help(TOPICS, _t)
_RELATED['mask_correction'] = ('segmentation_review','merge_objects','delete_masks','manual_types')
_RELATED['delete_masks'] = ('segmentation_review','mask_correction','results')
_RELATED['segmentation_review'] += ('mask_correction','delete_masks')
_RELATED['merge_objects'] += ('mask_correction','delete_masks')
from .black_tile_text import HELP as _BLACK_HELP
TOPICS['black_tiles'] = dict(title=_t('Automatic exclusion of black tiles','Автоматическое исключение чёрных тайлов','החרגה אוטומטית של אריחים שחורים'),
    paragraphs=tuple(_t(*paragraph) for paragraph in _BLACK_HELP),parameters=())
TOPICS['tiles']['paragraphs'] += TOPICS['black_tiles']['paragraphs']
_RELATED['black_tiles'] = ('tiles','tile_editor','results')
_RELATED['tiles'] += ('black_tiles',)
TOPICS['image_ruler'] = dict(title=_t('Image ruler', 'Линейка изображения', 'סרגל תמונה'), paragraphs=(
    _t('Ruler is available in image panels and separate SoLoData viewers, including 1:1. Object crops use the calibration recorded with the measurement that produced them. For a large source TIFF, use View whole TIFF and select a native region. The Windows image viewer has its own controls.',
       '«Линейка» доступна в панелях и отдельных окнах SoLoData, включая 1:1. Фрагменты объектов используют калибровку сохранённой версии измерений. Для большого исходного TIFF откройте «Просмотр всего TIFF…» и выберите участок в исходных пикселях. У системного просмотрщика Windows свои инструменты.',
       'הסרגל זמין בלוחות ובחלונות הנפרדים של SoLoData, כולל 1:1. חיתוכי עצמים משתמשים בכיול שנשמר עם המדידה שיצרה אותם. עבור TIFF מקור גדול פתחו תצוגת TIFF שלם ובחרו אזור בפיקסלי המקור. למציג Windows כלים משלו.'),
    _t('Drag a straight segment or select Polyline ruler from the ruler menu. Click to add vertices. The preview follows the pointer. Double-click or press Enter to finish the open line. Backspace removes the last vertex while drawing. Hold Shift to align a segment and press Esc to clear.',
       'Проведите прямой отрезок или выберите «Ломаная линейка» в меню линейки. Добавляйте вершины щелчком. Предпросмотр следует за курсором. Двойной щелчок или Enter завершает открытую линию. Во время рисования Backspace убирает последнюю вершину. Shift выравнивает отрезок, Esc очищает линию.',
       'גררו מקטע ישר או בחרו סרגל קו שבור בתפריט הסרגל. לחצו להוספת קודקודים. התצוגה המקדימה עוקבת אחרי הסמן. לחיצה כפולה או Enter מסיימים את הקו הפתוח. Backspace מסיר את הקודקוד האחרון בזמן הציור. Shift מיישר מקטע ו־Esc מנקה את הקו.'),
    _t('The ruler uses saved image coordinates. Known transforms convert the two coordinate differences to source pixels before calculating the straight-line length. A saved calibration also displays micrometres. For example, differences of 3 and 4 source pixels give 5 source pixels, or 2 µm at 0.4 µm per source pixel.',
       'Линейка использует координаты сохранённого изображения. При известном преобразовании разности координат переводятся в пиксели исходника до расчёта длины. Сохранённая калибровка добавляет значение в микрометрах. Например, разности 3 и 4 пикселя исходника дают длину 5 пикселей, или 2 мкм при 0,4 мкм на пиксель.',
       'הסרגל משתמש בקואורדינטות של התמונה השמורה. כשידועה ההמרה, הפרשי הקואורדינטות מומרים לפיקסלי מקור לפני חישוב האורך הישר. כיול שמור מוסיף תצוגה במיקרומטרים. לדוגמה, הפרשים של 3 ו־4 פיקסלי מקור נותנים אורך של 5 פיקסלים, או 2 מיקרומטרים בכיול 0.4 מיקרומטר לפיקסל מקור.'),
    _t('A polyline adds the lengths of its committed segments. The menu sets the color and width from 1 to 12 screen pixels. Right-click an individual segment to change its color. If the source transform is unavailable, length is in file pixels. Use the native view for fine endpoint placement.',
       'Длина ломаной равна сумме длин поставленных отрезков. В меню можно задать цвет и толщину от 1 до 12 экранных пикселей. Чтобы изменить цвет одного отрезка, щёлкните по нему правой кнопкой. Если масштаб исходника неизвестен, длина дана в пикселях файла. Для точной установки точек откройте Native.',
       'אורך קו שבור הוא סכום אורכי המקטעים שנקבעו. בתפריט בוחרים צבע ועובי בין 1 ל־12 פיקסלי מסך. לחצו לחיצה ימנית על מקטע יחיד כדי לשנות את צבעו. אם ההמרה למקור לא ידועה, האורך הוא בפיקסלי הקובץ. למיקום קצוות מדויק השתמשו בתצוגת המקור.'),
), parameters=('pixel_size_um',))
TOPICS['image_contour'] = dict(title=_t('Measuring an image contour', 'Измерение контура на изображении', 'מדידת מתאר בתמונה'), paragraphs=(
    _t('The dashed preview follows the pointer after the first vertex. Double-click to close a contour with at least three vertices. The Contour menu sets line color and thickness from 1 to 12 screen pixels. Imported YOLO outlines have their own color and width controls in the same menu.',
       'Пунктир следует за курсором после первой вершины. Двойной щелчок замыкает контур из трёх или более вершин. В меню «Контур» задаются цвет и толщина линии от 1 до 12 экранных пикселей. Для импортированных полигонов YOLO в этом же меню есть отдельные цвет и толщина.',
       'הקו המקווקו עוקב אחרי הסמן אחרי הקודקוד הראשון. לחיצה כפולה סוגרת מתאר עם לפחות שלושה קודקודים. תפריט המתאר קובע צבע ועובי בין 1 ל־12 פיקסלי מסך. למתארי YOLO מיובאים יש בקרות צבע ועובי נפרדות באותו תפריט.'),
    _t('Choose Contour and click to add vertices. Drag a vertex to move it. Press Enter or click the first point to close the shape. A click on an edge of a closed contour inserts a vertex. Backspace removes the last point and Esc clears the contour. The menu also offers a rectangle, a 32-point ellipse and a copy of a displayed outline. To copy an outline, select the copy tool and click that outline on the image.',
       'Выберите «Контур» и щёлкайте по изображению, чтобы добавить вершины. Вершины можно перетаскивать. Enter или щелчок по первой точке замыкает фигуру. Щелчок по ребру замкнутого контура вставляет вершину. Backspace удаляет последнюю точку, Esc очищает контур. В меню также есть прямоугольник, эллипс из 32 точек и копирование отображаемого полигона. Для копирования включите инструмент и щёлкните по полигону на изображении.',
       'בחרו מתאר ולחצו כדי להוסיף קודקודים. גררו קודקוד כדי להזיזו. Enter או לחיצה על הנקודה הראשונה סוגרים את הצורה. לחיצה על צלע במתאר סגור מוסיפה קודקוד. Backspace מסיר את הנקודה האחרונה ו־Esc מנקה את המתאר. התפריט מציע גם מלבן, אליפסה בת 32 נקודות והעתקת מתאר מוצג. להעתקה בחרו בכלי ולחצו על המתאר בתמונה.'),
    _t('The icons in the Contour menu show each shape. Hold Shift when placing a vertex to make the new segment horizontal or vertical. Hold Shift while dragging a rectangle or ellipse to draw a square or circle.',
       'Значки в меню «Контур» показывают форму. Удерживайте Shift, когда ставите вершину, чтобы провести горизонтальный или вертикальный отрезок. Удерживайте Shift при рисовании прямоугольника или эллипса, чтобы получить квадрат или круг.',
       'הסמלים בתפריט המתאר מציגים את הצורות. החזיקו Shift בעת הצבת קודקוד כדי ליצור מקטע אופקי או אנכי. החזיקו Shift בעת גרירת מלבן או אליפסה כדי לצייר ריבוע או מעגל.'),
    _t('With focus on the image, press Ctrl+Z to undo one contour edit at a time. You can also choose Undo contour edit in the menu. Moving a vertex counts as one edit, and undo can restore a contour after clearing or replacing it. Switching images or turning off Contour clears its history.',
       'Когда фокус на изображении, нажимайте Ctrl+Z, чтобы отменять по одной правке. Та же команда есть в меню «Контур». Перетаскивание вершины считается одной правкой. Отмена может вернуть контур после очистки или замены. При смене изображения или выключении контура история сбрасывается.',
       'כשהמיקוד בתמונה, לחצו Ctrl+Z לביטול עריכת מתאר אחת בכל פעם. אפשר גם לבחור ביטול עריכת מתאר בתפריט. גרירת קודקוד נחשבת לעריכה אחת, וניתן לבטל ניקוי או החלפה של מתאר. החלפת התמונה או כיבוי כלי המתאר מנקים את ההיסטוריה.'),
    _t('An open path reports its length. A closed contour reports perimeter. A simple closed contour also reports area and the diameter of a circle with that area, 2√(area/π). For a 3 by 4 px rectangle, perimeter is 14 px and equivalent diameter is about 3.91 px. Saved calibration adds µm and µm². These contours are temporary viewing overlays. Edits to a copy are separate from imported YOLO polygons and saved masks.',
       'Открытая ломаная показывает длину, замкнутый контур — периметр. Для замкнутого контура без самопересечений также показаны площадь и диаметр круга той же площади, 2√(площадь/π). У прямоугольника 3 × 4 px периметр равен 14 px, эквивалентный диаметр — около 3,91 px. При наличии калибровки доступны мкм и мкм². Контуры временные. Правки копии отделены от импортированных полигонов YOLO и сохранённых масок.',
       'קו פתוח מציג אורך. מתאר סגור מציג היקף. מתאר סגור פשוט מציג גם שטח וקוטר עיגול בעל אותו שטח, 2√(שטח/π). במלבן של 3 על 4 פיקסלים ההיקף הוא 14 פיקסלים והקוטר השקול כ־3.91 פיקסלים. כיול שמור מוסיף מיקרומטרים ומיקרומטרים רבועים. המתארים זמניים. עריכות העותק נפרדות ממצולעי YOLO מיובאים וממסכות שמורות.'),
), parameters=('pixel_size_um',))
_RELATED['image_contour'] = ('image_ruler', 'workspace', 'segmentation_review')
_RELATED['image_ruler'] = ('workspace', 'tiles', 'image_contour')
TOPICS['image_comparison'] = dict(title=_t('Image comparison and overlay', 'Сравнение и наложение изображений', 'השוואה וחפיפת תמונות'), paragraphs=(
    _t('In Preparation or Segmentation, select Compare side by side and click Open comparison window at the end of the tabs. In other viewers, the two-image icon opens Compare with file. Drag the divider to resize the panes. Each pane has its own pan, zoom and display levels.',
       'В «Подготовке» или «Сегментации» выберите «Сравнить рядом» и нажмите «Открыть окно сравнения» справа от вкладок. В других просмотрах значок двух изображений открывает «Сравнить с файлом». Перетаскивайте разделитель. В каждой панели свои масштаб, панорамирование и уровни отображения.',
       'בהכנה או בפילוח, בחרו השוואה זו לצד זו ולחצו פתיחת חלון השוואה בקצה הלשוניות. בתצוגות אחרות סמל שתי התמונות פותח השוואה לקובץ. גררו את המפריד לשינוי גודל הלוחות. בכל לוח יש זום, הזזה ורמות תצוגה משלו.'),
    _t('When the two images have the same width and height, choose Overlay. At 0% you see the first image, at 100% the second, and at 50% you see an equal blend. The views share a pixel origin and use the smaller available preview grid. For comparing channels, use matching crops with the same orientation and acquisition coordinates. Equal dimensions alone do not establish spatial registration.',
       'При одинаковой ширине и высоте нажмите «Наложение». При 0% видна первая картинка, при 100% вторая, при 50% обе имеют равный вклад. Начала пиксельных координат совмещаются, используется меньшая из доступных сеток предпросмотра. Для сравнения каналов берите одинаковые области с совпадающими координатами съёмки и ориентацией. Один размер файлов не подтверждает пространственное совмещение.',
       'כשהרוחב והגובה זהים בחרו שכבה חופפת. ב־0% רואים את התמונה הראשונה, ב־100% את השנייה וב־50% את שתיהן במשקל שווה. ראשית הפיקסלים משותפת ונעשה שימוש בסריג התצוגה הקטן יותר. להשוואת ערוצים בחרו חיתוכים תואמים בכיוון ובקואורדינטות הצילום. מידות זהות לבדן אינן מבטיחות רישום מרחבי.'),
    _t('In the tile editor, Compare with original opens the original tile and a snapshot of your applied edits, including unsaved edits. Apply a pending preview first if you want it in the comparison.',
       'В редакторе тайла кнопка «Сравнить с оригиналом» открывает исходный тайл и снимок применённых правок, включая несохранённые. Если нужно сравнить текущий предпросмотр, сначала нажмите «Применить».',
       'בעורך האריח, השוואה למקור פותחת את האריח המקורי ותמונת מצב של השינויים שהוחלו, כולל שינויים שטרם נשמרו. כדי להשוות תצוגה מקדימה שממתינה, החילו אותה תחילה.'),
), parameters=())
TOPICS['image_levels'] = dict(title=_t('Brightness, contrast and display levels', 'Яркость, контраст и уровни отображения', 'בהירות, ניגודיות ורמות תצוגה'), paragraphs=(
    _t('Open the slider icon on the image toolbar. Brightness shifts the black-to-white range toward darker or lighter input values. Contrast narrows or widens the range. You can enter Black level and White level directly. For example, on 8-bit data levels 20 and 100 display samples at 20 as black, 60 as mid-gray and 100 as white.',
       'Откройте значок ползунков на панели изображения. Яркость сдвигает интервал от чёрного к белому, а контраст сужает или расширяет его. Уровни чёрного и белого можно ввести напрямую. Например, в 8-битном изображении с уровнями 20 и 100 значение 20 видно как чёрный, 60 как серый, 100 как белый.',
       'פתחו את סמל המחוונים בסרגל התמונה. בהירות מזיזה את טווח השחור עד הלבן וניגודיות מצמצמת או מרחיבה אותו. ניתן להזין רמות שחור ולבן ישירות. לדוגמה, בתמונה של 8 סיביות עם רמות 20 ו־100 הערך 20 מוצג כשחור, 60 כאפור ו־100 כלבן.'),
    _t('These adjustments apply to the view. Reset returns to the initial display. Supported 16-bit grayscale inputs allow levels in their original units. To save an adjusted copy, use Save displayed image. For an active scientific tile edit use the tile editor and Save tile.',
       'Настройка действует на просмотр. Сброс возвращает начальное отображение. Для поддерживаемых 16-битных серых изображений уровни задаются в их исходных единицах. Чтобы сохранить настроенный вид, выберите «Сохранить видимое изображение». Для активной научной правки используйте редактор и «Сохранить тайл».',
       'ההתאמות חלות על התצוגה. איפוס מחזיר את התצוגה ההתחלתית. בקלט נתמך של 16 סיביות בגוני אפור אפשר לבחור רמות ביחידות המקור. לשמירת עותק מותאם בחרו שמירת התמונה המוצגת. לעריכה מדעית פעילה השתמשו בעורך ובשמירת האריח.'),
), parameters=())
TOPICS['image_export'] = dict(title=_t('Saving images as TIFF, PNG or JPEG', 'Сохранение изображений в TIFF, PNG и JPEG', 'שמירת תמונות כ־TIFF, PNG או JPEG'), paragraphs=(
    _t('The save icon offers Save displayed image and, when a file is open, Export saved file. The first saves the visible image, display levels and overlays at the decoded view resolution. For example, a 2400-pixel preview exports at 2400 pixels even if the window is larger. An overlay exports both layers at the chosen opacity.',
       'Значок сохранения предлагает «Сохранить видимое изображение» и, если открыт файл, «Экспортировать сохранённый файл». Первый вариант сохраняет видимые пиксели, уровни и наложения в разрешении предпросмотра. Например, предпросмотр на 2400 пикселей экспортируется на 2400 пикселей даже в большом окне. Наложение сохраняется с выбранной непрозрачностью.',
       'סמל השמירה מציע שמירת התמונה המוצגת, וכשקובץ פתוח גם ייצוא קובץ שמור. האפשרות הראשונה שומרת את התמונה, רמות התצוגה והשכבות ברזולוציית הפענוח. לדוגמה, תצוגה של 2400 פיקסלים תיוצא באותו גודל גם בחלון גדול. תמונה חופפת תיוצא באטימות שנבחרה.'),
    _t('Use Export saved file for the full saved file. Same-format exports copy the original bytes, including metadata. Conversion exports the first image in the file. TIFF and PNG support lossless grayscale data up to 16 bits. JPEG is lossy and uses 8-bit samples. Save tile in the editor publishes an active dataset version separately.',
       'Для сохранённого файла в полном разрешении выберите «Экспортировать сохранённый файл». В том же формате копируются исходные байты вместе с метаданными. При преобразовании используется первое изображение файла. TIFF и PNG поддерживают серые данные до 16 бит без потерь. JPEG использует 8 бит и сжимает с потерями. «Сохранить тайл» в редакторе отдельно публикует активную версию набора.',
       'לייצוא הקובץ השמור במלוא רזולוצייתו בחרו ייצוא קובץ שמור. באותו פורמט הבתים המקוריים ומטא־הנתונים מועתקים. המרה משתמשת בתמונה הראשונה בקובץ. TIFF ו־PNG תומכים בגוני אפור עד 16 סיביות ללא אובדן; JPEG משתמש ב־8 סיביות ובדחיסה עם אובדן. שמירת האריח בעורך מפרסמת בנפרד גרסה פעילה של המערך.'),
), parameters=())
TOPICS['editor_cursor'] = dict(title=_t('Drawing cursor', 'Курсор рисования', 'סמן ציור'), paragraphs=(
    _t('Choose Crosshair, Dot, Arrow or Precision target in the tile and mask editors. The selection changes the pointer for drawing and picking. The brush or eraser still uses its native-pixel size. For example, a dot cursor can be used with a 60-pixel eraser.',
       'В редакторах тайла и масок выберите «Крест», «Точка», «Стрелка» или «Прицел». Выбор меняет указатель при рисовании и взятии образца. Размер кисти или ластика по-прежнему задаётся в исходных пикселях. Например, с курсором-точкой можно пользоваться ластиком радиусом 60 пикселей.',
       'בחרו צלב, נקודה, חץ או כוונת בעורכי האריח והמסכה. הבחירה משנה את הסמן בציור ובדגימה. גודל המברשת והמחק עדיין נקבע בפיקסלי המקור. לדוגמה, אפשר להשתמש בסמן נקודה עם מחק ברדיוס 60 פיקסלים.'),
), parameters=())
_RELATED['workspace'] += ('image_ruler', 'image_contour', 'image_comparison', 'image_levels', 'image_export')
_RELATED['preparation'] += ('image_comparison', 'image_levels')
_RELATED['segmentation_review'] += ('image_comparison',)
_RELATED['tile_editor'] += ('image_levels', 'image_export', 'editor_cursor')
_RELATED['mask_correction'] += ('editor_cursor',)
_RELATED['image_comparison'] = ('workspace', 'image_levels', 'image_export')
_RELATED['image_levels'] = ('workspace', 'image_export', 'tile_editor')
_RELATED['image_export'] = ('image_levels', 'image_comparison')
_RELATED['editor_cursor'] = ('tile_editor', 'mask_correction')
_RELATED['tiles'] += ('image_ruler',)
TOPICS['tiles']['paragraphs'] += (
    _t('Ownership shows a binary map of which source pixels belong to the selected tile. An entirely white rectangle on the dark background means every pixel in the crop belongs to it. Polygons shows the model image with imported YOLO outlines. Its caption tells you whether the tile has outlines, an empty annotation file, no annotation file or invalid annotations. The same YOLO status is shown in Segmentation.',
       '«Принадлежность» показывает бинарную карту исходных пикселей, закреплённых за выбранным тайлом. Полностью белый прямоугольник на тёмном фоне означает, что тайлу принадлежат все пиксели фрагмента. «Полигоны» показывает модельное изображение с импортированными контурами YOLO. Подпись сообщает, есть ли контуры, пуст ли файл, отсутствует ли он или содержит ошибку. Такой же статус YOLO показан в «Сегментации».',
       'שיוך מציג מפה בינארית של פיקסלי המקור השייכים לאריח שנבחר. מלבן לבן מלא על רקע כהה פירושו שכל הפיקסלים בחיתוך שייכים לאריח. מצולעים מציג את תמונת המודל עם מתארי YOLO מיובאים. הכיתוב מציין אם יש מתארים, קובץ תיוג ריק, קובץ חסר או תיוגים לא תקינים. אותו מצב מוצג גם בפילוח.'),
)
TOPICS['settings']['paragraphs'] += (
    _t('Settings in the top bar collects every processing parameter, including advanced values. Search by name or key. The factory column is a reference. Edit the Value to apply column and select OK to save to the open project. An invalid value keeps OK disabled. Reset the selected setting or the active tab to load factory values into the draft.',
       '«Настройки» в верхней панели собирают все параметры обработки, включая расширенные. Ищите по названию или ключу. Колонка заводских значений служит справочником. Измените «Новое значение» и нажмите OK, чтобы сохранить параметры открытого проекта. При ошибке OK недоступна. Можно сбросить выбранное поле или текущую вкладку к заводским значениям в черновике.',
       'הגדרות בסרגל העליון מרכזות את כל פרמטרי העיבוד, כולל ערכים מתקדמים. חפשו לפי שם או מפתח. עמודת ערכי היצרן מיועדת לעיון. ערכו את הערך להחלה ולחצו אישור כדי לשמור בפרויקט הפתוח. ערך לא תקין משבית את האישור. ניתן לאפס את ההגדרה שנבחרה או את הלשונית הפעילה לערכי היצרן בטיוטה.'),
    _t('Check Also use these processing settings for new projects to update your personal starting values. The editor tabs set personal starting values when opening an editor. Tile radii and mask widths use source pixels. For example, a mask brush width of 9 is valid and 8 is rejected because widths must be odd. Factory defaults and completed runs keep their own values.',
       'Установите «Использовать эти параметры обработки и в новых проектах», чтобы изменить личные начальные значения. Вкладки редакторов задают начальные параметры при их открытии. Радиусы тайла и толщины маски измеряются в пикселях исходника. Например, кисть маски толщиной 9 допустима, а 8 отклоняется, потому что ширина должна быть нечётной. Заводской каталог и завершённые запуски хранят свои значения.',
       'סמנו השתמשו גם בהגדרות עיבוד אלו בפרויקטים חדשים כדי לשנות ערכי התחלה אישיים. לשוניות העורכים קובעות את הערכים בעת פתיחת עורך. רדיוסי האריח ורוחבי המסכה הם בפיקסלי מקור. לדוגמה, רוחב מברשת מסכה 9 מותר ו־8 נדחה כי הרוחב חייב להיות אי־זוגי. לערכי היצרן ולהרצות שכבר הושלמו נשמרים הערכים שלהם.'),
)
TOPICS['pixel_segmentation'] = dict(title=_t('Pixel segmentation', 'Сегментация по пикселям', 'פילוח לפי פיקסלים'), paragraphs=(
    _t('In Segmentation, open Pixel segmentation and choose measurement datasets and foreground classes. Particle and fiber are preselected. Review the exact native masks and assign manual types before training. The number of trees is 1–2000 with a factory value of 200. The feature table trains an object classifier on the Model training page.',
       'На странице «Сегментация» откройте «Сегментация по пикселям» и выберите наборы измерений и классы переднего плана. Изначально отмечены частица и волокно. До обучения проверьте точные native-маски и назначьте ручные классы. Число деревьев 1–2000, заводское значение 200. На странице «Обучение модели» таблица признаков служит для обучения классификатора объектов.',
       'בדף פילוח פתחו פילוח לפי פיקסלים ובחרו מערכי מדידות ומחלקות קדמה. חלקיק וסיב מסומנים מראש. לפני האימון בדקו מסכות מקור מדויקות והקצו מחלקות ידניות. מספר העצים הוא 1–2000, עם ברירת מחדל 200. בדף אימון המודל טבלת התכונות משמשת לאימון מסווג עצמים.'),
    _t('The pixel forest uses local intensity features. It learns foreground from the selected reviewed masks. Overlaps, manual additions and unselected objects are excluded from samples. Valid pixels sufficiently far from every measured mask are candidate background. This heuristic can include faint unmeasured objects. Inspect predictions on independent TIFFs before using the maps for scientific work.',
       'Пиксельный лес использует локальные признаки яркости. Передний план задают проверенные маски выбранных классов. Перекрытия, ручные добавления и объекты других классов исключаются из выборки. Кандидаты в фон — действительные пиксели достаточно далеко от всех измеренных масок. Эта эвристика может захватить слабые неизмеренные объекты. Проверьте прогнозы на независимых TIFF перед научным использованием карт.',
       'יער הפיקסלים משתמש בתכונות עוצמה מקומיות. הקדמה נלמדת מהמסכות הסקורות של המחלקות שנבחרו. חפיפות, תוספות ידניות ועצמים שלא נבחרו אינם נדגמים. פיקסלים תקפים רחוקים מספיק מכל המסכות שנמדדו משמשים כמועמדים לרקע. השיטה עלולה לכלול עצמים חלשים שלא נמדדו. בדקו תחזיות בקובצי TIFF עצמאיים לפני שימוש מדעי במפות.'),
    _t('Tiles must be grayscale native images up to 32 MP. Training skips tiles with synthetic intensity painting. It samples up to 4096 pixels per label, including background outside the 8-pixel margin around measured masks. If a class has too few eligible pixels, select more reviewed datasets or change the foreground classes.',
       'Нужны native-тайлы в градациях серого до 32 Мп. Обучение пропускает тайлы с синтетической дорисовкой яркости. Выбирается до 4096 пикселей на метку, включая фон за пределами отступа 8 пикселей вокруг измеренных масок. Если для класса мало пригодных пикселей, добавьте проверенные наборы или измените список классов переднего плана.',
       'נדרשים אריחי מקור בגוני אפור עד 32 מגה־פיקסל. באימון מדלגים על אריחים עם ציור עוצמה סינתטי. נדגמים עד 4096 פיקסלים לתווית, כולל רקע מחוץ לשוליים של 8 פיקסלים סביב המסכות שנמדדו. אם למחלקה יש מעט מדי פיקסלים מתאימים, הוסיפו מערכים סקורים או שנו את מחלקות הקדמה.'),
    _t('Apply a saved model to the active native tile. The separate output includes a color overlay and a class PNG. Code 0 is background, class IDs 0–5 use codes 1–6, and 255 marks pixels outside tile ownership. For example, particle and fiber use codes 1 and 2. Touching objects of one class can share a region. The trained model and maps are stored under pixel_segmentation in the project.',
       'Примените сохранённую модель к выбранному активному native-тайлу. Отдельный результат включает цветное наложение и PNG классов. Код 0 означает фон, ID классов 0–5 получают коды 1–6, а 255 отмечает пиксели вне принадлежности тайлу. Например, частица и волокно получают коды 1 и 2. Соприкасающиеся объекты одного класса могут образовать общую область. Модели и карты хранятся в pixel_segmentation проекта.',
       'החילו מודל שמור על אריח המקור הפעיל. הפלט הנפרד כולל שכבת צבע וקובץ PNG של המחלקות. קוד 0 מציין רקע, מזהי מחלקות 0–5 מקבלים קודים 1–6, ו־255 מציין פיקסלים מחוץ לבעלות האריח. לדוגמה, חלקיק וסיב מקבלים קודים 1 ו־2. עצמים נוגעים מאותה מחלקה יכולים לחלוק אזור אחד. המודלים והמפות נשמרים בתיקיית pixel_segmentation בפרויקט.'),
), parameters=())
_RELATED['pixel_segmentation'] = ('segmentation', 'manual_types', 'model_evaluation')
_RELATED['segmentation'] += ('pixel_segmentation',)
_RELATED['model_evaluation'] += ('pixel_segmentation',)

_TOPIC_ALIASES = {
    'dataset': 'sources', 'open_tiles': 'tiles', 'source_selection': 'sources',
    'tile_search': 'tiles', 'tile_filter': 'tiles', 'tile_ids': 'tiles', 'labels_mode': 'segmentation',
    'manual_class': 'manual_types', 'manual_navigation': 'manual_types', 'manual_export': 'export',
    'result_search': 'results', 'result_class_filter': 'results', 'image_viewer': 'workspace',
    'image_zoom': 'workspace', 'image_fit': 'workspace', 'image_fullscreen': 'workspace', 'language': 'workspace',
    'image_original': 'workspace', 'detailed_map': 'tiles', 'result_tile': 'manual_types',
    'filters': 'preparation', 'defaults': 'settings', 'parameters': 'parameters',
    'import_yolo': 'segmentation', 'check_yolo': 'segmentation', 'open_yolo': 'segmentation',
    'measure_objects': 'segmentation', 'detect_fallback': 'segmentation', 'open_measurements': 'segmentation',
    'excel_export': 'export', 'ml_bundle': 'export', 'feature_statistics': 'results',
}
_MISSING = object()


TOPICS['source_viewer'] = dict(title=_t('View the whole TIFF', 'Просмотр всего TIFF', 'תצוגת TIFF שלם'), paragraphs=(
    _t('In Preparation, select the TIFF, channel and plane, then click View whole TIFF. The main image starts at 1:1 on the physical display. Drag the main image to pan. Click the sampled navigation map on the left to jump. The status shows the loaded region in source pixels. A low-zoom overview is labeled as reduced. The default uint16 display uses the high byte.',
       'В «Подготовке» выберите TIFF, канал и плоскость, затем нажмите «Просмотр всего TIFF…». Основное изображение открывается в масштабе 1:1 на физическом экране. Перетаскивайте его для панорамирования или щёлкните по уменьшенной карте слева. Статус показывает загруженную область в исходных пикселях. При сильном отдалении вид подписан как уменьшенный. Для uint16 по умолчанию используется старший байт.',
       'בהכנה בחרו TIFF, ערוץ ומישור ולחצו על תצוגת TIFF שלם. התמונה הראשית נפתחת ב־1:1 על המסך הפיזי. גררו אותה להזזה או לחצו על מפת הניווט המוקטנת משמאל. המצב מציג את האזור הנטען בפיקסלי מקור. תצוגת זום נמוך מסומנת כמוקטנת. ברירת המחדל עבור uint16 משתמשת בבית הגבוה.'),
    _t('If a large TIFF must be decoded in its entirety to read a region, use Open TIFF file in Windows. Filtered and protective-mask previews are in Preparation and can be enlarged with F11 at their saved display resolution.',
       'Если для чтения участка большого TIFF нужно декодировать всю серию, воспользуйтесь кнопкой «Открыть файл TIFF в Windows». Фильтрация и защитная маска доступны во вкладках «Подготовки». F11 увеличивает их до полного экрана в сохранённом разрешении предпросмотра.',
       'אם קריאת אזור בקובץ TIFF גדול מחייבת פענוח של כל הסדרה, השתמשו בפתיחת קובץ TIFF ב־Windows. תצוגות הסינון ומסכת ההגנה נמצאות בהכנה. F11 פותח אותן במסך מלא ברזולוציית התצוגה השמורה.'),
), parameters=('channel', 'plane'))

from .view_help_topics import TOPIC_TEXT as _VIEW_HELP
for _key, (_title, *_paragraphs) in _VIEW_HELP.items():
    TOPICS[_key] = dict(title=_t(*_title), paragraphs=tuple(_t(*paragraph) for paragraph in _paragraphs), parameters=())
_RELATED['preparation'] = ('prep_source', 'prep_filtering', 'prep_mask', 'prep_resolution', 'channel_composite') + _RELATED['preparation']
_RELATED['tiles'] = ('tile_overview', 'tile_model', 'tile_native', 'tile_ownership', 'tile_polygons') + _RELATED['tiles']
_RELATED['workspace'] += ('interface_scale',)
_RELATED['settings'] += ('interface_scale', 'editor_cursor')
_RELATED['prep_filtering'] = ('prep_source', 'prep_mask', 'prep_resolution', 'image_levels')
_RELATED['prep_mask'] = ('prep_filtering', 'prep_resolution')
_RELATED['tile_native'] = ('tile_model', 'tile_ownership', 'tile_editor')
TOPICS['results']['paragraphs'] += (
    _t('In Charts, drag inside the plot to pan and use the wheel to zoom around the pointer. Home on the toolbar resets the view. Drag the horizontal divider to resize the chart, or collapse Chart settings to use the full height. Open charts in a separate window lets you move and maximize the window. Chart colors sets data color, background and the palette for covariance and correlation matrices.',
       'В «Графиках» перетаскивайте область построения для панорамирования и используйте колесо для приближения вокруг указателя. Кнопка «Домой» возвращает исходный вид. Перетаскивайте горизонтальный разделитель или сверните «Настройки графика», чтобы использовать всю высоту. Отдельное окно графиков можно перемещать и разворачивать. В меню «Цвета графика» меняются цвет данных, фон и палитра матриц ковариации и корреляции.',
       'בתרשימים גררו בתוך התרשים להזזה והשתמשו בגלגלת לזום סביב הסמן. כפתור הבית בסרגל מחזיר לתצוגה הראשונית. גררו את המפריד האופקי לשינוי הגודל או כווצו את הגדרות התרשים לשימוש בכל הגובה. אפשר להזיז ולהגדיל חלון תרשימים נפרד. צבעי התרשים משנים את צבע הנתונים, הרקע והלוח למטריצות שונות משותפת ומתאם.'),
)
TOPICS['editor_cursor']['paragraphs'] += (
    _t('The Drawing cursor list displays a picture of each shape next to its name. The icon beside the selected name shows the current choice.',
       'В списке «Курсор рисования» рядом с названием показана форма каждого указателя. Значок рядом с выбранным названием показывает текущую форму.',
       'ברשימת סמן הציור מוצגת תמונה של כל צורה לצד שמה. הסמל לצד השם הנבחר מציג את הצורה הנוכחית.'),
    _t('In Tiles select a tile and click Edit selected tile above the image. The Drawing cursor menu is directly below the editing tool. It applies during drawing, including the brush and eraser. Choose the starting cursor for both editors in Settings → Appearance.',
       'В «Тайлах» выберите тайл и нажмите «Редактировать выбранный тайл» над изображением. Меню «Курсор рисования» находится под выбором инструмента. Оно действует при рисовании, в том числе кистью и ластиком. Начальный курсор обоих редакторов выбирается в «Настройки → Внешний вид».',
       'באריחים בחרו אריח ולחצו עריכת האריח הנבחר מעל לתמונה. תפריט סמן הציור נמצא מתחת לבחירת הכלי. הוא חל בעת ציור, כולל במברשת ובמחק. סמן התחלתי לשני העורכים נקבע בהגדרות → מראה.'),
)
TOPICS['image_levels']['paragraphs'] += (
    _t('The display maps each input x to round(255 × clip((x − black)/(white − black), 0, 1)). Raising brightness moves the interval toward lower inputs. Raising contrast makes the interval narrower. A bright band may become saturated and faint background may become visible. Gamma is a nonlinear power curve. Bilateral and white top-hat also use nearby pixels. Display levels only affect the view or a displayed-image export.',
       'Просмотр переводит каждое значение x в round(255 × clip((x − чёрный)/(белый − чёрный), 0, 1)). Увеличение яркости сдвигает интервал к более слабому сигналу. Увеличение контраста сужает интервал. Яркая полоса может пересветиться, а слабый фон стать заметным. Гамма использует нелинейную степенную кривую. Bilateral и white top-hat также учитывают соседние пиксели. Уровни действуют на просмотр и экспорт видимого изображения.',
       'התצוגה ממפה כל ערך x באמצעות עיגול של 255 כפול המיקום היחסי בין שחור ללבן, עם חיתוך לטווח 0 עד 1. העלאת בהירות מזיזה את הטווח לערכי קלט נמוכים יותר. העלאת ניגודיות מצמצמת את הטווח. פס בהיר עלול להגיע לרוויה ורקע חלש עשוי להתגלות. גאמה משתמשת בעקומת חזקה לא ליניארית. Bilateral ו־white top-hat משתמשים גם בפיקסלים סמוכים. הרמות משפיעות על התצוגה ועל ייצוא התמונה המוצגת.'),
)

TOPICS['database'] = dict(title=_t('Project database and backups', 'База данных проекта и резервные копии', 'מסד הנתונים של הפרויקט וגיבויים'), paragraphs=(
    _t('Open Help → Project database to check the saved project catalog, browse datasets or history in pages of 100 rows, and create a metadata-only backup. This window is unavailable during processing. F1 opens this guide. The catalog contains saved values; unsaved settings on the form are not included. Search terms: SQLite, database, catalog, backup, recovery.',
       'Откройте «Справка → База данных проекта», чтобы проверить каталог сохранённого проекта, просмотреть наборы и историю страницами по 100 строк или сделать копию метаданных. Во время обработки окно недоступно. F1 открывает это руководство. Каталог содержит сохранённые значения; несохранённые настройки формы в него не входят. Поиск: SQLite, база данных, каталог, резервная копия, восстановление.',
       'פתחו עזרה ← מסד הנתונים של הפרויקט לבדיקת קטלוג הפרויקט השמור, לעיון במערכים ובהיסטוריה בעמודים של 100 שורות ולגיבוי מטא־נתונים בלבד. החלון אינו זמין בזמן עיבוד. F1 פותח מדריך זה. הקטלוג מכיל ערכים שמורים; הגדרות טופס שלא נשמרו אינן כלולות. מילות חיפוש: SQLite, מסד נתונים, קטלוג, גיבוי, שחזור.'),
    _t('project.json remains the authoritative project record. Saving it also updates the derived project.sqlite3 catalog using one transaction. TIFFs, native/model tiles, validity masks, YOLO TXT, measurement CSVs, manual labels and models remain separate files. A SHA-256 check refuses SQL queries against a catalog that no longer matches the JSON. Current means that metadata matches; it does not certify that images exist or that a measurement is scientifically current.',
       'project.json остаётся основным документом проекта. При его сохранении производный каталог project.sqlite3 обновляется одной транзакцией. TIFF, native/model-тайлы, маски принадлежности, YOLO TXT, CSV измерений, ручные классы и модели остаются отдельными файлами. Проверка SHA-256 запрещает SQL-запросы к каталогу, который не совпадает с JSON. «Актуален» означает соответствие метаданных; это не проверка наличия изображений или научной актуальности измерений.',
       'project.json נשאר הרשומה הקובעת של הפרויקט. שמירתו מעדכנת גם את קטלוג project.sqlite3 הנגזר בעסקה אחת. TIFF, אריחי מקור ומודל, מסכות תקפות, YOLO TXT, CSV של מדידות, תוויות ידניות ומודלים נשארים קבצים נפרדים. בדיקת SHA-256 דוחה שאילתות SQL לקטלוג שאינו תואם ל־JSON. מעודכן מציין התאמת מטא־נתונים; אין בכך אימות שקיימות תמונות או שהמדידה עדכנית מבחינה מדעית.'),
    _t('Refresh catalog creates a missing index or updates an outdated one from the saved JSON. For example, after an older release changes project.json, refresh before browsing history. Rebuild catalog repairs a damaged index and preserves its old bytes under backups/Database_catalog_001. It changes only the derived index. An unrelated database or newer schema is refused and preserved. Catalog failure does not undo a successful JSON save. Opening a legacy project alone does not create a database.',
       '«Обновить каталог» создаёт отсутствующий индекс или обновляет устаревший по сохранённому JSON. Например, после изменения project.json старой версией программы обновите каталог перед просмотром истории. «Пересоздать каталог» восстанавливает повреждённый индекс с сохранением прежних байтов в backups/Database_catalog_001. Меняется только производный индекс. Чужая база или более новая схема не заменяется. Сбой каталога не отменяет успешное сохранение JSON. Само открытие старого проекта не создаёт базу.',
       'עדכון הקטלוג יוצר אינדקס חסר או מעדכן אינדקס ישן מה־JSON השמור. למשל, אחרי שגרסה ישנה משנה project.json, עדכנו לפני עיון בהיסטוריה. בנייה מחדש מתקנת אינדקס פגום ושומרת את הבתים הישנים תחת backups/Database_catalog_001. רק האינדקס הנגזר משתנה. מסד זר או סכמה חדשה יותר נדחים ונשמרים. כשל בקטלוג אינו מבטל שמירת JSON מוצלחת. פתיחת פרויקט ישן לבדה אינה יוצרת מסד.'),
    _t('Back up project metadata creates a new Project_metadata_YYYY-MM-DD_001 folder with matching JSON and SQLite snapshots and a METADATA_ONLY notice. Existing destinations are never overwritten. This copy excludes images, masks, annotations, labels, measurement CSVs and trained models. For a complete backup, finish or stop the job, close all SoLoData windows and copy the entire project folder to another disk. Reopening the copy may still require path relocation for older absolute references; automatic portable-project relocation is not implemented.',
       '«Копия метаданных проекта» создаёт новую папку Project_metadata_YYYY-MM-DD_001 с согласованными снимками JSON и SQLite и предупреждением METADATA_ONLY. Существующие папки не перезаписываются. В копию не входят изображения, маски, разметка, ручные метки, CSV измерений и обученные модели. Для полной копии завершите или остановите задание, закройте все окна SoLoData и скопируйте всю папку проекта на другой диск. При открытии копии старые абсолютные ссылки могут потребовать перенастройки путей; автоматический перенос путей проекта пока не реализован.',
       'גיבוי מטא־נתוני הפרויקט יוצר תיקייה חדשה Project_metadata_YYYY-MM-DD_001 עם תמונות מצב תואמות של JSON ו־SQLite והודעת METADATA_ONLY. תיקיות קיימות אינן נדרסות. הגיבוי אינו כולל תמונות, מסכות, סימונים, תוויות ידניות, CSV של מדידות או מודלים מאומנים. לגיבוי מלא סיימו או עצרו את המשימה, סגרו את כל חלונות SoLoData והעתיקו את כל תיקיית הפרויקט לכונן אחר. פתיחת ההעתק עשויה לדרוש התאמת נתיבים מוחלטים ישנים; התאמת נתיבי פרויקט אוטומטית טרם מומשה.'),
    _t('Keep the working project on a local disk. A shared SQLite file on a network drive or simultaneous editing of a cloud-synchronized project is not a supported collaboration mode. SQLite is not encryption or a permission system. Future multi-user access needs a server API, authentication and a server database. The catalog does not accelerate image filters or replace object-table storage.',
       'Рабочий проект храните на локальном диске. Общий SQLite-файл на сетевом диске или одновременное редактирование синхронизируемого облаком проекта не является поддерживаемой совместной работой. SQLite не заменяет шифрование и права доступа. Для будущей работы нескольких пользователей нужны серверный API, вход пользователей и серверная база. Каталог не ускоряет фильтры изображений и не заменяет хранение таблиц объектов.',
       'שמרו את הפרויקט הפעיל בכונן מקומי. קובץ SQLite משותף בכונן רשת או עריכה בו־זמנית של פרויקט מסונכרן לענן אינם מצב שיתוף נתמך. SQLite אינו הצפנה או מערכת הרשאות. עבודה עתידית של כמה משתמשים דורשת API שרת, הזדהות ומסד נתונים שרתי. הקטלוג אינו מאיץ מסנני תמונה ואינו מחליף אחסון טבלאות עצמים.'),
), parameters=())
_RELATED['database'] = ('sources', 'recovery', 'export')
_RELATED['sources'] = _RELATED.get('sources', ()) + ('database',)

_LABEL_STORAGE_HELP = (
    _t('Assigning a type saves only that object’s target and its audit event in manual_object_labels.sqlite3 beside the measurement. The feature CSV and project JSON are not rewritten on each click. The validated feature snapshot is reused while its file revision is unchanged. The gallery and unfiltered table update only the changed object; active text/class/unclassified filters may rebuild their visible selection.',
       'При выборе типа в manual_object_labels.sqlite3 рядом с измерением сохраняются только метка выбранного объекта и событие её изменения. CSV признаков и JSON проекта не переписываются на каждом нажатии. Проверенная таблица признаков используется повторно, пока версия её файла не изменилась. Галерея и таблица без фильтров обновляют только выбранный объект; активные фильтры текста, класса или неразмеченных объектов могут перестраивать видимый список.',
       'בחירת סוג שומרת רק את תווית העצם ואת אירוע השינוי ב־manual_object_labels.sqlite3 לצד המדידה. קובצי CSV ו־JSON של הפרויקט אינם נכתבים מחדש בכל לחיצה. תמונת התכונות שנבדקה משמשת שוב כל עוד גרסת הקובץ לא השתנתה. הגלריה והטבלה ללא מסננים מעדכנות רק את העצם ששונה; מסנני טקסט, מחלקה או עצמים ללא תיוג עשויים לבנות מחדש את הבחירה הגלויה.'),
    _t('Old manual_object_labels.json files are read without conversion until the first change. That change validates the measurement and imports every existing target in one transaction; the original JSON remains byte-identical. Old class catalogs are interpreted by stable class keys. For example, legacy agglomeration ID 2 becomes current ID 4. Corrections copy current targets for unchanged objects into the new measurement; undo returns to the parent’s intact targets.',
       'Старые manual_object_labels.json читаются без переноса до первого изменения. При нём проверяется версия измерения и все существующие метки переносятся одной транзакцией; исходный JSON остаётся побайтово прежним. Старый каталог определяется по стабильным ключам классов. Например, прежний ID агломерации 2 переводится в текущий 4. Исправления масок переносят актуальные метки неизменённых объектов в новое измерение; отмена возвращает неповреждённые метки родителя.',
       'קובצי manual_object_labels.json ישנים נקראים ללא המרה עד לשינוי הראשון. השינוי בודק את גרסת המדידה ומייבא את כל התוויות בעסקה אחת; קובץ JSON המקורי נשאר זהה בית־לבית. קטלוגים ישנים מפורשים לפי מפתחות מחלקה קבועים. למשל, מזהה צבר ישן 2 הופך למזהה הנוכחי 4. תיקוני מסכות מעתיקים תוויות עדכניות של עצמים שלא השתנו למדידה החדשה; ביטול מחזיר את תוויות מדידת האב בשלמותן.'),
    _t('More class controls → Export label snapshot (JSON) writes all current targets as a separate compatibility file. Use that snapshot with older readers on a separate project copy. It does not replace the active database or the original JSON. Training CSV, model evaluation and predictions always read current targets. Re-extraction creates a fresh measurement without old targets.',
       '«Дополнительные действия → Экспорт снимка меток (JSON)» записывает все актуальные метки в отдельный совместимый файл. Используйте этот снимок со старой программой на отдельной копии проекта. Он не заменяет действующую базу или исходный JSON. Обучающий CSV, оценка моделей и прогнозы читают актуальные метки. Полный повторный расчёт создаёт новое измерение без прежних меток.',
       'בקרות סיווג נוספות ← ייצוא תמונת מצב של תוויות (JSON) שומרות את כל התוויות העדכניות בקובץ תאימות נפרד. השתמשו בו עם קוראים ישנים בעותק נפרד של הפרויקט. הוא אינו מחליף את מסד הנתונים הפעיל או את JSON המקורי. CSV לאימון, הערכת מודלים ותחזיות קוראים את התוויות העדכניות. חישוב מדידה מחדש מתחיל ללא תוויות קודמות.'),
    _t('The target database is authoritative user data; it cannot be rebuilt from the old JSON. Keep manual_object_labels.sqlite3, manual_object_labels_storage.json and the original JSON in a full project backup. If the database is missing or damaged, restore that backup. If an older program changes the original JSON after conversion, editing/export stops rather than silently choosing one copy. The audit is committed with each target and recovered after reopening, even before the next project JSON save.',
       'База меток содержит основные пользовательские данные; восстановить её из старого JSON нельзя. В полной копии проекта сохраняйте manual_object_labels.sqlite3, manual_object_labels_storage.json и исходный JSON. При отсутствии или повреждении базы восстановите резервную копию. Если старая программа изменит исходный JSON после переноса, назначение классов и экспорт остановятся, чтобы не выбирать версию молча. История записывается вместе с каждой меткой и восстанавливается при открытии даже до следующего сохранения JSON проекта.',
       'מסד התוויות הוא נתוני המשתמש הקובעים; אי אפשר לבנות אותו מחדש מ־JSON הישן. כללו את manual_object_labels.sqlite3, manual_object_labels_storage.json ואת JSON המקורי בגיבוי מלא. אם המסד חסר או פגום, שחזרו את הגיבוי. אם תוכנה ישנה משנה את JSON המקורי לאחר ההמרה, העריכה והייצוא נעצרים במקום לבחור עותק בשקט. יומן השינויים נשמר עם כל תווית ומשוחזר בפתיחה גם לפני שמירת JSON נוספת של הפרויקט.'),
)
for _topic in ('manual_types', 'export', 'database'):
    TOPICS[_topic]['paragraphs'] += _LABEL_STORAGE_HELP

_HELP_FOLDERS = (
    (_t('01 · Start and sources', '01 · Начало и исходники', '01 · התחלה ומקורות'), ('getting_started', 'sources', 'database')),
    (_t('02 · Preparation', '02 · Подготовка', '02 · הכנה'),
     ('preparation', 'prep_source', 'prep_filtering', 'prep_mask', 'prep_resolution', 'source_viewer', 'channel_composite')),
    (_t('03 · Tiles', '03 · Тайлы', '03 · אריחים'),
     ('tiles', 'tile_overview', 'tile_model', 'tile_native', 'tile_ownership', 'tile_polygons',
      'black_tiles', 'tile_editor', 'editor_cursor')),
    (_t('04 · Segmentation', '04 · Сегментация', '04 · פילוח'),
     ('segmentation', 'segmentation_review', 'merge_objects', 'mask_correction', 'delete_masks', 'pixel_segmentation')),
    (_t('05 · Object labeling', '05 · Разметка объектов', '05 · תיוג עצמים'), ('manual_types',)),
    (_t('06 · Model training and review', '06 · Обучение и проверка', '06 · אימון ובדיקה'),
     ('model_evaluation', 'model_fit', 'training_charts', 'tree_impurity', 'confusion_matrix',
      'permutation_importance', 'evaluation_gallery', 'object_prediction_review')),
    (_t('07 · Results and export', '07 · Результаты и экспорт', '07 · תוצאות וייצוא'), ('results', 'export')),
)
_WORKSPACE_FOLDER = _t('Workspace and troubleshooting', 'Рабочая область и устранение ошибок', 'סביבת עבודה ופתרון בעיות')

_PARAMETER_STARTERS = {
    SOURCES: _t('Start here to select which pixels to process. Channel chooses a color or acquisition channel. Plane chooses one slice or time point. Pixel size converts source pixels to physical units when there is valid calibration.',
                'Начните здесь, чтобы выбрать пиксели для обработки. Канал выбирает цвет или канал съёмки. Плоскость выбирает один срез или момент времени. Размер пикселя переводит исходные пиксели в физические единицы при известной калибровке.',
                'התחילו כאן כדי לבחור אילו פיקסלים לעבד. הערוץ בוחר צבע או ערוץ רכישה. המישור בוחר פרוסה או נקודת זמן אחת. גודל הפיקסל ממיר פיקסלי מקור ליחידות פיזיות כשיש כיול תקף.'),
    FILTERS: _t('Compare the same region before and after filtering. Bilateral smooths noise near similar pixels, top-hat removes slowly varying bright background, and gamma changes contrast by brightness. For example, gamma 1 leaves brightness unchanged. With gamma 1.2, faint signals and faint background both become brighter.',
                'Сравнивайте одну и ту же область до и после фильтрации. Bilateral сглаживает шум среди похожих пикселей, top-hat убирает плавно меняющийся фон для выделения светлых деталей, а gamma меняет яркость нелинейно. При gamma 1 яркость сохраняется. При gamma 1,2 становятся светлее и слабые сигналы, и слабый фон.',
                'השוו אותו אזור לפני ואחרי הסינון. Bilateral מחליק רעש בין פיקסלים דומים, top-hat מפחית רקע המשתנה באיטיות כדי להדגיש פרטים בהירים, ו־gamma משנה בהירות באופן לא ליניארי. gamma של 1 שומר על הבהירות. ב־1.2 גם אות חלש וגם רקע חלש מתבהרים.'),
    MASK: _t('Inspect the protective mask before preparing tiles. A lower threshold can include more faint signal. Closing fills small gaps and dilation adds a margin around white areas. A thicker protective mask can leave fewer paths for tile boundaries.',
             'Проверьте защитную маску перед нарезкой. Более низкий порог может включить больше слабого сигнала. Замыкание заполняет небольшие разрывы, а расширение добавляет запас вокруг белых областей. Более широкая защитная маска может оставить меньше путей для границ тайлов.',
             'בדקו את מסכת ההגנה לפני חיתוך לאריחים. סף נמוך יותר עשוי לכלול יותר אות חלש. סגירה ממלאת פערים קטנים והרחבה מוסיפה שוליים סביב אזורים לבנים. מסכה עבה יותר עשויה להשאיר פחות נתיבים לגבולות האריחים.'),
    TILING: _t('Tile size sets the model canvas. The search window controls where the slicer looks for a boundary in source pixels. Check the boundary map and the native tile after a trial run. A native crop can exceed the model canvas when it must hold an entire protected component.',
               'Размер тайла задаёт размер изображения для модели. Окно поиска определяет, где искать границу в пикселях исходника. После пробного запуска проверьте карту границ и native-тайл. Исходный фрагмент может быть больше модельного поля, чтобы вместить целый защищённый компонент.',
               'גודל האריח קובע את גודל תמונת המודל. חלון החיפוש קובע איפה מחפשים גבול בפיקסלי המקור. לאחר ריצת ניסיון בדקו את מפת הגבולות ואת אריח המקור. חיתוך המקור יכול להיות גדול מתמונת המודל כדי להכיל רכיב מוגן שלם.'),
    MEASURE: _t('These settings change which pixels count as a measured object. Compare verification masks and feature values after a change. A size threshold can remove small components, so check whether genuine particles disappear along with noise.',
                'Эти настройки меняют, какие пиксели попадут в измеряемый объект. После изменения сравните проверочные маски и значения признаков. Порог размера удаляет мелкие компоненты. Проверьте, не исчезли ли вместе с шумом настоящие частицы.',
                'הגדרות אלו משנות אילו פיקסלים ייחשבו לעצם נמדד. אחרי שינוי השוו את מסכות האימות ואת ערכי התכונות. סף גודל יכול להסיר רכיבים קטנים. בדקו אם חלקיקים אמיתיים נעלמו יחד עם הרעש.'),
}
register_translations(_RU, hebrew=_HE)


class HelpCenter(QtWidgets.QDialog):
    """A reusable modeless reader. Never writes settings or project files."""

    def __init__(self, parent=None, current_settings=None, language=None):
        super().__init__(parent)
        self.language = language or get_language()
        self.current_settings = deepcopy(current_settings) if current_settings is not None else {}
        self._current_topic = 'getting_started'
        self._current_parameter = None
        self.setModal(False)
        self.resize(1120, 760)
        self.setMinimumSize(760, 500)
        layout = QtWidgets.QVBoxLayout(self)
        self.search = QtWidgets.QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setObjectName('helpSearch')
        self.search.textChanged.connect(self._search_changed)
        toolbar = QtWidgets.QHBoxLayout()
        self.home_button = QtWidgets.QPushButton()
        self.home_button.clicked.connect(lambda: self.open_topic('getting_started'))
        toolbar.addWidget(self.home_button)
        toolbar.addWidget(self.search, 1)
        layout.addLayout(toolbar)
        self.summary = QtWidgets.QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.navigation = QtWidgets.QTreeWidget()
        self.navigation.setHeaderHidden(True)
        self.navigation.setMinimumWidth(210)
        self.navigation.setMaximumWidth(330)
        self.navigation.setWordWrap(True)
        self.navigation.currentItemChanged.connect(self._navigation_changed)
        split.addWidget(self.navigation)
        self.pages = QtWidgets.QStackedWidget()
        self.browser = QtWidgets.QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._follow_link)
        self.pages.addWidget(self.browser)
        parameter_page = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.parameter_table = QtWidgets.QTableWidget(0, 4)
        self.parameter_table.setObjectName('parameterReferenceTable')
        self.parameter_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.parameter_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.parameter_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.parameter_table.verticalHeader().hide()
        self.parameter_table.horizontalHeader().setStretchLastSection(True)
        self.parameter_table.itemSelectionChanged.connect(self._parameter_row_selected)
        parameter_page.addWidget(self.parameter_table)
        self.details = QtWidgets.QTextBrowser()
        self.details.setOpenLinks(False)
        self.details.anchorClicked.connect(self._follow_link)
        parameter_page.addWidget(self.details)
        parameter_page.setChildrenCollapsible(False)
        parameter_page.setSizes([260, 390])
        self.pages.addWidget(parameter_page)
        split.addWidget(self.pages)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)
        self.close_button = QtWidgets.QPushButton()
        self.close_button.clicked.connect(self.close)
        footer = QtWidgets.QHBoxLayout()
        footer.addStretch()
        footer.addWidget(self.close_button)
        layout.addLayout(footer)
        self.search_shortcut = QtGui.QShortcut(QtGui.QKeySequence('Ctrl+F'), self)
        self.search_shortcut.activated.connect(self.search.setFocus)
        self.retranslate(self.language)

    def _text(self, text, **values):
        return tr(text, language=self.language, **values)

    def retranslate(self, language=None):
        self.language = language or get_language()
        self.setLayoutDirection(QtCore.Qt.LayoutDirection.RightToLeft if self.language == 'he' else QtCore.Qt.LayoutDirection.LeftToRight)
        self.setLocale(QtCore.QLocale({'en': 'en_US', 'ru': 'ru_RU', 'he': 'he_IL'}.get(self.language, 'en_US')))
        self.setWindowTitle(self._text('SoLoData help'))
        self.search.setPlaceholderText(self._text('Search application help or a parameter key'))
        self.home_button.setText(self._text('Start'))
        self.summary.setText(self._text('Reference version {version}. Help is read-only; factory defaults are independent of the current project.', version=DEFAULTS_VERSION))
        self.close_button.setText(self._text('Close'))
        self._search_changed()

    def refresh_settings(self, values):
        # Take a read-only snapshot of the form, which can include unsaved
        # values. The reference table reads factory defaults separately.
        self.current_settings = deepcopy(values) if values is not None else {}
        self._populate_parameter_table(self.search.text().strip().casefold())
        if self.pages.currentIndex() == 1 and self._current_parameter:
            self._show_parameter(self._current_parameter)

    def _format_value(self, value, key=None):
        if value is _MISSING:
            return self._text('Not supplied')
        if value is None:
            return self._text('Automatic' if key in ('search_window_end', 'straight_shift_left') else 'Not set')
        if isinstance(value, bool):
            return self._text('On' if value else 'Off')
        if isinstance(value, float):
            return format(value, '.12g')
        return str(value)

    def _parameter_matches(self, entry, query):
        text = ' '.join([*(str(value) for value in entry.values()),
                         self._text(_PARAMETER_GUIDANCE[entry['key']])]).casefold()
        return all(word in text for word in query.split())

    def _topic_matches(self, key, topic, query):
        sections = [text for section in _GUIDED.get(key, ()) for text in section]
        if key == 'getting_started':
            sections.extend(_FIRST_RUN)
        text = ' '.join([key, *topic['parameters'], *(self._text(p) for p in
                        (topic['title'], *sections, *topic['paragraphs']))]).casefold()
        return all(word in text for word in query.split())

    def _search_changed(self, *_):
        # Rebuild both the topic and parameter results. Retain the open page
        # by technical key when it still matches after filtering.
        query = self.search.text().strip().casefold()
        entries = self._populate_parameter_table(query)
        wanted = ('parameter', self._current_parameter) if self._current_parameter else ('topic', self._current_topic)
        self.navigation.blockSignals(True)
        self.navigation.clear()
        self._nav_items = {}
        def article(parent, title, kind, key):
            item = QtWidgets.QTreeWidgetItem(parent, [title])
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, (kind, key))
            item.setToolTip(0, title)
            self._nav_items[kind, key] = item
            return item

        grouped = {key for _, keys in _HELP_FOLDERS for key in keys}
        remaining = tuple(key for key in TOPICS if key not in grouped)
        for name, keys in (*_HELP_FOLDERS, (_WORKSPACE_FOLDER, remaining)):
            matches = [key for key in keys if self._topic_matches(key, TOPICS[key], query)]
            if matches:
                folder = QtWidgets.QTreeWidgetItem(self.navigation, [self._text(name)])
                folder.setFlags(folder.flags() & ~QtCore.Qt.ItemFlag.ItemIsSelectable)
                for key in matches:
                    article(folder, self._text(TOPICS[key]['title']), 'topic', key)
        if entries or not query:
            parameters = article(self.navigation, self._text('Parameters and factory defaults'), 'topic', 'parameters')
            titles = {entry['key']: entry['title'] for entry in entries}
            for group in _PARAMETER_GROUPS:
                keys = [key for key, entry in PARAMETER_REFERENCE.items() if entry.group == group and key in titles]
                if keys:
                    folder = QtWidgets.QTreeWidgetItem(parameters, [self._text(group)])
                    folder.setFlags(folder.flags() & ~QtCore.Qt.ItemFlag.ItemIsSelectable)
                    for key in keys:
                        article(folder, titles[key], 'parameter', key)
        selected = self._nav_items.get(wanted) or next(iter(self._nav_items.values()), None)
        if query:
            self.navigation.expandAll()
        if selected is not None:
            parent = selected.parent()
            while parent is not None:
                parent.setExpanded(True)
                parent = parent.parent()
            self.navigation.setCurrentItem(selected)
        self.navigation.blockSignals(False)
        if selected is not None:
            self._navigation_changed(selected)
        else:
            self.pages.setCurrentIndex(0)
            self.browser.setPlainText(self._text('No matching help. Try a shorter term or a technical key such as gamma.'))

    def _navigation_changed(self, item, previous=None):
        if item is None:
            return
        payload = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if payload is None:
            return
        kind, key = payload
        if kind == 'parameter':
            self._show_parameter(key)
        else:
            self._current_topic = key
            self._current_parameter = None
            if key == 'parameters':
                self.pages.setCurrentIndex(1)
                with QtCore.QSignalBlocker(self.parameter_table):
                    self.parameter_table.clearSelection()
                self.details.setHtml(self._parameter_index_html())
            else:
                self.pages.setCurrentIndex(0)
                self.browser.setHtml(self._topic_html(key))

    def _populate_parameter_table(self, query):
        entries = [entry for entry in reference_rows(self.language) if self._parameter_matches(entry, query)]
        table = self.parameter_table
        with QtCore.QSignalBlocker(table):
            table.clearSelection()
            table.setRowCount(len(entries))
            table.setHorizontalHeaderLabels([self._text(label) for label in
                                             ('Parameter', 'Factory default', 'Current value', 'Valid range')])
            for row, entry in enumerate(entries):
                key = entry['key']
                values = (
                    entry['title'] + '\n' + key,
                    self._format_value(entry['factory_default'], key),
                    self._format_value(self.current_settings.get(key, _MISSING), key),
                    entry['valid_range'],
                )
                for column, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(value)
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, key)
                    table.setItem(row, column, item)
            table.resizeColumnsToContents()
            table.resizeRowsToContents()
        return entries

    def _parameter_row_selected(self):
        items = self.parameter_table.selectedItems()
        if items:
            key = items[0].data(QtCore.Qt.ItemDataRole.UserRole)
            item = self._nav_items.get(('parameter', key))
            if item is not None:
                with QtCore.QSignalBlocker(self.navigation):
                    item.parent().setExpanded(True)
                    item.parent().parent().setExpanded(True)
                    self.navigation.setCurrentItem(item)
            self._show_parameter(key)

    def _parameter_index_html(self):
        body = '<h1>' + self._inline(self._text('Parameters and factory defaults')) + '</h1>'
        body += '<p>' + self._inline(self._text('Select a row in the table to read its detailed guide here.')) + '</p>'
        groups = list(_PARAMETER_GROUPS)
        body += '<p>' + ' · '.join(f'<a href="#group-{index}">{self._inline(self._text(group))}</a>'
                                  for index, group in enumerate(groups)) + '</p>'
        for paragraph in (
            'Choose a parameter by the stage where you use it. You can also search by name or key, or click the question mark beside a control in the main window.',
            'Factory default is the value shipped with the application. Current value is a snapshot of the control when Help reads it, and may include unsaved edits. For automatic calibration it can show the selected TIFF’s scale.',
            'Example: gamma is 1.2 at the factory, 1.1 in the last saved settings and 1.3 in the form. Restore saved settings brings back 1.1. Use factory default on the gamma field brings back 1.2.',
            'Make a comparison with one parameter changed at a time. Use the same image and region. Preview filters before preparing tiles, and inspect verification crops after changing measurement controls.',
        ):
            body += '<p>' + self._inline(self._text(paragraph)) + '</p>'
        body += '<p><a href="topic:settings">' + self._inline(self._text(TOPICS['settings']['title'])) + '</a></p>'
        for index, group in enumerate(groups):
            body += f'<h2><a name="group-{index}"></a>{self._inline(self._text(group))}</h2>'
            body += '<p>' + self._inline(self._text(_PARAMETER_STARTERS[group])) + '</p><ul>'
            body += ''.join('<li>' + self._parameter_link(key) + '</li>'
                            for key, entry in PARAMETER_REFERENCE.items() if entry.group == group)
            body += '</ul>'
        return self._html(body)

    def _parameter_link(self, key):
        title = self._text(PARAMETER_REFERENCE[key].title)
        return '<a href="parameter:' + key + '">' + self._inline(title) + '</a>'

    def _show_parameter(self, key):
        entry = parameter_entry(key, self.language)
        if entry is None:
            return
        self._current_topic = 'parameters'
        self._current_parameter = key
        self.pages.setCurrentIndex(1)
        table = self.parameter_table
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item.data(QtCore.Qt.ItemDataRole.UserRole) == key:
                with QtCore.QSignalBlocker(table):
                    flags = QtCore.QItemSelectionModel.SelectionFlag
                    table.setCurrentCell(row, 0, flags.ClearAndSelect | flags.Rows)
                    table.scrollToItem(item, QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible)
                break
        group = PARAMETER_REFERENCE[key].group
        location, topic = _PARAMETER_GROUPS[group]
        location = _PARAMETER_LOCATIONS.get(key, location)
        body = '<p><a href="topic:parameters">' + self._inline(self._text('All parameters')) + '</a></p>'
        body += '<h1>' + self._inline(entry['title']) + '</h1>'
        body += '<p><b>' + self._inline(self._text('Where to find it')) + '</b><br>' + self._inline(self._text(location)) + '</p>'
        body += '<p><code dir="ltr">' + self._inline(key) + '</code></p>'
        pairs = [('Factory default', self._format_value(entry['factory_default'], key)),
                 ('Current value', self._format_value(self.current_settings.get(key, _MISSING), key))]
        alignment = 'right' if self.language == 'he' else 'left'
        body += f'<table align="{alignment}" cellspacing="0" cellpadding="8" border="1"><tr>'
        body += ''.join('<th>' + self._inline(self._text(label)) + '</th>' for label, _ in pairs)
        body += '</tr><tr>' + ''.join('<td>' + self._inline(value) + '</td>' for _, value in pairs) + '</tr></table>'
        for label, value in (
            ('Try it and check the result', self._text(_PARAMETER_GUIDANCE[key])),
            ('How it works', entry['purpose']),
            ('Increase / enable', entry['increase']),
            ('Decrease / disable', entry['decrease']),
            ('Example', entry['example']),
            ('Important', entry['safety']),
        ):
            body += '<h3>' + self._inline(self._text(label)) + '</h3><p>' + self._inline(value) + '</p>'
        body += '<h3>' + self._inline(self._text('Pipeline validation and units')) + '</h3><p>'
        body += self._inline(entry['valid_range']) + '<br>' + self._inline(entry['unit']) + '</p>'
        body += '<p>' + self._inline(self._text('Desktop fields can have narrower limits than the pipeline rules. Available channels and slices depend on the TIFF.')) + '</p>'
        related = next((keys for keys in _PARAMETER_NEIGHBORS if key in keys), ())
        if related:
            body += '<h3>' + self._inline(self._text('Related parameters')) + '</h3><p>'
            body += ' · '.join(self._parameter_link(other) for other in related if other != key) + '</p>'
        body += '<p><a href="topic:' + topic + '">' + self._inline(self._text(TOPICS[topic]['title'])) + '</a></p>'
        self.details.setHtml(self._html(body))

    def _inline(self, value):
        text = str(value)
        if self.language != 'he':
            return escape(text)
        # Isolate left-to-right technical text within Hebrew prose. Match
        # half-open intervals as a unit so brackets stay with their endpoints.
        pattern = (r'\[\d+,\s*\d+\)|'
                   r'[A-Za-z0-9][A-Za-z0-9_./×^()*=+:µ²><−–-]*(?:[ \t]+[A-Za-z0-9_./×^()*=+:µ²><−–-]+)*')
        chunks, position = [], 0
        for match in re.finditer(pattern, text):
            chunks.append(escape(text[position:match.start()]))
            chunks.append('<span dir="ltr">\u2066' + escape(match.group()) + '\u2069</span>')
            position = match.end()
        chunks.append(escape(text[position:]))
        return ''.join(chunks)

    def _html(self, body):
        direction = 'rtl' if self.language == 'he' else 'ltr'
        return '<html dir="' + direction + '"><head><style>body{font-size:11pt;}p{margin:10px 0;}a{color:#188978;}code{font-family:Consolas;}</style></head><body>' + body + '</body></html>'

    def _topic_html(self, key):
        topic = TOPICS[key]
        body = '<h1>' + escape(self._text(topic['title'])) + '</h1>'
        related = []
        for destination in _RELATED.get(key, ()):
            title = TOPICS[destination]['title'] if destination in TOPICS else 'Parameters and factory defaults'
            related.append('<a href="topic:' + destination + '">' + escape(self._text(title)) + '</a>')
        related_html = '<p><b>' + escape(self._text('Related guides')) + '</b><br>' + ' · '.join(related) + '</p>'
        if related and key != 'getting_started':
            body += related_html
        sections = _GUIDED.get(key, ())
        for index, (heading, paragraph) in enumerate(sections):
            body += '<h2>' + escape(self._text(heading)) + '</h2><p>' + self._inline(self._text(paragraph)) + '</p>'
            if index == 0 and 'example_table' in topic:
                headers, rows = topic['example_table']
                body += '<table dir="ltr" border="1" cellspacing="0" cellpadding="6"><tr>'
                body += ''.join('<th>' + self._inline(self._text(cell)) + '</th>' for cell in headers)
                body += '</tr>' + ''.join(
                    '<tr>' + ''.join('<td>' + self._inline(self._text(cell)) + '</td>' for cell in row) + '</tr>'
                    for row in rows)
                body += '</table>'
        if key == 'getting_started':
            body += '<h2>' + escape(self._text('First run, step by step')) + '</h2><ol>'
            body += ''.join('<li style="margin-bottom:8px">' + self._inline(self._text(step)) + '</li>'
                            for step in _FIRST_RUN)
            body += '</ol>'
            if related:
                body += related_html
        if topic['parameters']:
            links = []
            for parameter in topic['parameters']:
                if parameter in PARAMETER_REFERENCE:
                    links.append(self._parameter_link(parameter))
            body += '<h3>' + escape(self._text('Related parameters')) + '</h3><p>' + ' · '.join(links) + '</p>'
        if sections and topic['paragraphs']:
            body += '<h2>' + escape(self._text('Details and reference')) + '</h2>'
        body += ''.join('<p>' + self._inline(self._text(paragraph)) + '</p>' for paragraph in topic['paragraphs'])
        return self._html(body)

    def open_parameter(self, key):
        if key not in PARAMETER_REFERENCE:
            return self.open_topic(_TOPIC_ALIASES.get(key, key))
        self._open_location('parameters', key)

    def open_topic(self, topic_id='getting_started'):
        topic_id = _TOPIC_ALIASES.get(topic_id, topic_id)
        if topic_id not in TOPICS and topic_id != 'parameters':
            topic_id = 'getting_started'
        self._open_location(topic_id)

    def _open_location(self, topic_id, parameter=None):
        self._current_topic = topic_id
        self._current_parameter = parameter
        with QtCore.QSignalBlocker(self.search):
            self.search.clear()
        self._search_changed()
        self.show()

    def _follow_link(self, url):
        # These internal schemes navigate the Help dialog independently of
        # the current language and leave the application form untouched.
        if url.scheme() == 'parameter':
            self.open_parameter(url.path())
        elif url.scheme() == 'topic':
            self.open_topic(url.path())
        elif url.isRelative() and url.hasFragment() and self.pages.currentIndex() == 1:
            self.details.scrollToAnchor(url.fragment())


# The reference node is separate from narrative topics, but participates in the
# same translation catalogue and search/navigation model.
register_translations({'Parameters and factory defaults': 'Параметры и заводские значения'},
                      hebrew={'Parameters and factory defaults': 'פרמטרים וברירות מחדל מקוריות'})
