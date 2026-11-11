"""Ordered contextual guides for the Preparation and Tiles image tabs."""


TOPIC_TEXT = {
    'prep_source': (
        ('Source channel tab', 'Вкладка «Исходный канал»', 'לשונית ערוץ מקור'),
        ('Start here to check the selected TIFF, channel and slice/frame before filtering. The quick view samples a large image. Source resolution opens the whole image for navigation and loads the visible source pixels.',
         'Начните с этой вкладки и проверьте выбранный TIFF, канал и срез или кадр до фильтрации. Быстрый вид большого TIFF использует выборку пикселей. Просмотр исходного разрешения позволяет перемещаться по всему TIFF и загружает исходные пиксели видимой области.',
         'התחילו כאן כדי לבדוק את קובץ ה־TIFF, הערוץ והחתך או הפריים לפני הסינון. התצוגה המהירה דוגמת תמונה גדולה. תצוגת רזולוציית מקור מאפשרת לנווט בכל התמונה וטוענת את פיקסלי המקור באזור הנראה.')),
    'prep_filtering': (
        ('Filtering tab', 'Вкладка «Фильтрация»', 'לשונית סינון'),
        ('Preview selected TIFF calculates the enabled bilateral, white top-hat and gamma steps on the whole plane. Compare this grayscale image to Source channel to see retained signal and background. The displayed PNG is reduced for large images.',
         '«Предпросмотр выбранного TIFF» выполняет включённые bilateral, white top-hat и гамма-коррекцию на всей плоскости. Сравните полученное серое изображение с исходным каналом и проверьте сигнал и фон. Для больших изображений экранный PNG уменьшен.',
         'תצוגת TIFF נבחר מפעילה על המישור כולו את השלבים שהופעלו: bilateral, white top-hat וגאמה. השוו את התמונה בגוני אפור לערוץ המקור ובדקו אות ורקע. PNG לתצוגה מוקטן בתמונות גדולות.')),
    'prep_mask': (
        ('Protective mask tab', 'Вкладка «Защитная маска»', 'לשונית מסכת הגנה'),
        ('White pixels mark areas protected during tile boundary search. The mask uses thresholding and the enabled closing and dilation steps. Check whether a fiber stays connected. Object measurements use their own masks.',
         'Белые пиксели показывают области, защищённые при поиске границ тайлов. Маска строится по порогу с включёнными операциями замыкания и расширения. Проверьте, осталось ли волокно связным. Для измерения объектов используются отдельные маски.',
         'פיקסלים לבנים מסמנים אזורים מוגנים בחיפוש גבולות האריחים. המסכה משתמשת בסף ובשלבי הסגירה וההרחבה שהופעלו. בדקו אם הסיב נשאר קשיר. מדידות עצמים משתמשות במסכות נפרדות.')),
    'prep_resolution': (
        ('View at source resolution…', 'Просмотр в исходном разрешении…', 'תצוגה ברזולוציית המקור…'),
        ('Select a Preparation tab and use View at source resolution or 1:1. The main view starts at one source pixel per physical display pixel. Drag the image to pan or click the reduced navigation overview to jump. At low zoom the main view shows an explicitly labeled reduced image. Filtering and Protective mask may first need a worker run to save full-size TIFFs.',
         'Выберите вкладку «Подготовки» и нажмите «Просмотр в исходном разрешении» или 1:1. Основной вид открывается в масштабе один пиксель источника на физический пиксель экрана. Перетаскивайте изображение или щёлкните по уменьшенной карте навигации для быстрого перехода. При сильном отдалении в основном виде отображается уменьшенная копия с явной подписью. Для «Фильтрации» и «Защитной маски» при первом открытии может потребоваться расчёт полноразмерных TIFF.',
         'בחרו לשונית בהכנה ולחצו תצוגה ברזולוציית המקור או 1:1. התצוגה הראשית נפתחת ביחס של פיקסל מקור אחד לפיקסל מסך פיזי אחד. גררו את התמונה או לחצו על מפת הניווט המוקטנת למעבר מהיר. בזום נמוך מוצגת תמונה מוקטנת עם תווית ברורה. לסינון ולמסכת ההגנה ייתכן שיידרש חישוב TIFF בגודל מלא.'),
        ('At native zoom, Save displayed image and Compare with file use the visible region on its source grid. At low zoom they use the reduced whole-image preview.',
         'При просмотре исходных пикселей сохранение видимого изображения и сравнение с файлом используют видимый участок на исходной сетке. При сильном отдалении используется уменьшенная копия всего изображения.',
         'בתצוגת פיקסלי המקור שמירת התמונה המוצגת והשוואה לקובץ משתמשות באזור הנראה בסריג המקור. בזום נמוך נעשה שימוש בעותק המוקטן של התמונה המלאה.')),
    'tile_overview': (
        ('Overview tab', 'Вкладка «Обзорная карта»', 'לשונית מפת סקירה'),
        ('Find the tile on the whole source map. Tile IDs and boundaries give context. Click a region to select its tile. Detailed boundary map or 1:1 generates a separate map with source dimensions.',
         'Найдите тайл на карте всего исходника. Номера и границы дают контекст. Щёлкните по области, чтобы выбрать её тайл. «Подробная карта границ» или 1:1 создаёт отдельную карту в размерах исходника.',
         'מצאו את האריח במפת המקור המלאה. מזהים וגבולות מספקים הקשר. לחצו על אזור לבחירת האריח. מפת גבולות מפורטת או 1:1 יוצרת מפה נפרדת במידות המקור.')),
    'tile_model': (
        ('Model tab', 'Вкладка «Модель»', 'לשונית מודל'),
        ('Fixed-size canvas for the model and YOLO coordinates. The crop may be padded or reduced to fit. For example, a 3000-pixel crop can fit a 1500-pixel model canvas at two source pixels per model pixel.',
         'Холст фиксированного размера для модели и координат YOLO. Фрагмент может дополняться паддингом или уменьшаться. Например, фрагмент шириной 3000 px может поместиться в холст 1500 px с масштабом два исходных пикселя на модельный.',
         'משטח בגודל קבוע למודל ולקואורדינטות YOLO. החיתוך עשוי לכלול ריפוד או הקטנה. לדוגמה, חיתוך של 3000 פיקסלים יכול להיכנס למשטח של 1500, עם שני פיקסלי מקור לפיקסל מודל.')),
    'tile_native': (
        ('Native tab', 'Вкладка Native', 'לשונית אריח בקנה מידת המקור'),
        ('The prepared crop on the source grid, at one source pixel per image pixel. Use this view for fine inspection, editing and checking measurement locations. Tiles up to 32 MP load the saved pixel grid directly.',
         'Подготовленный фрагмент на исходной сетке, один пиксель изображения на один пиксель исходника. Используйте этот вид для проверки мелких деталей, редактирования и поиска измеренного объекта. Для тайлов до 32 Мп загружается полная сохранённая сетка.',
         'החיתוך המוכן בסריג המקור, פיקסל מקור אחד לכל פיקסל בתמונה. השתמשו בו לבדיקה מדויקת, לעריכה ולאיתור עצמים שנמדדו. אריחים עד 32 מגה־פיקסל נטענים בסריג השמור המלא.')),
    'tile_ownership': (
        ('Ownership tab', 'Вкладка «Принадлежность»', 'לשונית שיוך פיקסלים'),
        ('White means the native pixel belongs to this tile. Black marks padding or pixels outside its active ownership. Check this view when an object meets a tile edge.',
         'Белый цвет означает, что исходный пиксель принадлежит этому тайлу. Чёрным показаны паддинг или пиксели за пределами действительной области тайла. Проверяйте эту вкладку, если объект подходит к границе.',
         'לבן מציין שפיקסל המקור שייך לאריח. שחור מסמן ריפוד או פיקסלים מחוץ לתחום השיוך התקף. בדקו תצוגה זו כאשר עצם מגיע לגבול האריח.')),
    'tile_polygons': (
        ('Polygons tab', 'Вкладка «Полигоны»', 'לשונית מצולעים'),
        ('Shows imported YOLO outlines on the model canvas. Its status distinguishes available outlines, empty TXT, missing TXT and invalid TXT. Check measurements in Segmentation → Objects.',
         'Показывает импортированные полигоны YOLO на модельном холсте. Статус различает наличие контуров, пустой TXT, отсутствующий TXT и ошибку файла. Измеренные маски проверяйте в «Сегментации → Объекты».',
         'מציג מצולעי YOLO שיובאו על משטח המודל. המצב מבדיל בין מתארים זמינים, TXT ריק, TXT חסר ו־TXT שגוי. בדקו מסכות מדידה בפילוח → עצמים.')),
    'channel_composite': (
        ('Combine TIFF channels…', 'Объединить каналы TIFF…', 'שילוב ערוצי TIFF…'),
        ('In Preparation select a TIFF and open Combine TIFF channels. Choose one slice/frame and enable the channels to combine. Set each color, gain from 0 to 1600% and opacity from 0 to 100%. The blend sums the colored signals and clips at white in each RGB component. For example, red and green at full intensity produce yellow.',
         'В «Подготовке» выберите TIFF и откройте «Объединить каналы TIFF». Выберите один срез или кадр и отметьте нужные каналы. Для каждого задайте цвет, усиление от 0 до 1600% и непрозрачность от 0 до 100%. Цветные сигналы суммируются с ограничением каждого компонента RGB. Например, красный и зелёный при полной яркости дают жёлтый.',
         'בהכנה בחרו TIFF ופתחו שילוב ערוצי TIFF. בחרו חתך או פריים אחד וסמנו את הערוצים הדרושים. קבעו צבע, הגבר בין 0 ל־1600% ואטימות בין 0 ל־100% לכל ערוץ. האותות הצבועים מתחברים ונחתכים בכל רכיב RGB. לדוגמה, אדום וירוק בעוצמה מלאה נותנים צהוב.'),
        ('Use the dedicated Save full-resolution composite button for an RGB image at the original width and height. TIFF supports large exports and carries supported isotropic OME calibration. PNG and JPEG are available up to 32 MP. The blend is an 8-bit RGB visualization of the chosen plane.',
         'Кнопка «Сохранить наложение в исходном разрешении» записывает RGB в исходной ширине и высоте. TIFF поддерживает большой экспорт и записывает поддерживаемую одинаковую по X/Y калибровку OME. PNG и JPEG доступны до 32 Мп. Результат — 8-битная RGB-визуализация выбранной плоскости.',
         'כפתור השמירה ברזולוציית המקור יוצר RGB ברוחב ובגובה המקוריים. TIFF תומך בייצוא גדול וכולל כיול OME איזוטרופי נתמך. PNG ו־JPEG זמינים עד 32 מגה־פיקסל. התוצאה היא תצוגת RGB של 8 סיביות של המישור שנבחר.')),
    'interface_scale': (
        ('Interface scale', 'Масштаб интерфейса', 'קנה מידה של הממשק'),
        ('Open Settings → Appearance. Automatic grows fonts and controls as the main window gets larger, up to 180%. Fixed choices range from 100% to 200%. This setting applies in addition to Windows display scaling.',
         'Откройте «Настройки → Внешний вид». Автомасштаб увеличивает текст и элементы при увеличении главного окна, до 180%. Фиксированные значения — от 100% до 200%. Этот масштаб действует поверх системного масштаба Windows.',
         'פתחו הגדרות → מראה. במצב אוטומטי הגופנים והפקדים גדלים כשהחלון הראשי גדל, עד 180%. הערכים הקבועים הם בין 100% ל־200%. קנה המידה נוסף לקנה המידה של Windows.')),
}
