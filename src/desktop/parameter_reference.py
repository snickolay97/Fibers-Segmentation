"""Read-only, versioned reference for every supported pipeline setting.

Numbers come from the canonical factory catalogue, never a loaded project or
mutable config module. Descriptions refer to validation rules, not UI bounds.
"""

from dataclasses import dataclass
from types import MappingProxyType

from src.default_settings import FACTORY_DEFAULTS, DEFAULTS_VERSION
from .i18n import register_translations, tr


_RU, _HE = {}, {}


def _t(english, russian, hebrew):
    _RU[english], _HE[english] = russian, hebrew
    return english


@dataclass(frozen=True)
class ParameterReference:
    key: str
    title: str
    group: str
    unit: str
    valid_range: str
    purpose: str
    increase: str
    decrease: str
    example: str
    safety: str


SOURCES = _t('Sources and scale', 'Исходники и масштаб', 'מקורות וקנה מידה')
FILTERS = _t('Grayscale filters', 'Фильтры серого изображения', 'מסנני גוני אפור')
MASK = _t('Protective mask', 'Защитная маска', 'מסכת הגנה')
TILING = _t('Tiling and outputs', 'Нарезка и файлы', 'חלוקה לאריחים וקבצים')
MEASURE = _t('Object measurements', 'Измерения объектов', 'מדידות עצמים')
BOOL = _t('On/off', 'Вкл./выкл.', 'פעיל/כבוי')
INTEGER = _t('Positive integer', 'Положительное целое число', 'מספר שלם חיובי')
POSITIVE = _t('Finite number greater than 0', 'Конечное число больше 0', 'מספר סופי גדול מאפס')
ODD = _t('Positive odd integer: 1, 3, 5, …', 'Положительное нечётное целое: 1, 3, 5, …', 'מספר שלם חיובי אי־זוגי: 1, 3, 5, …')
PX = _t('Source pixels', 'Исходные пиксели', 'פיקסלים במקור')
LEVEL = _t('Intensity on a 0–255 processing image', 'Яркость обрабатываемого изображения 0–255', 'עוצמה בתמונת עיבוד בטווח 0–255')
FACTOR = _t('Dimensionless factor', 'Безразмерный коэффициент', 'מקדם חסר יחידות')
NEW_RUN = _t('Changes apply to a preview or a new run; existing outputs keep their saved settings.',
             'Изменения действуют для предпросмотра или нового запуска; готовые файлы сохраняют свои настройки.',
             'שינויים חלים בתצוגה מקדימה או בריצה חדשה; תוצרים קיימים שומרים על ההגדרות שנשמרו.')
MASK_WARNING = _t('The protective mask guides tiling. It is not a physical diameter or object measurement mask.',
                  'Защитная маска направляет нарезку. Это не маска физического диаметра или измеряемого объекта.',
                  'מסכת ההגנה מנחה את החלוקה לאריחים. היא אינה מסכה למדידת קוטר פיזי או עצמים.')
QUALITY_WARNING = _t('Appearance changes are not proof of improved biological segmentation accuracy.',
                     'Изменение вида изображения не доказывает улучшение точности биологической сегментации.',
                     'שינוי במראה התמונה אינו הוכחה לשיפור בדיוק הפילוח הביולוגי.')
MORE_FILES = _t('Save additional files; use more disk space.', 'Сохранить дополнительные файлы; потребуется больше места.', 'לשמור קבצים נוספים; נדרש יותר שטח אחסון.')
FEWER_FILES = _t('Skip these auxiliary files; native measurement outputs remain.', 'Не сохранять эти дополнительные файлы; native-данные измерений остаются.', 'לדלג על קבצי העזר האלה; תוצרי המדידה ברזולוציית המקור נשארים.')
ENABLE = _t('Enable this processing stage.', 'Включить эту стадию обработки.', 'להפעיל שלב עיבוד זה.')
BYPASS = _t('Bypass this stage while retaining its parameter values.', 'Пропустить стадию, сохранив значения её параметров.', 'לדלג על השלב תוך שמירת ערכי הפרמטרים שלו.')


_PARAMETERS = (
    ParameterReference('channel', _t('TIFF channel', 'Канал TIFF', 'ערוץ TIFF'), SOURCES,
        _t('Zero-based index', 'Индекс начиная с 0', 'אינדקס המתחיל ב־0'),
        _t('Integer ≥ 0 and less than the source channel count', 'Целое ≥ 0 и меньше числа каналов исходника', 'מספר שלם שאינו שלילי וקטן ממספר הערוצים במקור'),
        _t('Choose one channel using TIFF axes metadata; grayscale has channel 0.', 'Выбрать один канал по осям TIFF; у серого изображения канал 0.', 'לבחור ערוץ אחד לפי מטא־נתוני הצירים של TIFF; בתמונת אפור משתמשים בערוץ 0.'),
        _t('Select the next channel, not a stronger filter.', 'Выбрать следующий канал, а не усилить фильтр.', 'לבחור בערוץ הבא, לא להגביר סינון.'),
        _t('Select the previous channel.', 'Выбрать предыдущий канал.', 'לבחור בערוץ הקודם.'),
        _t('RGB: 0 red, 1 green, 2 blue.', 'RGB: 0 красный, 1 зелёный, 2 синий.', 'RGB: אדום 0, ירוק 1, כחול 2.'),
        _t('The selected channel must exist in every checked TIFF.', 'Выбранный канал должен быть во всех TIFF пакета.', 'הערוץ שנבחר חייב להתקיים בכל קובצי ה־TIFF המסומנים.')),
    ParameterReference('plane', _t('TIFF slice / frame', 'Срез / кадр TIFF', 'חתך / פריים ב־TIFF'), SOURCES,
        _t('Zero-based index', 'Индекс начиная с 0', 'אינדקס המתחיל ב־0'),
        _t('Integer ≥ 0 and less than the source plane count', 'Целое ≥ 0 и меньше числа плоскостей', 'מספר שלם שאינו שלילי וקטן ממספר המישורים במקור'),
        _t('Choose one depth Z, time T or image I plane, separately from the channel. A 2D TIFF has one plane (0, read-only); no projection is performed.', 'Выбрать один срез глубины Z, кадр времени T или изображение I, отдельно от канала. У 2D TIFF одна плоскость (0, только чтение); проекция не выполняется.', 'לבחור חתך עומק Z, פריים בזמן T או תמונה I, בנפרד מהערוץ. בתמונת TIFF דו־ממדית יש מישור אחד (0, לקריאה בלבד); לא מחושבת הטלה.'),
        _t('Select the next plane.', 'Выбрать следующую плоскость.', 'לבחור במישור הבא.'),
        _t('Select the previous plane.', 'Выбрать предыдущую плоскость.', 'לבחור במישור הקודם.'),
        _t('A 10-plane stack accepts 0–9.', 'Для стека из 10 плоскостей допустимы 0–9.', 'בערימה בעלת 10 מישורים מותר לבחור 0–9.'),
        _t('Ambiguous multiple stack axes require an explicitly exported source.', 'Для неоднозначных осей стека нужен явно экспортированный исходник.', 'כאשר צירי הערימה אינם חד־משמעיים, יש לייצא מקור בעל צירים מפורשים.')),
    ParameterReference('pixel_size_um', _t('Pixel calibration', 'Калибровка пикселя', 'כיול פיקסל'), SOURCES,
        _t('Micrometres per source pixel', 'Микрометры на исходный пиксель', 'מיקרומטר לפיקסל במקור'),
        _t('Not set, or a finite number greater than 0', 'Не задано либо конечное число больше 0', 'לא מוגדר, או מספר סופי גדול מאפס'),
        _t('Convert native pixel area to Area_um2 = Area × calibration². Uniform scaling does not change AR.', 'Перевести native-площадь: Area_um2 = Area × калибровка². Одинаковый масштаб осей не меняет AR.', 'להמיר שטח בפיקסלי המקור: Area_um2 = Area × כיול². שינוי קנה מידה אחיד אינו משנה את AR.'),
        _t('Increase physical lengths linearly and areas quadratically.', 'Физические длины растут линейно, площади — квадратично.', 'המידות הפיזיות גדלות ליניארית והשטחים גדלים בריבוע.'),
        _t('Decrease physical lengths and areas without changing the image.', 'Уменьшить физические длины и площади, не меняя изображение.', 'להקטין מידות ושטחים פיזיים בלי לשנות את התמונה.'),
        _t('100 px² at 0.5 µm/px becomes 25 µm².', '100 px² при 0.5 µm/px дают 25 µm².', '100 פיקסלים רבועים בכיול 0.5 מיקרומטר לפיקסל הם 25 מיקרומטר רבוע.'),
        _t('From TIFF metadata reads a supported isotropic OME/ImageJ scale per source. Manual mode applies one scale to the batch; 0 means not set. Print DPI and magnification are not used automatically. Old results keep their recorded calibration.', 'Из TIFF читается поддерживаемый одинаковый масштаб OME/ImageJ по обеим осям для каждого исходника. Ручной режим задаёт один масштаб пакету; 0 — не задано. DPI печати и увеличение не применяются автоматически. Прежние результаты сохраняют свою калибровку.', 'מטא־נתוני TIFF מספקים קנה מידה נתמך וזהה בצירים דרך OME/ImageJ לכל מקור. מצב ידני מחיל קנה מידה אחד על האצווה; 0 פירושו לא מוגדר. DPI הדפסה והגדלת עדשה אינם משמשים אוטומטית. תוצאות ישנות שומרות על הכיול שתועד.')),
    ParameterReference('target_size', _t('Model tile size', 'Размер модельного тайла', 'גודל אריח למודל'), TILING,
        _t('Model-canvas pixels per side', 'Пиксели стороны модельного поля', 'פיקסלים בכל צלע של אריח המודל'),
        _t('Integer ≥ 8', 'Целое ≥ 8', 'מספר שלם של 8 לפחות'),
        _t('Set the square model PNG and derive slicing search offsets from its side length.', 'Задать квадратный модельный PNG и отступы поиска нарезки от его стороны.', 'לקבוע את גודל תמונת ה־PNG הריבועית למודל ואת מרחקי חיפוש החיתוך הנגזרים ממנה.'),
        _t('Usually create larger model canvases and wider search offsets.', 'Обычно увеличить модельное поле и отступы поиска.', 'בדרך כלל להגדיל את משטח המודל ואת מרחקי החיפוש.'),
        _t('Use smaller canvases; oversized crops may be reduced more.', 'Уменьшить поле; крупные фрагменты могут сильнее уменьшаться.', 'להקטין את המשטח; ייתכן שפרגמנטים גדולים יוקטנו יותר.'),
        _t('At 1500, the initial search window is [1125, 1462) and the shift step is 22 px.', 'При 1500 первое окно поиска — [1125, 1462), шаг сдвига — 22 px.', 'בגודל 1500 חלון החיפוש הראשון הוא [1125, 1462) וצעד ההזזה הוא 22 פיקסלים.'),
        _t('v3 measurements use native pixels; changing this size creates new tile IDs and a new annotation version.', 'v3 измеряет native-пиксели; изменение размера создаёт новые ID тайлов и версию разметки.', 'מדידות v3 משתמשות בפיקסלי המקור; שינוי הגודל יוצר מזהי אריחים וגרסת תיוג חדשים.')),
    ParameterReference('search_window_end', _t('Initial search window end', 'Конец исходного окна поиска', 'קצה חלון החיפוש הראשון'), TILING, PX,
        _t('Automatic or an integer from floor(0.75N) + 1 to N, where N is the model tile side.', 'Автоматически или целое от floor(0,75N) + 1 до N, где N — сторона модельного тайла.', 'אוטומטי או מספר שלם בין floor(0.75N) + 1 ל־N, כאשר N הוא אורך צלע אריח המודל.'),
        _t('Set the exclusive right or bottom edge of the first window. Automatic uses floor(0.975N). The start is floor(0.75N).', 'Задаёт правую или нижнюю границу первого окна. Пиксель на границе не входит в окно. В режиме «Автоматически» это floor(0,975N). Начало окна — floor(0,75N).', 'מגדיר את הקצה הימני או התחתון של החלון הראשון ללא פיקסל הקצה. במצב אוטומטי הקצה הוא floor(0.975N). תחילת החלון היא floor(0.75N).'),
        _t('Widen the initial window and reduce the available right/down shift.', 'Расширяет первое окно и уменьшает доступный сдвиг вправо или вниз.', 'מרחיב את החלון הראשון ומצמצם את ההזזה הזמינה ימינה או למטה.'),
        _t('Narrow the initial window and allow more right/down travel.', 'Сужает первое окно и увеличивает допустимый сдвиг вправо или вниз.', 'מצמצם את החלון הראשון ומגדיל את ההזזה הזמינה ימינה או למטה.'),
        _t('At N=1500, 1400 gives [1125, 1400) and a right/down shift limit of 100 px. The left/up limit is 750 px.', 'При N=1500 значение 1400 задаёт окно [1125, 1400) и предел сдвига вправо или вниз 100 px. Предел влево или вверх — 750 px.', 'כאשר N=1500, ערך 1400 יוצר את החלון [1125, 1400) ומאפשר הזזה של עד 100 פיקסלים ימינה או למטה. הגבול שמאלה או למעלה הוא 750 פיקסלים.'),
        _t('A narrow window can leave too little room for a straight corridor. Dijkstra uses this initial window. The setting applies to new preparation runs.', 'Узкое окно может оставить слишком мало места для прямого коридора. Дейкстра использует это первое окно. Настройка применяется при новой подготовке.', 'חלון צר עלול להשאיר מעט מדי מקום למסדרון ישר. דייקסטרה משתמש בחלון הראשון הזה. ההגדרה חלה על ריצות הכנה חדשות.')),
    ParameterReference('straight_shift_left', _t('Straight window shift left / up', 'Сдвиг окна влево / вверх', 'הזזת חלון החיפוש שמאלה / למעלה'), TILING, PX,
        _t('Automatic or an integer from 0 to floor(0.75N) − max(1, floor(0.25N)), where N is the model tile side.', 'Автоматически или целое от 0 до floor(0.75N) − max(1, floor(0.25N)), где N — сторона модельного тайла.', 'אוטומטי או מספר שלם בין 0 ל־floor(0.75N) − max(1, floor(0.25N)), כאשר N הוא אורך צלע אריח המודל.'),
        _t('Limit how far the straight-corridor window moves left for a vertical cut or up for a horizontal cut.', 'Ограничивает сдвиг окна поиска прямого коридора влево для вертикального шва или вверх для горизонтального.', 'הגבלת הזזת חלון חיפוש המסדרון הישר שמאלה עבור חיתוך אנכי או למעלה עבור חיתוך אופקי.'),
        _t('Try additional windows toward the start of the current crop.', 'Добавляет пробные окна ближе к началу текущего фрагмента.', 'מאפשר לנסות חלונות נוספים לכיוון תחילת הפרגמנט הנוכחי.'),
        _t('Keep the search closer to the initial window. At 0 there are no leftward or upward trials.', 'Оставляет поиск ближе к первому окну. При 0 пробы влево и вверх отключены.', 'משאיר את החיפוש קרוב יותר לחלון הראשון. בערך 0 אין ניסיונות שמאלה או למעלה.'),
        _t('For N=1500, choose 45 px to test shifts of 22, 44 and 45 px on this side when earlier windows fail. The limit can be at most 750 px.', 'При N=1500 и пределе 45 px после неудачных проб проверяются сдвиги на 22, 44 и 45 px в эту сторону. Максимальный предел — 750 px.', 'עבור N=1500 ובחירה של 45 פיקסלים נבדקות הזזות של 22, 44 ו־45 פיקסלים בצד זה אם החלונות הקודמים נכשלו. הגבול המרבי הוא 750 פיקסלים.'),
        _t('Automatic tries full steps from the initial window up to the left/up limit. Dijkstra uses the initial window.', 'В режиме «Автоматически» окно сдвигается полными шагами до предела влево или вверх. Дейкстра работает в первом окне.', 'במצב אוטומטי החלון זז בצעדים שלמים עד לגבול שמאלה או למעלה. דייקסטרה פועל בחלון הראשון.')),
    ParameterReference('straight_shift_right', _t('Straight window shift right / down', 'Сдвиг окна вправо / вниз', 'הזזת חלון החיפוש ימינה / למטה'), TILING, PX,
        _t('Integer from 0 to N minus the initial window end, where N is the model tile side.', 'Целое от 0 до N минус конец исходного окна, где N — сторона модельного тайла.', 'מספר שלם מ־0 עד N פחות קצה החלון הראשון, כאשר N הוא אורך צלע אריח המודל.'),
        _t('Limit how far the straight-corridor window moves right for a vertical cut or down for a horizontal cut.', 'Ограничивает сдвиг окна поиска прямого коридора вправо для вертикального шва или вниз для горизонтального.', 'הגבלת הזזת חלון חיפוש המסדרון הישר ימינה עבור חיתוך אנכי או למטה עבור חיתוך אופקי.'),
        _t('Try additional windows toward the end of the current crop.', 'Добавляет пробные окна ближе к концу текущего фрагмента.', 'מאפשר לנסות חלונות נוספים לכיוון סוף הפרגמנט הנוכחי.'),
        _t('Reduce rightward or downward trials. At 0 they are disabled.', 'Сокращает число проб вправо и вниз. При 0 они отключены.', 'מצמצם ניסיונות ימינה או למטה. בערך 0 הם מבוטלים.'),
        _t('At N=1500, the maximum is 38 px with an automatic end or 100 px with an end of 1400. A limit of 30 px tries 22 and 30 px if needed.', 'При N=1500 максимум равен 38 px с автоматической границей и 100 px с границей 1400. Предел 30 px даёт пробы на 22 и 30 px при необходимости.', 'כאשר N=1500, הגבול המרבי הוא 38 פיקסלים עם קצה אוטומטי או 100 פיקסלים עם קצה 1400. בגבול של 30 פיקסלים נבדקים לפי הצורך היסטים של 22 ו־30 פיקסלים.'),
        _t('This affects straight-corridor trials. Dijkstra uses the initial window.', 'Параметр меняет пробы прямого коридора. Дейкстра работает в первом окне.', 'הערך משפיע על ניסיונות במסדרון ישר. דייקסטרה פועל בחלון הראשון.')),
    ParameterReference('overview_size', _t('Overview size', 'Размер обзора', 'גודל תמונת הסקירה'), TILING,
        _t('Display pixels on the longest side', 'Пиксели большей стороны обзора', 'פיקסלי תצוגה בצלע הארוכה'), INTEGER,
        _t('Choose the maximum side of the overview image.', 'Задать максимальную сторону обзорной карты.', 'לקבוע את אורך הצלע המרבי בתמונת הסקירה.'),
        _t('Show finer overview detail at higher memory and disk cost.', 'Показать больше деталей ценой памяти и места.', 'להציג פרטים רבים יותר במחיר של זיכרון ואחסון.'),
        _t('Produce a smaller, faster preview.', 'Получить меньший и более быстрый обзор.', 'להפיק תצוגה קטנה ומהירה יותר.'),
        _t('6000 → 3000 halves the longest display side.', '6000 → 3000 уменьшает большую сторону вдвое.', 'שינוי מ־6000 ל־3000 מקטין בחצי את הצלע הארוכה בתצוגה.'),
        _t('Display resolution does not change native measurements or exact ownership.', 'Разрешение обзора не меняет native-измерения и точную принадлежность.', 'רזולוציית התצוגה אינה משנה מדידות מקור או שיוך פיקסלים מדויק.')),
    ParameterReference('bilateral_d', _t('Bilateral diameter', 'Диаметр bilateral', 'קוטר המסנן הבילטרלי'), FILTERS, PX, INTEGER,
        _t('Set the neighborhood diameter for edge-aware smoothing.', 'Задать диаметр окрестности сглаживания с учётом границ.', 'לקבוע את קוטר סביבת ההחלקה המתחשבת בקצוות.'),
        _t('Consider a larger neighborhood and usually spend more processing time.', 'Учитывать большую окрестность и обычно увеличить время обработки.', 'להתחשב בסביבה רחבה יותר ובדרך כלל להאריך את זמן העיבוד.'),
        _t('Use a smaller smoothing neighborhood.', 'Использовать меньшую окрестность.', 'להשתמש בסביבת החלקה קטנה יותר.'),
        _t('Diameter 9 examines a wider neighborhood than 5.', 'Диаметр 9 рассматривает более широкую окрестность, чем 5.', 'קוטר 9 בוחן סביבה רחבה יותר מקוטר 5.'), QUALITY_WARNING),
    ParameterReference('bilateral_sigma_color', _t('Bilateral intensity sigma', 'Сигма яркости bilateral', 'סיגמת עוצמה בילטרלית'), FILTERS, LEVEL, POSITIVE,
        _t('Control how different neighboring intensities may be mixed.', 'Управлять смешиванием соседей с разной яркостью.', 'לקבוע כמה ניתן לערבב שכנים בעלי עוצמות שונות.'),
        _t('Mix more dissimilar intensities; weak edges may soften.', 'Смешивать сильнее различающиеся яркости; слабые границы могут сгладиться.', 'לערבב עוצמות שונות יותר; קצוות חלשים עלולים להתרכך.'),
        _t('Restrict mixing across intensity differences.', 'Ограничить смешивание через перепады яркости.', 'להגביל ערבוב בין עוצמות שונות.'),
        _t('45 → 60 tolerates larger intensity differences.', '45 → 60 допускает большие различия яркости.', 'מעבר מ־45 ל־60 מאפשר הבדלי עוצמה גדולים יותר.'), QUALITY_WARNING),
    ParameterReference('bilateral_sigma_space', _t('Bilateral spatial sigma', 'Пространственная сигма bilateral', 'סיגמה מרחבית בילטרלית'), FILTERS, PX, POSITIVE,
        _t('Control spatial weighting within the selected bilateral diameter.', 'Задать пространственные веса в пределах диаметра bilateral.', 'לקבוע את המשקולות המרחביות בתוך קוטר המסנן שנבחר.'),
        _t('Give more weight to distant neighbors within the diameter.', 'Усилить вклад дальних соседей в пределах диаметра.', 'להגדיל את משקלם של שכנים רחוקים בתוך הקוטר.'),
        _t('Concentrate smoothing near each pixel.', 'Сосредоточить сглаживание около пикселя.', 'לרכז את ההחלקה בקרבת כל פיקסל.'),
        _t('15 → 8 reduces the relative contribution of distant pixels.', '15 → 8 уменьшает относительный вклад дальних пикселей.', 'מעבר מ־15 ל־8 מקטין את התרומה היחסית של פיקסלים רחוקים.'), QUALITY_WARNING),
    ParameterReference('tophat_radius', _t('White top-hat radius', 'Радиус white top-hat', 'רדיוס white top-hat'), FILTERS, PX, INTEGER,
        _t('Remove broad background using an elliptical kernel, then min–max normalize.', 'Удалить широкий фон эллиптическим ядром, затем выполнить min–max нормализацию.', 'להסיר רקע רחב באמצעות גרעין אליפטי, ולאחר מכן לבצע נרמול מינימום–מקסימום.'),
        _t('Use a broader background scale; effects on thick objects depend on their size.', 'Использовать более широкий масштаб фона; эффект на толстых объектах зависит от размера.', 'להשתמש בקנה מידה רחב יותר לרקע; ההשפעה על עצמים עבים תלויה בגודלם.'),
        _t('Use a finer background scale; broad object signal may also be removed.', 'Использовать более мелкий масштаб; широкий сигнал объекта тоже может удаляться.', 'להשתמש בקנה מידה קטן יותר; גם אות רחב של עצם עלול להימחק.'),
        _t('Radius 85 gives a (2r+1)=171 pixel kernel.', 'Радиус 85 даёт ядро (2r+1)=171 пиксель.', 'רדיוס 85 נותן גרעין של (2r+1)=171 פיקסלים.'),
        _t('Min–max changes the value range; it does not make the distribution Gaussian.', 'Min–max меняет диапазон значений, а не делает распределение гауссовым.', 'נרמול מינימום–מקסימום משנה את טווח הערכים, לא הופך את ההתפלגות לגאוסית.')),
    ParameterReference('gamma', _t('Gamma', 'Гамма', 'גאמה'), FILTERS, FACTOR, POSITIVE,
        _t('Apply x^(1/gamma) through a uint8 lookup table.', 'Применить x^(1/gamma) через таблицу uint8.', 'להחיל x^(1/gamma) באמצעות טבלת המרה של uint8.'),
        _t('Above 1, brighten faint background as well as faint signal.', 'При значении выше 1 осветлить слабый фон и слабый сигнал.', 'מעל 1 מובהרים גם רקע חלש וגם אות חלש.'),
        _t('Below 1, darken intermediate intensities; 1 is the identity control.', 'Ниже 1 затемнить промежуточные яркости; 1 — контроль без изменения.', 'מתחת ל־1 מוחשכות עוצמות ביניים; הערך 1 הוא בקרת זהות ללא שינוי.'),
        _t('Gamma 1.2 uses exponent 0.8333; gamma 1 uses exponent 1.', 'Гамма 1.2 использует показатель 0.8333; гамма 1 — показатель 1.', 'גאמה 1.2 משתמשת בחזקה 0.8333; גאמה 1 משתמשת בחזקה 1.'), QUALITY_WARNING),
    ParameterReference('otsu_safety_factor', _t('Protective Otsu factor', 'Коэффициент защитного Otsu', 'מקדם Otsu להגנה'), MASK, FACTOR, POSITIVE,
        _t('Set protective threshold max(10, int(T × factor)); global Otsu T ignores intensity bin 0.', 'Задать защитный порог max(10, int(T × коэффициент)); глобальный Otsu T игнорирует яркость 0.', 'לקבוע סף הגנה max(10, int(T × מקדם)); סף Otsu הגלובלי T מתעלם מתא העוצמה 0.'),
        _t('Raise the threshold and usually protect fewer faint pixels.', 'Повысить порог и обычно защитить меньше слабых пикселей.', 'להעלות את הסף ובדרך כלל להגן על פחות פיקסלים חלשים.'),
        _t('Include more faint signal and background, possibly connecting large components.', 'Включить больше слабого сигнала и фона, возможно соединяя крупные компоненты.', 'לכלול יותר אות חלש ורקע, וייתכן לחבר רכיבים גדולים.'),
        _t('T=80 and factor=0.25 gives threshold 20.', 'T=80 и коэффициент 0.25 дают порог 20.', 'T=80 ומקדם 0.25 נותנים סף 20.'), MASK_WARNING),
    ParameterReference('bridge_kernel_size', _t('Protective closing kernel', 'Ядро защитного замыкания', 'גרעין סגירה להגנה'), MASK, PX, ODD,
        _t('Close gaps in the protective binary mask with an elliptical kernel.', 'Замкнуть разрывы защитной бинарной маски эллиптическим ядром.', 'לסגור פערים במסכה הבינרית המגינה באמצעות גרעין אליפטי.'),
        _t('Bridge wider gaps and potentially merge neighboring components.', 'Соединять более широкие разрывы и соседние компоненты.', 'לגשר על פערים רחבים יותר ואולי לחבר רכיבים סמוכים.'),
        _t('Bridge fewer gaps; 1 is a no-op kernel.', 'Соединять меньше разрывов; ядро 1 не меняет маску.', 'לגשר על פחות פערים; גרעין 1 אינו משנה את המסכה.'),
        _t('17 means a 17×17 ellipse; 16 is invalid.', '17 — эллипс 17×17; 16 недопустимо.', '17 מציין אליפסה בגודל 17×17; הערך 16 אינו תקין.'), MASK_WARNING),
    ParameterReference('buffer_kernel_size', _t('Protective dilation kernel', 'Ядро защитного расширения', 'גרעין הרחבה להגנה'), MASK, PX, ODD,
        _t('Dilate the protective mask to add a safety buffer around its pixels.', 'Расширить защитную маску буфером вокруг её пикселей.', 'להרחיב את מסכת ההגנה ולהוסיף מרווח סביב הפיקסלים שלה.'),
        _t('Create a wider buffer and potentially merge nearby components.', 'Создать более широкий буфер и объединить близкие компоненты.', 'ליצור מרווח רחב יותר ואולי למזג רכיבים קרובים.'),
        _t('Create a narrower buffer; 1 leaves the mask unchanged.', 'Создать более узкий буфер; 1 оставляет маску неизменной.', 'ליצור מרווח צר יותר; הערך 1 משאיר את המסכה ללא שינוי.'),
        _t('5 means a 5×5 ellipse; 4 is invalid.', '5 — эллипс 5×5; 4 недопустимо.', '5 מציין אליפסה בגודל 5×5; הערך 4 אינו תקין.'), MASK_WARNING),
    ParameterReference('min_corridor_width', _t('Minimum corridor width', 'Минимальная ширина коридора', 'רוחב מסדרון מזערי'), TILING, PX, INTEGER,
        _t('Prefer a straight obstacle-free corridor of this width; a narrower fallback is also tried.', 'Предпочитать свободный прямой коридор этой ширины; проверяется и более узкий вариант.', 'להעדיף מסדרון ישר ללא מכשולים ברוחב זה; נבדקת גם חלופה צרה יותר.'),
        _t('Prefer broader free corridors.', 'Предпочитать более широкие свободные коридоры.', 'להעדיף מסדרונות פנויים רחבים יותר.'),
        _t('Allow narrower preferred corridors.', 'Допускать более узкие предпочтительные коридоры.', 'לאפשר מסדרונות מועדפים צרים יותר.'),
        _t('15 has fallback max(3, 15//2)=7.', 'Для 15 запасной вариант max(3, 15//2)=7.', 'לערך 15 חלופת הגיבוי היא max(3, 15//2)=7.'),
        _t('This is not a minimum fiber diameter. Final ownership, not the seam alone, preserves protective components.', 'Это не минимальный диаметр волокна. Компоненты сохраняет итоговая принадлежность, а не только шов.', 'זה אינו קוטר סיב מזערי. שיוך הפיקסלים הסופי, ולא מסלול החיתוך לבדו, שומר על רכיבי ההגנה.')),
    ParameterReference('seam_repulsion_power', _t('Route distance power', 'Степень расстояния маршрута', 'חזקת המרחק במסלול'), TILING, FACTOR, POSITIVE,
        _t('Weight free route vertices by 1/(distance^power + 0.001); obstacles have infinite cost.', 'Задать вес свободных вершин 1/(расстояние^степень + 0.001); препятствия имеют бесконечную цену.', 'לתת לצומתי מסלול פנויים משקל 1/(מרחק^חזקה + 0.001); למכשולים עלות אינסופית.'),
        _t('Strengthen the preference for vertices farther from obstacles.', 'Усилить предпочтение вершин вдали от препятствий.', 'לחזק העדפה לצמתים הרחוקים ממכשולים.'),
        _t('Reduce the contrast between near and distant free vertices.', 'Снизить различие весов близких и дальних свободных вершин.', 'להקטין את ההבדל בין צמתים פנויים קרובים ורחוקים.'),
        _t('Changing 1.5 to 2 changes route preference, not the obstacle mask.', 'Изменение 1.5 на 2 меняет предпочтение маршрута, а не защитную маску.', 'מעבר מ־1.5 ל־2 משנה את העדפת המסלול, לא את מסכת ההגנה.'),
        _t('Diagonal corner crossing is possible; whole-component allocation later repairs ownership, not the seam.', 'Возможен диагональный проход между углами; затем распределение целых компонент исправляет принадлежность, а не шов.', 'ייתכן מעבר אלכסוני בין פינות; בהמשך שיוך רכיבים שלמים מתקן את הבעלות על הפיקסלים, לא את המסלול.')),
    ParameterReference('oversized_policy', _t('Oversized crop policy', 'Правило для крупного фрагмента', 'מדיניות לפרגמנט גדול מדי'), TILING,
        _t('Policy name', 'Название правила', 'שם מדיניות'),
        _t('preserve or error', 'preserve или error', 'preserve או error'),
        _t('Choose whether an oversized native crop is retained or rejected before export.', 'Выбрать сохранение крупного native-фрагмента или отказ перед экспортом.', 'לבחור אם לשמור פרגמנט מקור גדול מדי או לדחות אותו לפני הייצוא.'),
        _t('preserve keeps the native crop and reduces its model canvas.', 'preserve сохраняет native-фрагмент и уменьшает модельное поле.', 'preserve שומר את פרגמנט המקור ומקטין את תמונת המודל.'),
        _t('error stops that export rather than cutting the protected component.', 'error останавливает экспорт вместо разрезания защищённой компоненты.', 'error עוצר את הייצוא במקום לחתוך רכיב מוגן.'),
        _t('A 3000-pixel native side can map to a 1500-pixel model side at factor 2.', 'Сторона native 3000 может перейти в модельную 1500 с коэффициентом 2.', 'צלע מקור של 3000 פיקסלים יכולה להפוך לצלע מודל של 1500 במקדם 2.'),
        _t('Reduced model images lose detail. Native images and transformation metadata remain essential.', 'Уменьшение теряет детали. Native-изображения и преобразования остаются необходимыми.', 'תמונות מודל מוקטנות מאבדות פרטים. תמונות המקור ומטא־נתוני ההמרה נשארים חיוניים.')),
    ParameterReference('min_clean_threshold', _t('Minimum cleanup threshold', 'Минимальный порог очистки', 'סף ניקוי מזערי'), MEASURE, LEVEL,
        _t('Integer from 0 to 255', 'Целое от 0 до 255', 'מספר שלם בין 0 ל־255'),
        _t('Set the minimum local object threshold. If local Otsu > 10, use max(minimum, int(local Otsu × factor)); otherwise use the minimum.', 'Задать минимум локального порога. При Otsu > 10: max(минимум, int(Otsu × коэффициент)); иначе минимум.', 'לקבוע סף מקומי מזערי לעצם. אם Otsu המקומי גדול מ־10 משתמשים ב־max(מינימום, int(Otsu × מקדם)); אחרת משתמשים במינימום.'),
        _t('Remove more dim object pixels; shape and skeleton can change.', 'Удалить больше слабых пикселей; форма и скелет могут измениться.', 'להסיר יותר פיקסלים חלשים; הצורה והשלד עלולים להשתנות.'),
        _t('Retain more dim pixels, including possible background.', 'Сохранить больше слабых пикселей, включая возможный фон.', 'להשאיר יותר פיקסלים חלשים, כולל רקע אפשרי.'),
        _t('Local Otsu 40 with factor 0.7 and minimum 25 gives threshold 28.', 'Локальный Otsu 40, коэффициент 0.7 и минимум 25 дают порог 28.', 'Otsu מקומי 40, מקדם 0.7 ומינימום 25 נותנים סף 28.'), QUALITY_WARNING),
    ParameterReference('tier2_threshold_factor', _t('Local Otsu factor', 'Локальный коэффициент Otsu', 'מקדם Otsu מקומי'), MEASURE, FACTOR, POSITIVE,
        _t('Multiply local Otsu inside each contour before applying the minimum cleanup threshold.', 'Умножить локальный Otsu внутри контура перед ограничением минимальным порогом.', 'להכפיל את Otsu המקומי בתוך כל קו מתאר לפני החלת סף הניקוי המזערי.'),
        _t('Usually retain fewer weak pixels.', 'Обычно сохранить меньше слабых пикселей.', 'בדרך כלל להשאיר פחות פיקסלים חלשים.'),
        _t('Retain more weak pixels until the minimum threshold dominates.', 'Сохранить больше слабых пикселей до ограничения минимальным порогом.', 'להשאיר יותר פיקסלים חלשים עד שסף המינימום קובע.'),
        _t('0.7 × local Otsu 100 gives 70 before the minimum is applied.', '0.7 × локальный Otsu 100 дают 70 до применения минимума.', '0.7 כפול Otsu מקומי 100 נותנים 70 לפני החלת המינימום.'), QUALITY_WARNING),
    ParameterReference('min_sub_object_area', _t('Minimum component area', 'Минимальная площадь компоненты', 'שטח רכיב מזערי'), MEASURE,
        _t('Native source pixels squared', 'Квадрат исходного native-пикселя', 'פיקסלי מקור בריבוע'), INTEGER,
        _t('Discard cleaned 8-connected components smaller than this before saving measured objects.', 'Отбрасывать очищенные 8-связные компоненты меньше порога до сохранения измерений.', 'להסיר רכיבים נקיים בקישוריות 8 ששטחם קטן מהסף לפני שמירת העצמים הנמדדים.'),
        _t('Keep fewer small objects.', 'Сохранить меньше малых объектов.', 'להשאיר פחות עצמים קטנים.'),
        _t('Keep more small objects and potential noise.', 'Сохранить больше малых объектов и возможного шума.', 'להשאיר יותר עצמים קטנים ורעש אפשרי.'),
        _t('At 30, area 29 is discarded and area 30 is retained.', 'При 30 площадь 29 отбрасывается, а 30 сохраняется.', 'בסף 30 רכיב בשטח 29 מוסר ורכיב בשטח 30 נשמר.'),
        _t('v3 uses native area, not the reduced model-canvas area.', 'v3 использует native-площадь, а не площадь уменьшенного модельного поля.', 'v3 משתמש בשטח ברזולוציית המקור, לא בשטח תמונת המודל המוקטנת.')),
)


def _boolean(key, title, group, purpose, example, safety=NEW_RUN, output=False):
    return ParameterReference(key, title, group, BOOL, _t('True or False', 'True или False', 'True או False'),
        purpose, MORE_FILES if output else ENABLE, FEWER_FILES if output else BYPASS, example, safety)


_PARAMETERS += (
    _boolean('save_raw_tiles', _t('Save raw tiles', 'Сохранять raw-тайлы', 'שמירת אריחי מקור'), TILING,
        _t('Also export the unfiltered selected channel with the same ownership; raw native uint16 retains its depth.', 'Дополнительно сохранить нефильтрованный канал с той же принадлежностью; raw native uint16 сохраняет разрядность.', 'לייצא גם את הערוץ הלא־מסונן באותו שיוך פיקסלים; מקור uint16 נשמר בעומק המקורי.'),
        _t('Enable to compare filtered and unfiltered crops.', 'Включить для сравнения фильтрованных и исходных фрагментов.', 'להפעיל כדי להשוות פרגמנטים מסוננים ולא־מסוננים.'), output=True),
    _boolean('enable_animations', _t('Save search animations', 'Сохранять анимации поиска', 'שמירת הנפשות חיפוש'), TILING,
        _t('Save attempted search windows and accepted route GIFs for diagnosis.', 'Сохранить GIF пробных окон поиска и принятых маршрутов для диагностики.', 'לשמור הנפשות GIF של חלונות החיפוש שנוסו והמסלול שהתקבל לצורך אבחון.'),
        _t('Match the number in the GIF file and frame header to the tile ID on the overview. For example, search_0033_right and search_0033_bottom both belong to tile #0033. A direction that ends directly at an image edge without a search has no GIF. Earlier exports used a separate search counter.', 'Сопоставьте номер в имени GIF и заголовке кадра с ID тайла на карте. Например, search_0033_right и search_0033_bottom относятся к тайлу #0033. Если граница совпала с краем снимка и поиск не выполнялся, GIF для этого направления не создаётся. В ранних выгрузках использовался отдельный счётчик поисков.', 'השוו את המספר בשם ה־GIF ובכותרת המסגרת למזהה האריח במפה. לדוגמה, search_0033_right ו־search_0033_bottom שייכים לאריח #0033. אם הגבול נקבע ישירות בקצה התמונה ללא חיפוש, לא נוצרת הנפשה לכיוון הזה. בייצוא ישן נעשה שימוש במונה חיפושים נפרד.'),
        _t('Animations do not show the priority-queue frontier or prove biological accuracy.', 'Анимации не показывают фронт очереди поиска и не доказывают биологическую точность.', 'ההנפשות אינן מציגות את חזית תור העדיפויות ואינן מוכיחות דיוק ביולוגי.'), output=True),
    _boolean('save_coverage_masks', _t('Save model coverage masks', 'Сохранять модельные маски покрытия', 'שמירת מסכות כיסוי למודל'), TILING,
        _t('Save fractional pixel coverage on the resized model canvas.', 'Сохранить долевое покрытие пикселей уменьшенного модельного поля.', 'לשמור כיסוי חלקי של פיקסלים בתמונת המודל המוקטנת.'),
        _t('Gray values can describe partial coverage after area resizing.', 'Серые значения могут означать частичное покрытие после уменьшения.', 'ערכי אפור עשויים לתאר כיסוי חלקי לאחר הקטנה.'),
        _t('Coverage is neither object segmentation nor the exact native ownership mask.', 'Покрытие — не сегментация объектов и не точная native-принадлежность.', 'כיסוי אינו פילוח עצמים ואינו מסכת שיוך המקור המדויקת.'), output=True),
    ParameterReference('animation_max_trial_frames', _t('Maximum search trial frames', 'Максимум кадров пробного поиска', 'מספר מרבי של מסגרות ניסוי בחיפוש'), TILING,
        _t('Frames per search diagnostic', 'Кадры диагностики поиска', 'מסגרות לאבחון חיפוש'), INTEGER,
        _t('Limit sampled trial-window frames when search animations are enabled.', 'Ограничить выборку кадров пробных окон при включённых анимациях.', 'להגביל את מספר מסגרות חלונות הניסוי כאשר הנפשות החיפוש מופעלות.'),
        _t('Show more attempted windows and use more export time and disk.', 'Показать больше пробных окон ценой времени экспорта и места.', 'להציג יותר חלונות ניסוי במחיר של זמן ייצוא ושטח אחסון.'),
        _t('Sample fewer trials without changing the chosen route.', 'Выбрать меньше кадров без изменения выбранного маршрута.', 'לדגום פחות ניסויים בלי לשנות את המסלול הנבחר.'),
        _t('24 caps the sampled trial frames; accepted-route reveal may add frames.', '24 ограничивает кадры проб; показ принятого маршрута может добавить кадры.', '24 מגביל את דגימת מסגרות הניסוי; חשיפת המסלול שהתקבל עשויה להוסיף מסגרות.'), NEW_RUN),
    _boolean('enable_bilateral', _t('Bilateral denoising', 'Bilateral-сглаживание', 'החלקה בילטרלית'), FILTERS,
        _t('Enable edge-aware denoising before the other grayscale stages.', 'Включить сглаживание с учётом границ перед другими фильтрами.', 'להפעיל הפחתת רעש המתחשבת בקצוות לפני יתר מסנני האפור.'),
        _t('Turn off to compare the same crop without bilateral smoothing.', 'Выключить для сравнения того же фрагмента без bilateral.', 'לכבות כדי להשוות את אותו פרגמנט ללא החלקה בילטרלית.'), QUALITY_WARNING),
    _boolean('enable_tophat', _t('White top-hat', 'White top-hat', 'Top-hat לבן'), FILTERS,
        _t('Enable background subtraction and its associated min–max normalization.', 'Включить вычитание фона и связанную min–max нормализацию.', 'להפעיל הסרת רקע ואת נרמול המינימום–מקסימום הנלווה.'),
        _t('Turning off skips both top-hat and its normalization.', 'Выключение пропускает и top-hat, и его нормализацию.', 'כיבוי מדלג גם על top-hat וגם על הנרמול שלו.'), QUALITY_WARNING),
    _boolean('enable_gamma', _t('Gamma correction', 'Гамма-коррекция', 'תיקון גאמה'), FILTERS,
        _t('Enable the reciprocal-gamma LUT; disabling it bypasses only that stage.', 'Включить LUT с показателем 1/gamma; выключение пропускает только эту стадию.', 'להפעיל טבלת המרה בחזקה 1/gamma; כיבוי מדלג רק על שלב זה.'),
        _t('Enabled gamma=1 is identity; enabled gamma=1.2 brightens signal and background.', 'Включённая gamma=1 ничего не меняет; gamma=1.2 осветляет сигнал и фон.', 'גאמה פעילה בערך 1 היא זהות; בערך 1.2 מובהרים גם האות וגם הרקע.'), QUALITY_WARNING),
    _boolean('enable_closing', _t('Morphological closing', 'Морфологическое замыкание', 'סגירה מורפולוגית'), MASK,
        _t('Enable elliptical closing after protective thresholding.', 'Включить эллиптическое замыкание после защитного порога.', 'להפעיל סגירה אליפטית לאחר סף ההגנה.'),
        _t('Disable to leave thresholded gaps unbridged.', 'Выключить, чтобы не соединять разрывы пороговой маски.', 'לכבות כדי להשאיר פערים במסכת הסף ללא גישור.'), MASK_WARNING),
    _boolean('enable_dilation', _t('Protective dilation', 'Защитное расширение', 'הרחבה להגנה'), MASK,
        _t('Enable a safety buffer on the protective mask.', 'Включить защитный буфер маски.', 'להפעיל מרווח בטיחות במסכת ההגנה.'),
        _t('Disable to omit the buffer while keeping protective thresholding.', 'Выключить буфер, сохранив защитное пороговое выделение.', 'לכבות את המרווח תוך שמירת סף ההגנה.'), MASK_WARNING),
)

PARAMETER_REFERENCE = MappingProxyType({entry.key: entry for entry in _PARAMETERS})
REFERENCE = PARAMETER_REFERENCE
register_translations(_RU, hebrew=_HE)


def parameter_entry(key, language=None):
    """Return a new localized description and the fixed canonical default."""
    entry = PARAMETER_REFERENCE.get(key)
    if entry is None:
        return None
    result = {name: tr(getattr(entry, name), language=language)
              for name in ('title', 'group', 'unit', 'valid_range', 'purpose', 'increase', 'decrease', 'example', 'safety')}
    result.update(key=key, factory_default=FACTORY_DEFAULTS[key], default=FACTORY_DEFAULTS[key], defaults_version=DEFAULTS_VERSION)
    return result


def reference_rows(language=None):
    """Display entries in the order of the shared factory catalog."""
    return [parameter_entry(key, language) for key in FACTORY_DEFAULTS]
