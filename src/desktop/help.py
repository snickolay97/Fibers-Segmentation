"""Scientific parameter explanations and compact hover-help controls."""

from .i18n import get_language
from .hebrew import HELP_HEBREW
from .qt import QtCore, QtWidgets


_HELP = {
    "enable_bilateral": (
        "Enable or bypass bilateral denoising. When enabled, diameter and intensity/spatial sigmas control smoothing before the next stage. Disabling does not alter saved raw pixels.",
        "Включить или пропустить bilateral-сглаживание. Диаметр и сигмы интенсивности/пространства управляют сглаживанием перед следующей стадией. Отключение не меняет сохраняемые raw-пиксели."),
    "enable_tophat": (
        "Enable or bypass white top-hat background subtraction. The enabled stage includes min–max normalization. Disabling also skips this normalization and sends the previous stage's image onward. Its effect on segmentation needs validation.",
        "Включить или пропустить вычитание фона white top-hat. Включённая стадия также выполняет min–max нормализацию. При отключении нормализация тоже пропускается и дальше передаётся изображение предыдущей стадии. Влияние на сегментацию требует проверки."),
    "enable_gamma": (
        "Enable or bypass the reciprocal-gamma LUT. When enabled, the transform is x^(1/gamma): gamma > 1 brightens faint background as well as faint signal. A brighter preview does not establish better detection accuracy.",
        "Включить или пропустить гамма-преобразование LUT с показателем 1/gamma. При gamma > 1 осветляется и слабый фон, и слабый сигнал. Более яркий предпросмотр не доказывает улучшение точности выделения объектов."),
    "enable_closing": (
        "Enable or bypass morphological closing of the binary protective mask. Closing can bridge gaps and merge nearby protected components. It changes the routing mask, not the grayscale measurement image or a physical diameter mask.",
        "Включить или пропустить морфологическое замыкание бинарной защитной маски. Может соединять разрывы и соседние компоненты. Меняет маску для нарезки, а не серое изображение измерений или маску физического диаметра."),
    "enable_dilation": (
        "Enable or bypass dilation of the protective mask. Dilation adds a buffer around protected pixels and may join nearby components. Disabling removes this buffer; it does not change the thresholded object measurement mask.",
        "Включить или пропустить расширение защитной маски. Добавляет буфер вокруг защищённых пикселей и может соединять компоненты. Отключение убирает этот буфер и не меняет пороговую маску измеряемого объекта."),
    "language": (
        "Interface language. English is the default; your choice is remembered for the next launch. It changes labels and help text without changing scientific settings, saved measurements or class keys.",
        "Язык интерфейса. По умолчанию английский; выбор сохраняется для следующего запуска. Меняет подписи и пояснения, не меняя научные параметры, сохранённые измерения или ключи классов."),
    "target_size": (
        "Width and height of the square model PNG, in pixels. Large protected objects stay whole and may be reduced to fit; native crops and scale metadata remain available for measurement.",
        "Ширина и высота квадратного модельного PNG в пикселях. Крупные защищённые объекты сохраняются целиком и могут уменьшаться; native-фрагменты и масштаб остаются для измерений."),
    "overview_size": (
        "Maximum side of the overview image. It affects display resolution, not tile ownership or measurement scale. Larger overviews require more disk space and preview memory.",
        "Максимальная сторона обзорной карты. Влияет на её разрешение, а не на принадлежность пикселей или масштаб измерений. Большая карта требует больше места и памяти."),
    "channel": (
        "Zero-based channel index from TIFF metadata. For RGB: 0=red, 1=green, 2=blue. A grayscale TIFF has channel 0. The index must exist in every selected source.",
        "Индекс канала по метаданным TIFF, начиная с 0. Для RGB: 0=красный, 1=зелёный, 2=синий. У серого TIFF канал 0. Канал должен существовать во всех выбранных исходниках."),
    "plane": (
        "Zero-based plane index along the TIFF Z, I or T axis. A 2D image uses 0. This selects one plane; planes are not projected or combined. Ambiguous multi-axis stacks are rejected.",
        "Индекс плоскости оси Z, I или T TIFF, начиная с 0. Для 2D изображения — 0. Выбирается одна плоскость, без проекции и объединения. Неоднозначные многомерные стеки не принимаются."),
    "pixel_size_um": (
        "Micrometers per original source pixel. Not set means pixel units. Physical area = native pixel area × calibration². AR is dimensionless and does not change under uniform scaling. Calibration must describe the original TIFF.",
        "Микрометры на исходный пиксель. Без калибровки остаются пиксельные единицы. Физическая площадь = native-площадь × калибровка². AR безразмерен и не меняется при одинаковом масштабе осей. Калибровка относится к исходному TIFF."),
    "save_raw_tiles": (
        "Also save the selected unfiltered channel using the same pixel ownership. Native raw data keeps uint8/uint16 depth. Filtering uses uint8; uint16 processing uses the high byte (value >> 8). Increases disk use.",
        "Дополнительно сохранить выбранный нефильтрованный канал с той же принадлежностью пикселей. Native raw сохраняет uint8/uint16. Фильтрация использует uint8; для uint16 берётся старший байт (value >> 8). Требует дополнительного места."),
    "enable_animations": (
        "Save GIFs of search-window trials and accepted routes for diagnosing slicing. This is optional and increases execution time and disk use; it does not change the partition.",
        "Сохранить GIF пробных поисковых окон и принятых маршрутов для анализа нарезки. Увеличивает время и объём файлов; на распределение пикселей не влияет."),
    "save_coverage_masks": (
        "Save reduced model-canvas coverage maps. Gray levels describe fractional coverage after resizing. These are neither object segmentation masks nor exact native ownership masks.",
        "Сохранить уменьшенные карты покрытия модельного поля. Яркость показывает долю покрытия после уменьшения. Это не сегментация объектов и не точные native-маски принадлежности."),
    "bilateral_d": (
        "Diameter of the bilateral filter neighborhood in source pixels. Larger neighborhoods smooth more but cost more time. The filter also uses intensity and spatial sigmas.",
        "Диаметр окрестности bilateral-фильтра в исходных пикселях. Большая окрестность сильнее сглаживает и медленнее работает. Также учитываются сигмы интенсивности и пространства."),
    "bilateral_sigma_color": (
        "Intensity similarity range for bilateral smoothing on the uint8 processing image. Larger values mix more different intensities and may soften weak boundaries.",
        "Диапазон сходства яркости для bilateral-сглаживания uint8 изображения. Большое значение смешивает сильнее различающиеся интенсивности и может смягчать слабые границы."),
    "bilateral_sigma_space": (
        "Spatial sigma of bilateral smoothing in source pixels. Larger values admit more distant neighbors within the selected diameter.",
        "Пространственная сигма bilateral-сглаживания в исходных пикселях. Большое значение сильнее учитывает удалённых соседей в пределах выбранного диаметра."),
    "tophat_radius": (
        "Radius r of the elliptical white top-hat kernel; its size is (2r+1) × (2r+1) source pixels. It removes broad background structures. Changes can affect bright thick objects as well as background.",
        "Радиус r эллиптического ядра white top-hat; размер (2r+1) × (2r+1) исходных пикселей. Удаляет широкие фоновые структуры. Может влиять и на яркие толстые объекты."),
    "gamma": (
        "Brightness transformation x^(1/gamma) on the current uint8 image. gamma > 1 brightens faint background as well as faint signal; gamma < 1 darkens them and gamma = 1 is the identity control. Min–max normalization occurs only when white top-hat is enabled. Changes can affect masks and measurements; brightness alone does not establish accuracy.",
        "Преобразование яркости x^(1/gamma) текущего uint8 изображения. gamma > 1 осветляет и слабый фон, и слабый сигнал; gamma < 1 затемняет их, gamma = 1 не меняет яркость. Min–max нормализация выполняется только при включённом white top-hat. Изменения влияют на маски и измерения; яркость сама по себе не доказывает точность."),
    "otsu_safety_factor": (
        "Factor multiplying the Otsu threshold when building the protective mask: threshold = max(10, int(Otsu × factor)). Lower values include fainter structures but may connect background into large components.",
        "Множитель порога Otsu для защитной маски: порог = max(10, int(Otsu × factor)). Меньшее значение включает слабые структуры, но может объединять фон в крупные компоненты."),
    "bridge_kernel_size": (
        "Positive odd size of the elliptical closing kernel in source pixels. It bridges gaps in the protective mask before slicing; nearby objects may become one protected component. It does not separate touching fibers.",
        "Положительный нечётный размер эллиптического ядра замыкания в исходных пикселях. Соединяет разрывы защитной маски перед нарезкой; соседние объекты могут стать одной компонентой. Не разделяет соприкасающиеся волокна."),
    "buffer_kernel_size": (
        "Positive odd size of the elliptical dilation kernel. Adds a safety margin around the protected components. Larger values can merge neighboring components and create larger native crops.",
        "Положительный нечётный размер эллиптического ядра расширения. Добавляет защитный отступ вокруг компонент. Большое значение может объединить соседние компоненты и увеличить native-фрагменты."),
    "min_clean_threshold": (
        "Minimum uint8 intensity threshold inside each object crop. If local Otsu > 10, use max(minimum, int(local Otsu × factor)); otherwise use this minimum alone. Removes dim pixels before measuring shape and skeleton.",
        "Минимальный порог яркости uint8 внутри объекта. Если локальный Otsu > 10, используется max(минимум, int(Otsu × коэффициент)); иначе только минимум. Удаляет слабые пиксели до измерения формы и скелета."),
    "tier2_threshold_factor": (
        "Multiplier of the local Otsu threshold inside an annotation or detected contour. Lower factors retain weaker object pixels; the minimum cleanup threshold still applies.",
        "Множитель локального порога Otsu внутри разметки или найденного контура. Меньший коэффициент сохраняет слабые пиксели; минимальный порог очистки продолжает действовать."),
    "min_sub_object_area": (
        "Minimum area of each 8-connected cleaned component before it becomes a measured object. Units are native source pixels squared for v3 datasets. Small components below the threshold are discarded.",
        "Минимальная площадь каждой очищенной 8-связной компоненты перед измерением. Для v3 единицы — квадрат исходного native-пикселя. Компоненты меньше порога отбрасываются."),
    "min_corridor_width": (
        "Minimum width in source pixels for an obstacle-free straight slicing corridor. Protected components are kept whole after boundary proposals are assigned. It is not a minimum fiber width.",
        "Минимальная ширина свободного прямого коридора нарезки в исходных пикселях. Защищённые компоненты сохраняются целиком после распределения предложенных границ. Это не минимальная толщина волокна."),
    "dataset": (
        "The active prepared tile dataset for review, annotations and measurements. Raw TIFFs appear on Sources, not here. Prepare TIFFs or open a previously prepared dataset folder. Different runs keep distinct identifiers.",
        "Активный подготовленный набор для проверки, разметки и измерений. Исходные TIFF находятся на странице «Исходники», а не здесь. Подготовьте TIFF или откройте папку ранее подготовленного набора. У запусков разные идентификаторы."),
    "open_tiles": (
        "Open one dataset folder, for example FL01_G3_RGB_Red, containing model tile PNGs plus native/, valid_masks/ and overview/*.json. Do not choose the parent directory containing many datasets. Reuses saved tiles and skips filtering/slicing.",
        "Откройте папку конкретного набора, например FL01_G3_RGB_Red, с модельными PNG и native/, valid_masks/, overview/*.json. Не выбирайте общую папку нескольких наборов. Использует сохранённые тайлы, минуя фильтрацию и нарезку."),
    "source_selection": (
        "Checked TIFF rows form the processing batch. Selecting a row only chooses the preview image; it does not change the checkboxes. Multiple TIFFs must support the selected channel and plane.",
        "TIFF с галочками составляют пакет обработки. Выделение строки выбирает только изображение для предпросмотра и не меняет галочки. Выбранный канал и плоскость должны существовать во всех TIFF пакета."),
    "tile_search": (
        "Filter the visible tile list by ID or filename. This does not exclude tiles from measurements. Clear the search to see all tiles.",
        "Фильтрует список по ID или имени файла. Поиск не исключает тайлы из измерений. Очистите запрос, чтобы увидеть все тайлы."),
    "tile_filter": (
        "Display active, excluded or bright-region tiles. Bright-region flags are review hints, not biological class predictions. Only explicit exclusion changes the active measurement set.",
        "Показать активные, исключённые тайлы или яркие области. Флаг яркой области — подсказка для проверки, а не биологический класс. Только явное исключение меняет набор измерений."),
    "tile_ids": (
        "Enter comma-separated IDs and ranges, such as 4,12-18, or select rows. Exclude moves only model PNGs to excluded_tiles; Restore returns them. Native crops, ownership masks and metadata remain. IDs belong to this slicing run.",
        "Введите ID и диапазоны через запятую, например 4,12-18, или выделите строки. Исключение переносит модельные PNG в excluded_tiles, возврат возвращает их. Native, маски принадлежности и метаданные сохраняются. ID относятся к этому запуску нарезки."),
    "labels_mode": (
        "Existing only: measure available annotations. Require all: every active tile needs a TXT. Automatic fallback: missing TXT files use detected contours with Unknown source class. An empty TXT always means no annotated objects, not a request for automatic detection.",
        "Только разметка: измерять имеющиеся полигоны. Требовать все: TXT нужен каждому активному тайлу. Автоматическое выделение: при отсутствующем TXT использовать контуры с исходным классом Unknown. Пустой TXT всегда означает отсутствие размеченных объектов."),
    "image_viewer": ("Drag to pan; use the mouse wheel or +/− to zoom. Double-click or press F11 to open a separate full-screen view; Esc closes it. The image is a bounded preview; measurements use native pixels.",
                     "Перетаскивайте для панорамирования; колесо и +/− меняют масштаб. Двойной щелчок или F11 открывает отдельный полный экран, Esc закрывает его. Показан уменьшенный предпросмотр; измерения используют native-пиксели."),
    "image_fullscreen": ("Open the loaded image in a separate full-screen window with the same polygons and original-pixel click coordinates. Pan, zoom and fit work independently of the original pane. Use double-click or F11 to open, and Esc or F11 to close. Changing the source image closes the window.",
                         "Открывает загруженное изображение в отдельном полноэкранном окне с теми же полигонами и координатами исходных пикселей. Масштаб, панорамирование и вписывание работают независимо от исходной панели. Открытие — двойной щелчок или F11, закрытие — Esc или F11. При смене изображения окно закрывается."),
    "image_zoom": ("Zoom the preview without changing image files or measurement scale.", "Изменяет масштаб просмотра, не меняя файлы и масштаб измерений."),
    "image_fit": ("Fit the entire preview into the available window.", "Показывает предпросмотр целиком в доступном окне."),
    "result_search": ("Search displayed feature rows by tile or object. Filtered export includes only visible rows; training export follows its own classification selection.",
                      "Поиск строк признаков по тайлу или объекту. Экспорт видимых строк включает только текущие строки; обучающий экспорт использует собственный выбор классификации."),
    "result_class_filter": ("Filter by original segmentation class or separately assigned manual class. Unclassified means no manual class has been saved. Filtering does not change measurements.",
                            "Фильтрует по исходному классу сегментации или отдельному ручному классу. «Без класса» означает отсутствие сохранённого ручного класса. Не меняет измерения."),
    "manual_class": ("Assign an object using the shared YOLO class IDs: 0 Particle, 1 Fiber, 2 Self-crossed tube, 3 Crossed tubes, 4 Agglomeration, 5 Adhered objects. You can also clear its class. Manual review is saved separately; original segmentation labels and scientific measurements remain unchanged.",
                     "Назначить объекту класс с общими для YOLO ID: 0 — частица, 1 — волокно, 2 — пересечение трубочки самой собой, 3 — перекрещенные трубочки, 4 — агломерация, 5 — несколько слипшихся объектов. Можно убрать класс. Ручная проверка сохраняется отдельно; исходная разметка сегментации и научные измерения не меняются."),
    "manual_navigation": ("Navigate through the currently visible objects. Next unclassified finds an object without a saved manual class within the current filters. Save and next saves first, then advances.",
                          "Переход по видимым объектам. «Следующий без класса» ищет объект без сохранённого ручного класса в текущем фильтре. «Сохранить и дальше» сначала сохраняет класс, затем переходит."),
    "manual_export": ("Export scientific predictors with Manual_Class_ID as the reviewed training target, using the same class IDs as YOLO. Only classified objects are included by default. Original Class_ID and Class_Name stay in the CSV as metadata; they and source identifiers are excluded from the predictor list. This exports data for later training.",
                      "Экспортирует научные признаки и проверенную целевую метку Manual_Class_ID с теми же ID классов, что у YOLO. По умолчанию включаются только классифицированные объекты. Исходные Class_ID и Class_Name остаются в CSV как метаданные; они и идентификаторы источника исключены из списка признаков модели. Данные предназначены для последующего обучения."),
}


def help_text(key, language=None):
    language = language or get_language()
    if language == 'he':
        return HELP_HEBREW.get(key, 'יש לרחף מעל ? לקבלת הסבר.')
    entry = _HELP.get(key)
    if entry is None:
        return "Hover over ? for help." if (language or get_language()) == "en" else "Наведите на ? для пояснения."
    return entry[1] if (language or get_language()) == "ru" else entry[0]


def attach_help(widget, key):
    widget.setToolTip(help_text(key))
    widget.setWhatsThis(help_text(key))
    widget.setProperty("helpKey", key)
    return widget


def help_label(key):
    label = QtWidgets.QLabel("?")
    label.setObjectName("helpBadge")
    label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    label.setFixedSize(20, 20)
    label.setCursor(QtCore.Qt.CursorShape.WhatsThisCursor)
    attach_help(label, key)
    return label
