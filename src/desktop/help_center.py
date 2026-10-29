"""Searchable, modeless application help with immutable factory references."""

from copy import deepcopy
from html import escape
import re

from src.default_settings import DEFAULTS_VERSION
from .i18n import get_language, register_translations, tr
from .parameter_reference import PARAMETER_REFERENCE, parameter_entry, reference_rows
from .qt import QtCore, QtGui, QtWidgets


_RU, _HE = {}, {}


def _t(english, russian, hebrew):
    _RU[english], _HE[english] = russian, hebrew
    return english


_t('SoLoData help', 'Справка SoLoData', 'עזרה של SoLoData')
_t('Search application help or a parameter key', 'Поиск по справке или ключу параметра', 'חיפוש בעזרה או לפי מפתח פרמטר')
_t('Parameter', 'Параметр', 'פרמטר')
_t('Factory default', 'Фиксированное значение', 'ערך ברירת מחדל מקורי')
_t('Current value', 'Текущее значение', 'ערך נוכחי')
_t('Valid range', 'Допустимые значения', 'טווח תקין')
_t('Purpose', 'Назначение', 'מטרה')
_t('Units', 'Единицы', 'יחידות')
_t('Increase / enable', 'Увеличение / включение', 'הגדלה / הפעלה')
_t('Decrease / disable', 'Уменьшение / выключение', 'הקטנה / כיבוי')
_t('Example', 'Пример', 'דוגמה')
_t('Important', 'Важно', 'חשוב')
_t('Related parameters', 'Связанные параметры', 'פרמטרים קשורים')
_t('Not supplied', 'Не передано', 'לא נמסר')
_t('Not set', 'Не задано', 'לא מוגדר')
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
        _t('SoLoData prepares microscopy images, detects or imports objects, measures their masks and helps you assign reviewed types. Its manual class panel is not a trained classifier. Random Forest training and inference are future modules.',
           'SoLoData подготавливает микроскопические изображения, выделяет или импортирует объекты, измеряет маски и помогает назначать проверенные типы. Панель ручных классов — не обученный классификатор. Обучение и применение Random Forest — будущие модули.',
           'SoLoData מכין תמונות מיקרוסקופיה, מזהה או מייבא עצמים, מודד את המסכות שלהם ומסייע בשיוך סוגים שנבדקו. לוח הסיווג הידני אינו מסווג מאומן. אימון וחיזוי של Random Forest הם מודולים עתידיים.'),
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
    ), parameters=('channel', 'plane', 'save_raw_tiles')),
    'preparation': dict(title=_t('Preparation and filters', 'Подготовка и фильтры', 'הכנה ומסננים'), paragraphs=(
        _t('Enabled grayscale steps run in order: bilateral denoising → white top-hat plus min–max normalization → reciprocal-gamma LUT. Switching a step off bypasses it while keeping its parameter values. Turning top-hat off also bypasses its normalization.',
           'Включённые фильтры идут по порядку: bilateral → white top-hat с min–max нормализацией → LUT с показателем 1/gamma. Выключенная стадия пропускается с сохранением параметров. Отключение top-hat пропускает и его нормализацию.',
           'שלבי האפור הפעילים פועלים לפי הסדר: החלקה בילטרלית ← white top-hat עם נרמול מינימום–מקסימום ← טבלת גאמה הפוכה. כיבוי שלב מדלג עליו ושומר את ערכיו. כיבוי top-hat מדלג גם על הנרמול שלו.'),
        _t('Gamma uses x^(1/gamma). Gamma 1 is identity; gamma above 1 brightens faint background as well as faint signal. Min–max normalization changes a value range, not a distribution into a Gaussian. A brighter image is not evidence of greater segmentation accuracy.',
           'Гамма использует x^(1/gamma). Гамма 1 — без изменения; выше 1 осветляются и слабый фон, и сигнал. Min–max меняет диапазон значений, а не превращает распределение в гауссово. Более яркая картинка не доказывает точность сегментации.',
           'גאמה משתמשת ב־x^(1/gamma). גאמה 1 היא זהות; מעל 1 מובהרים גם רקע חלש וגם אות חלש. נרמול מינימום–מקסימום משנה טווח ערכים, לא יוצר התפלגות גאוסית. תמונה בהירה יותר אינה ראיה לדיוק פילוח גבוה יותר.'),
        _t('A separate protective mask uses modified global Otsu ignoring zero intensity, threshold max(10, int(T × factor)), optional elliptical closing and dilation. Closing and dilation change mask dimensions. This routing mask is not the grayscale image, the annotation polygon or the thresholded measurement mask.',
           'Отдельная защитная маска использует глобальный Otsu без нулевой яркости, порог max(10, int(T × коэффициент)), замыкание и расширение эллипсом. Морфология меняет размеры маски. Она не равна серому изображению, полигону разметки или пороговой маске измерений.',
           'מסכת הגנה נפרדת משתמשת ב־Otsu גלובלי המתעלם מעוצמה אפס, בסף max(10, int(T × מקדם)) ובסגירה והרחבה אליפטיות אופציונליות. המורפולוגיה משנה את ממדי המסכה. מסכת הניתוב אינה תמונת האפור, מצולע התיוג או מסכת הסף למדידה.'),
        _t('Crop previews are approximate: crop normalization and Otsu can differ from full-image results. Compare the same crop with one changed setting at a time, then review a newly prepared run. Existing tiles keep the processing settings used to create them.',
           'Предпросмотр фрагмента приблизителен: нормализация и Otsu фрагмента могут отличаться от полного изображения. Сравнивайте тот же фрагмент, меняя один параметр, затем проверяйте новый набор. Готовые тайлы сохраняют настройки своего создания.',
           'תצוגה מקדימה של פרגמנט היא בקירוב: נרמול ו־Otsu מקומיים עשויים להיות שונים מתוצאות התמונה השלמה. השוו אותו פרגמנט תוך שינוי פרמטר אחד בכל פעם, ואז בדקו ריצה חדשה. אריחים קיימים שומרים את ההגדרות ששימשו ליצירתם.'),
    ), parameters=('enable_bilateral', 'enable_tophat', 'enable_gamma', 'gamma', 'otsu_safety_factor', 'bridge_kernel_size', 'buffer_kernel_size')),
    'tiles': dict(title=_t('Tiles, native scale and review', 'Тайлы, native-масштаб и проверка', 'אריחים, קנה מידה מקורי ובדיקה'), paragraphs=(
        _t('Each v3 tile has a fixed square model PNG, a native crop, an exact valid ownership mask and scale metadata. Large complete crops can be reduced into the model canvas while retaining native pixels for measurement. Padding is added on the right and bottom.',
           'У v3-тайла есть квадратный модельный PNG, native-фрагмент, точная маска принадлежности и масштаб. Большой целый фрагмент может уменьшаться в модельное поле; измерения сохраняют native-пиксели. Поля добавляются справа и снизу.',
           'לכל אריח v3 יש PNG ריבועי קבוע למודל, פרגמנט מקור, מסכת שיוך מדויקת ומטא־נתוני קנה מידה. פרגמנטים גדולים ושלמים יכולים להיות מוקטנים לתמונת המודל תוך שמירת פיקסלי המקור למדידה. ריפוד נוסף מימין ומלמטה.'),
        _t('Final ownership assigns every source pixel once and keeps whole 8-connected components of the supplied protective mask. Rectangular crops can overlap; valid_masks determines ownership. This does not prove that all biological objects were detected. The route alone may cross a diagonal corner; later component allocation repairs ownership.',
           'Итоговая принадлежность назначает каждый пиксель один раз и сохраняет целые 8-связные компоненты защитной маски. Прямоугольники могут пересекаться; принадлежность задаёт valid_masks. Это не доказывает нахождение всех биологических объектов. Маршрут может пройти между диагональными углами; затем распределение компонент исправляет принадлежность.',
           'השיוך הסופי מקצה כל פיקסל מקור פעם אחת ושומר רכיבים שלמים בקישוריות 8 במסכת ההגנה שסופקה. מלבני הפרגמנטים יכולים לחפוף; valid_masks קובע את השיוך. אין בכך הוכחה שכל העצמים הביולוגיים זוהו. המסלול עצמו עשוי לעבור בין פינות אלכסוניות; שיוך הרכיבים בהמשך מתקן את הבעלות על הפיקסלים.'),
        _t('Open prepared tiles expects one dataset folder containing model PNGs, native, valid_masks and overview JSON, not the parent of many datasets. Click the overview to select exact pixel ownership. Search and display filters only change the list; explicit Exclude or Restore changes active model PNGs while retaining native files and metadata.',
           '«Открыть тайлы» ожидает папку одного набора с модельными PNG, native, valid_masks и overview JSON, а не общий каталог. Нажатие на обзор выбирает точную принадлежность. Поиск меняет список; «Исключить»/«Вернуть» меняют активные PNG, сохраняя native и метаданные.',
           'פתיחת אריחים מוכנים דורשת תיקייה של מערך אחד עם PNG למודל, native, valid_masks ו־JSON של הסקירה, לא את תיקיית האב של כמה מערכים. לחיצה בסקירה בוחרת לפי שיוך מדויק. חיפוש ומסנני תצוגה משנים רק את הרשימה; החרגה או שחזור משנים את אריחי המודל הפעילים ושומרים את קובצי המקור והמטא־נתונים.'),
        _t('Inspect bright-region flags and boundary areas before marking the review complete. Flags are review hints, not predicted biological classes. Changed exclusions invalidate current measurements; new slicing runs must not reuse old tile IDs or annotations automatically.',
           'Проверьте яркие области и границы перед завершением проверки. Флаги — подсказки, а не биологические классы. Изменение исключений делает измерения неактуальными; новая нарезка не должна автоматически наследовать старые ID и разметку.',
           'בדקו אזורים בהירים וגבולות לפני סימון הבדיקה כהושלמה. הדגלים הם רמזי בדיקה, לא מחלקות ביולוגיות חזויות. שינוי החרגות מבטל את עדכניות המדידות; חלוקה חדשה אינה אמורה להשתמש אוטומטית במזהים ובתיוגים ישנים.'),
    ), parameters=('target_size', 'oversized_policy', 'min_corridor_width', 'seam_repulsion_power', 'overview_size')),
    'segmentation': dict(title=_t('Segmentation and annotations', 'Сегментация и разметка', 'פילוח ותיוגים'), paragraphs=(
        _t('Import YOLO segmentation TXT polygons matched to exact model-tile filenames. Coordinates are normalized to the model canvas; v3 maps them back into native space. Import checks names, class IDs, vertex count and coordinate ranges. No built-in trained YOLO or SAM inference runs here.',
           'Импортируйте YOLO segmentation TXT с точными именами модельных тайлов. Координаты нормированы на модельное поле; v3 переносит их в native. Проверяются имена, ID классов, число вершин и диапазон. Обученный YOLO или SAM внутри этого этапа не запускается.',
           'ייבאו מצולעי TXT של YOLO segmentation התואמים בדיוק לשמות אריחי המודל. הקואורדינטות מנורמלות למשטח המודל; v3 ממפה אותן למקור. הייבוא בודק שמות, מזהי מחלקות, מספר קודקודים וטווחים. כאן לא מופעל חיזוי של YOLO או SAM מאומנים.'),
        _t('Existing annotations only measures available TXT files. Require all needs a TXT for every active tile. Automatic fallback detects contours only where a TXT is missing. An existing empty TXT always means zero annotated objects. Automatically detected source classes are Unknown.',
           '«Только разметка» измеряет имеющиеся TXT. «Требовать все» требует TXT для каждого активного тайла. Автоматический режим ищет контуры только при отсутствии TXT. Пустой существующий TXT всегда означает ноль объектов. Исходный класс автоматических объектов — Unknown.',
           'מצב תיוגים קיימים בלבד מודד קובצי TXT זמינים. דרישת כולם מחייבת TXT לכל אריח פעיל. גיבוי אוטומטי מזהה קווי מתאר רק כאשר TXT חסר. קובץ TXT קיים וריק תמיד מציין אפס עצמים מתויגים. מחלקת המקור של עצמים אוטומטיים היא Unknown.'),
        _t('Inside each polygon or detected contour, local thresholding produces a measurement mask. Cleaned 8-connected components are split and filtered by minimum native area. Touching fibers are not separated by an implemented Frangi/hybrid method. Components inherit their source annotation class until you review manual targets.',
           'В полигоне или контуре локальный порог формирует маску измерений. Очищенные 8-связные компоненты разделяются и фильтруются по native-площади. Разделение соприкасающихся волокон Frangi/hybrid не реализовано. Компоненты наследуют исходный класс до ручной проверки.',
           'בתוך כל מצולע או קו מתאר, סף מקומי יוצר מסכת מדידה. רכיבים נקיים בקישוריות 8 מופרדים ומסוננים לפי שטח מקור מזערי. לא ממומשת הפרדת סיבים נוגעים באמצעות Frangi/hybrid. הרכיבים יורשים את מחלקת תיוג המקור עד לבדיקת היעדים הידניים.'),
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
        _t('v3 measures native source pixels. Area counts foreground pixels; with calibration s in µm/px, Area_um2=Area×s². Aspect_Ratio is equivalent-ellipse major/minor axis ratio, not curved fiber centerline length divided by thickness. A degenerate minor axis currently returns AR=1.0.',
           'v3 измеряет исходные native-пиксели. Area считает пиксели объекта; при калибровке s в µm/px Area_um2=Area×s². Aspect_Ratio — отношение осей эквивалентного эллипса, а не длина изогнутого волокна по скелету к толщине. При вырожденной малой оси сейчас AR=1.0.',
           'v3 מודד בפיקסלי המקור. Area סופר פיקסלי עצם; בכיול s במיקרומטר לפיקסל מתקבל Area_um2=Area×s². Aspect_Ratio הוא יחס צירי האליפסה השקולה, לא אורך קו המרכז של סיב מעוקל חלקי עוביו. כאשר הציר הקטן מנוון, מוחזר כיום AR=1.0.'),
        _t('Solidity is mask area divided by convex-hull area. Euler_Number describes connected components minus holes. Endpoints counts skeleton pixels with one neighbor; Branch_Points counts pixels with more than two neighbors, not merged graph junctions. A single crossing can therefore contribute several branch pixels.',
           'Solidity — площадь маски к площади выпуклой оболочки. Euler_Number — число компонент минус отверстия. Endpoints считает пиксели скелета с одним соседом; Branch_Points — с более чем двумя, а не объединённые узлы графа. Один перекрёсток может дать несколько пикселей ветвления.',
           'Solidity הוא שטח המסכה חלקי שטח המעטפת הקמורה. Euler_Number מתאר מספר רכיבים פחות חורים. Endpoints סופר פיקסלי שלד בעלי שכן אחד; Branch_Points סופר פיקסלים בעלי יותר משני שכנים, ולא צמתי גרף מאוחדים. לכן הצטלבות אחת עשויה לתרום כמה פיקסלי הסתעפות.'),
        _t('These are software-defined mask descriptors. Expert ground truth is required to assess segmentation accuracy. Class-specific diameter/length measurement, Random Forest training and inference are future work; assigning a manual type does not calculate those quantities.',
           'Это программно определённые признаки маски. Для проверки точности нужна экспертная разметка. Измерение длины/диаметра по классу, обучение и применение Random Forest — будущая работа; ручной тип не вычисляет эти величины.',
           'אלו מתארי מסכה המוגדרים בתוכנה. נדרש תיוג מומחה כדי להעריך דיוק פילוח. מדידות קוטר ואורך לפי מחלקה ואימון וחיזוי של Random Forest הם עבודה עתידית; שיוך סוג ידני אינו מחשב גדלים אלה.'),
    ), parameters=('pixel_size_um', 'min_sub_object_area', 'min_clean_threshold')),
    'export': dict(title=_t('CSV and training export', 'CSV и обучающий экспорт', 'ייצוא CSV ונתוני אימון'), paragraphs=(
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
        _t('Every image supports wheel or +/− zoom and dragging to pan. Fit to window restores automatic fitting after resize. The full-screen icon, image double-click or F11 opens a second view of the same image and polygons; Esc or F11 closes it. Changing the image closes the old full-screen view.',
           'Колесо и +/− меняют масштаб, перетаскивание панорамирует. «По размеру окна» возвращает автовписывание. Значок, двойной щелчок или F11 открывают второе окно той же сцены с полигонами; Esc/F11 закрывает. При смене изображения старое окно закрывается.',
           'גלגלת או +/− משנים זום וגרירה מזיזה את התמונה. התאמה לחלון מחזירה התאמה אוטומטית בשינוי גודל. הסמל, לחיצה כפולה בתמונה או F11 פותחים תצוגה נוספת של אותה תמונה ומצולעים; Esc או F11 סוגרים אותה. החלפת תמונה סוגרת את התצוגה הקודמת.'),
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

register_translations(_RU, hebrew=_HE)

_TOPIC_ALIASES = {
    'dataset': 'sources', 'open_tiles': 'tiles', 'source_selection': 'sources',
    'tile_search': 'tiles', 'tile_filter': 'tiles', 'tile_ids': 'tiles', 'labels_mode': 'segmentation',
    'manual_class': 'manual_types', 'manual_navigation': 'manual_types', 'manual_export': 'export',
    'result_search': 'results', 'result_class_filter': 'results', 'image_viewer': 'workspace',
    'image_zoom': 'workspace', 'image_fit': 'workspace', 'image_fullscreen': 'workspace', 'language': 'workspace',
    'filters': 'preparation', 'defaults': 'settings', 'parameters': 'parameters',
}
_MISSING = object()


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
        layout.addWidget(self.search)
        self.summary = QtWidgets.QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.navigation = QtWidgets.QListWidget()
        self.navigation.setMinimumWidth(210)
        self.navigation.setMaximumWidth(330)
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
        self.parameter_table.verticalHeader().setVisible(False)
        self.parameter_table.itemSelectionChanged.connect(self._parameter_selected)
        self.parameter_table.horizontalHeader().setStretchLastSection(True)
        self.details = QtWidgets.QTextBrowser()
        self.details.setOpenLinks(False)
        self.details.anchorClicked.connect(self._follow_link)
        parameter_page.addWidget(self.parameter_table)
        parameter_page.addWidget(self.details)
        parameter_page.setSizes([270, 370])
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
        self.summary.setText(self._text('Reference version {version}. Help is read-only; factory defaults are independent of the current project.', version=DEFAULTS_VERSION))
        self.close_button.setText(self._text('Close'))
        self._search_changed()

    def refresh_settings(self, values):
        self.current_settings = deepcopy(values) if values is not None else {}
        self._populate_parameters(self.search.text())
        if self._current_parameter:
            self._show_parameter(self._current_parameter)

    def _format_value(self, value):
        if value is _MISSING:
            return self._text('Not supplied')
        if value is None:
            return self._text('Not set')
        if isinstance(value, bool):
            return self._text('On' if value else 'Off')
        if isinstance(value, float):
            return format(value, '.12g')
        return str(value)

    def _parameter_matches(self, entry, query):
        return not query or query in ' '.join(str(value) for value in entry.values()).casefold()

    def _topic_matches(self, key, topic, query):
        text = ' '.join([key, self._text(topic['title']), *(self._text(p) for p in topic['paragraphs']), *topic['parameters']])
        return not query or query in text.casefold()

    def _search_changed(self, *_):
        query = self.search.text().strip().casefold()
        wanted = ('parameter', self._current_parameter) if query and self.pages.currentIndex() == 1 and self._current_parameter else ('topic', 'parameters' if self.pages.currentIndex() == 1 else self._current_topic)
        self.navigation.blockSignals(True)
        self.navigation.clear()
        for key, topic in TOPICS.items():
            if self._topic_matches(key, topic, query):
                item = QtWidgets.QListWidgetItem(self._text(topic['title']))
                item.setData(QtCore.Qt.ItemDataRole.UserRole, ('topic', key))
                self.navigation.addItem(item)
        if not query:
            item = QtWidgets.QListWidgetItem(self._text('Parameters and factory defaults'))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, ('topic', 'parameters'))
            self.navigation.insertItem(1, item)
        else:
            for entry in reference_rows(self.language):
                if self._parameter_matches(entry, query):
                    item = QtWidgets.QListWidgetItem(self._text('Parameter: {title}', title=entry['title']))
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, ('parameter', entry['key']))
                    self.navigation.addItem(item)
        selected = None
        for index in range(self.navigation.count()):
            item = self.navigation.item(index)
            if tuple(item.data(QtCore.Qt.ItemDataRole.UserRole)) == wanted:
                selected = item
                break
        self.navigation.setCurrentItem(selected or self.navigation.item(0))
        self.navigation.blockSignals(False)
        self._populate_parameters(query)
        if self.navigation.count():
            self._navigation_changed(self.navigation.currentItem())
        else:
            self.pages.setCurrentIndex(0)
            self.browser.setPlainText(self._text('No matching help. Try a shorter term or a technical key such as gamma.'))

    def _navigation_changed(self, item, previous=None):
        if item is None:
            return
        kind, key = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if kind == 'parameter':
            self.pages.setCurrentIndex(1)
            self._select_parameter(key)
        elif key == 'parameters':
            self._current_topic = key
            self.pages.setCurrentIndex(1)
            if self._current_parameter and self._select_parameter(self._current_parameter):
                return
            if self.parameter_table.rowCount():
                self.parameter_table.selectRow(0)
                self._show_parameter(self.parameter_table.item(0, 0).data(QtCore.Qt.ItemDataRole.UserRole))
        else:
            self._current_topic = key
            self.pages.setCurrentIndex(0)
            self.browser.setHtml(self._topic_html(key))

    def _populate_parameters(self, query=''):
        query = query.strip().casefold()
        entries = [entry for entry in reference_rows(self.language) if self._parameter_matches(entry, query)]
        self.parameter_table.blockSignals(True)
        self.parameter_table.setRowCount(len(entries))
        self.parameter_table.setHorizontalHeaderLabels([self._text('Parameter'), self._text('Factory default'), self._text('Current value'), self._text('Valid range')])
        for row, entry in enumerate(entries):
            values = [entry['title'] + '\n' + entry['key'], self._format_value(entry['factory_default']),
                      self._format_value(self.current_settings.get(entry['key'], _MISSING)), entry['valid_range']]
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, entry['key'])
                self.parameter_table.setItem(row, column, item)
        self.parameter_table.resizeColumnsToContents()
        self.parameter_table.resizeRowsToContents()
        self.parameter_table.blockSignals(False)

    def _select_parameter(self, key):
        for row in range(self.parameter_table.rowCount()):
            item = self.parameter_table.item(row, 0)
            if item.data(QtCore.Qt.ItemDataRole.UserRole) == key:
                self.parameter_table.selectRow(row)
                self.parameter_table.scrollToItem(item)
                self._show_parameter(key)
                return True
        return False

    def _parameter_selected(self):
        selected = self.parameter_table.selectedItems()
        if selected:
            self._show_parameter(selected[0].data(QtCore.Qt.ItemDataRole.UserRole))

    def _show_parameter(self, key):
        entry = parameter_entry(key, self.language)
        if entry is None:
            return
        self._current_parameter = key
        pairs = [('Factory default', self._format_value(entry['factory_default'])),
                 ('Current value', self._format_value(self.current_settings.get(key, _MISSING))),
                 ('Purpose', entry['purpose']), ('Units', entry['unit']), ('Valid range', entry['valid_range']),
                 ('Increase / enable', entry['increase']), ('Decrease / disable', entry['decrease']),
                 ('Example', entry['example']), ('Important', entry['safety'])]
        body = ''.join('<p><b>' + self._inline(self._text(label)) + '</b><br>' + self._inline(value) + '</p>' for label, value in pairs)
        self.details.setHtml(self._html('<h2>' + escape(entry['title']) + '</h2><p><code dir="ltr">' + escape(key) + '</code></p>' + body))

    def _inline(self, value):
        text = str(value)
        if self.language != 'he':
            return escape(text)
        # Unicode isolates keep formulae, filenames and Latin technical keys
        # readable without reversing the surrounding Hebrew explanation.
        pattern = r'[A-Za-z0-9][A-Za-z0-9_./×^()*=+:µ²><−–-]*(?:[ \t]+[A-Za-z0-9_./×^()*=+:µ²><−–-]+)*'
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
        body += ''.join('<p>' + self._inline(self._text(paragraph)) + '</p>' for paragraph in topic['paragraphs'])
        if topic['parameters']:
            links = []
            for parameter in topic['parameters']:
                entry = parameter_entry(parameter, self.language)
                if entry:
                    links.append('<a href="parameter:' + parameter + '">' + escape(entry['title']) + '</a>')
            body += '<h3>' + escape(self._text('Related parameters')) + '</h3><p>' + ' · '.join(links) + '</p>'
        return self._html(body)

    def open_parameter(self, key):
        if key not in PARAMETER_REFERENCE:
            return self.open_topic(_TOPIC_ALIASES.get(key, key))
        self._current_topic = 'parameters'
        self._current_parameter = key
        self.search.clear()
        self._populate_parameters()
        self.pages.setCurrentIndex(1)
        for index in range(self.navigation.count()):
            item = self.navigation.item(index)
            if tuple(item.data(QtCore.Qt.ItemDataRole.UserRole)) == ('topic', 'parameters'):
                self.navigation.setCurrentItem(item)
                break
        self._select_parameter(key)
        self.show()

    def open_topic(self, topic_id='getting_started'):
        topic_id = _TOPIC_ALIASES.get(topic_id, topic_id)
        if topic_id not in TOPICS and topic_id != 'parameters':
            topic_id = 'getting_started'
        self._current_topic = topic_id
        self._current_parameter = None
        self.search.clear()
        self._search_changed()
        for index in range(self.navigation.count()):
            item = self.navigation.item(index)
            if tuple(item.data(QtCore.Qt.ItemDataRole.UserRole)) == ('topic', topic_id):
                self.navigation.setCurrentItem(item)
                break
        self.show()

    def _follow_link(self, url):
        if url.scheme() == 'parameter':
            self.open_parameter(url.path())
        elif url.scheme() == 'topic':
            self.open_topic(url.path())


# The reference node is separate from narrative topics, but participates in the
# same translation catalogue and search/navigation model.
register_translations({'Parameters and factory defaults': 'Параметры и исходные значения'},
                      hebrew={'Parameters and factory defaults': 'פרמטרים וברירות מחדל מקוריות'})
