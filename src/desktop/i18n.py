"""Pure-Python English/Russian/Hebrew catalogue shared with the worker."""

from .hebrew import HEBREW_TRANSLATIONS, translate_hebrew

LANGUAGES = ('en', 'ru', 'he')

_language = "en"

# Russian source strings remain accepted for the existing pipeline's messages.
_EN = {
    "Исходники": "Sources", "Подготовка": "Preparation", "Тайлы": "Tiles",
    "Разметка": "Annotations", "Результаты": "Results", "Новый проект": "New project",
    "Открыть": "Open", "Сохранить": "Save", "Тёмная тема": "Dark theme", "Светлая тема": "Light theme",
    "Набор:": "Dataset:", "Набор": "Dataset", "Готов к работе": "Ready",
    "Добавить TIFF": "Add TIFF", "Подключить готовую нарезку": "Open prepared tiles",
    "Открыть подготовленные тайлы": "Open prepared tiles", "Открыть тайлы…": "Open tiles…",
    "К подготовке →": "Prepare →", "Выбор": "Select", "Изображение": "Image",
    "Размеры": "Dimensions", "Оси": "Axes", "Тип": "Type", "Статус": "Status",
    "Добавьте TIFF или подключите готовую нарезку": "Add TIFF images or open prepared tiles",
    "Исходные изображения остаются на диске. Выберите TIFF для подготовки или подключите существующий набор v3.":
        "Source images stay on disk. Select TIFFs to prepare, or open a previously prepared v3 tile dataset.",
    "Выберите строку, чтобы увидеть путь и свойства TIFF. Галочки задают пакет обработки.":
        "Select a row to inspect TIFF properties. Checkboxes select the images to process.",
    "Размер модельного тайла": "Model tile size", "Размер обзорной карты": "Overview size",
    "Канал (нумерация с 0)": "Channel (starting at 0)", "Плоскость стека": "Stack plane",
    "Калибровка µm/px": "Calibration, µm/px", "Не задана · исходные px": "Not set · source pixels",
    "Сохранить raw-тайлы": "Save raw tiles", "Сохранить анимации поиска": "Save search animations",
    "Сохранить модельные маски покрытия": "Save model coverage masks",
    "Крупные объекты уменьшаются до модельного тайла целиком. Native-фрагменты сохраняют пространственный масштаб для измерений.":
        "Large objects are reduced to fit a model tile while staying whole. Native crops preserve source scale for measurements.",
    "Параметры фильтрации и защитной маски": "Filtering and protective mask",
    "Bilateral: размер": "Bilateral: diameter", "Bilateral: интенсивность": "Bilateral: intensity sigma",
    "Bilateral: пространство": "Bilateral: spatial sigma", "Top-hat: радиус": "Top-hat: radius",
    "Доля порога Otsu": "Safety Otsu factor", "Соединение защитной маски": "Protective bridge kernel",
    "Буфер защитной маски": "Protective buffer kernel", "Порог очистки объекта": "Object cleanup threshold",
    "Локальная доля Otsu": "Local Otsu factor", "Минимальная площадь (native px²)": "Minimum area, native px²",
    "Минимальная ширина коридора": "Minimum corridor width", "Исходный канал": "Source channel",
    "Фильтрация": "Filtering", "Защитная маска": "Protective mask", "Предпросмотр": "Preview",
    "Предпросмотр выбранного TIFF": "Preview selected TIFF", "Подготовить выбранные TIFF": "Prepare selected TIFFs",
    "Здесь появится отфильтрованное изображение": "The filtered image will appear here",
    "Здесь появится защитная маска": "The protective mask will appear here",
    "Предпросмотр служит проверкой параметров. Полная подготовка использует весь TIFF; набор сохраняет собственный снимок настроек.":
        "Preview helps check settings. Preparation uses the full TIFF; each dataset stores its own settings snapshot.",
    "Подключите или подготовьте набор, чтобы проверить тайлы": "Prepare or open a dataset to review its tiles",
    "ID или имя тайла": "Tile ID or filename", "Все тайлы": "All tiles", "Активные": "Active",
    "Исключённые": "Excluded", "Яркие области": "Bright regions", "Карта": "Overview",
    "Модельный": "Model", "Принадлежность": "Ownership", "Полигоны": "Polygons",
    "Обзорная карта ещё не открыта": "No overview is open yet",
    "Выберите тайл из списка или нажмите на карту": "Select a tile from the list or click the overview",
    "Native-фрагмент сохраняет исходный пространственный масштаб": "Native crop preserves the source spatial scale",
    "Маска принадлежности пикселей тайлу": "Exact pixel ownership mask",
    "Полигонная разметка выбранного тайла": "Polygon annotations for the selected tile",
    "На карте выбор определяется точной маской принадлежности пикселей.":
        "Overview selection uses the exact pixel ownership mask.",
    "ID: 4, 12-18 · или выделите тайлы": "IDs: 4, 12-18 · or select tiles",
    "Исключить": "Exclude", "Вернуть": "Restore", "Обновить карту": "Rebuild overview",
    "Проверка завершена": "Review complete", "Обзорная карта": "Overview",
    "Импортировать папку разметки": "Import annotation folder", "Проверить разметку": "Check annotations",
    "Открыть папку": "Open folder", "Разметка ещё не подключена": "No annotations are connected",
    "Импортируйте YOLO segmentation: один TXT на модельный PNG, нормализованные координаты полигона. Разметка связана с текущими ID тайлов.":
        "Import YOLO segmentation: one TXT per model PNG, with normalized polygon coordinates. Annotations belong to the current tile IDs.",
    "Выберите тайл на странице «Тайлы», чтобы увидеть его разметку": "Select a tile on the Tiles page to view its annotations",
    "Только имеющаяся разметка": "Use existing annotations only",
    "Требовать разметку всех активных тайлов": "Require annotations for every active tile",
    "Для отсутствующей разметки выделять объекты автоматически": "Automatically detect objects where annotations are missing",
    "Режим измерений": "Measurement mode", "Рассчитать признаки": "Extract features",
    "Пустой TXT означает отсутствие размеченных объектов. Автоматически найденные объекты получают класс Unknown. Native используется для измерений и обратного переноса полигонов.":
        "An empty TXT means no annotated objects. Automatically detected objects have the Unknown source class. Measurements and polygon mapping use native crops.",
    "Признаки ещё не рассчитаны": "Features have not been extracted yet",
    "AR = большая / малая ось маски. Площади v3 измерены в исходных пикселях; µm² доступны при заданной калибровке. Скелет даёт концы и количество пикселей ветвления.":
        "AR = major / minor mask axis. v3 areas use source pixels; µm² requires calibration. Skeleton features count endpoints and branching pixels.",
    "Выберите объект в таблице для проверки маски": "Select an object in the table to inspect its mask",
    "Обновить результаты": "Refresh results", "Открыть папку результатов": "Open results folder",
    "Экспорт всей таблицы": "Export full table", "Экспорт видимых строк": "Export visible rows",
    "Остановить": "Stop", "Журнал": "Log", "Измерения": "Measurements",
    "Подключение набора": "Opening dataset", "Выбор тайла": "Selecting tile", "Импорт разметки": "Importing annotations",
    "Чтение TIFF": "Reading TIFF", "Чтение тайлов": "Reading tiles", "Проверка набора": "Validating dataset",
    "Поиск границ": "Finding boundaries", "Защитные компоненты": "Protected components",
    "Сохранение тайлов": "Saving tiles", "Нарезка": "Slicing", "Обработка": "Processing",
    "Готов": "Ready", "Готов к проверке": "Ready for review", "Выполняется": "Running",
    "Остановлен": "Stopped", "Ошибка": "Error", "Подключён": "Connected", "Ожидает": "Pending",
    "Незавершён": "Incomplete", "Нужна проверка": "Needs review", "Новый": "New",
    "Ожидает разметку": "Awaiting annotations", "Прерван": "Interrupted", "Проверен": "Reviewed",
    "Нужна проверка тайлов": "Tile review required", "активен": "active", "исключён": "excluded",
    "Проект сохранён: ": "Project saved: ", "Создан проект ": "Created project ", "Открыт проект ": "Opened project ",
    "Создать проект": "Create project", "Открыть проект": "Open project", "Проект SoLoData (*.json)": "SoLoData project (*.json)",
    "Добавлено исходников: {v0}": "Sources added: {v0}",
    "Добавьте TIFF для предпросмотра.": "Add a TIFF to preview.",
    "Выберите хотя бы один TIFF галочкой на странице «Исходники».": "Check at least one TIFF on the Sources page.",
    "Сначала подготовьте TIFF или подключите готовую нарезку.": "Prepare a TIFF or open prepared tiles first.",
    "Дождитесь завершения текущей задачи или остановите её.": "Wait for the current job to finish or stop it.",
    "Дождитесь текущей операции": "Wait for the current operation",
    "Не удалось обновить набор: ": "Could not refresh dataset: ", "Набор недоступен или незавершён: ": "Dataset unavailable or incomplete: ",
    "Проверка набора: ": "Dataset validation: ",
    "Обзорная карта · нажмите на область для выбора тайла": "Overview · click a region to select its tile",
    "Карта отсутствует. Нажмите «Обновить карту».": "Overview missing. Click Rebuild overview.",
    "Тайлов: {v0} · Активных: {v1} · Исключённых: {v2} · Ярких областей: {v3}":
        "Tiles: {v0} · Active: {v1} · Excluded: {v2} · Bright regions: {v3}",
    "Тайл {v0} · {v1} · Native: {v2} px · Исходных px / модельный px: {v3:.4f} · Принадлежащих пикселей: {v4}":
        "Tile {v0} · {v1} · Native: {v2} px · Source px / model px: {v3:.4f} · Owned pixels: {v4}",
    "{v0}\nОси: {v1} · Размеры: {v2} · Тип: {v3}": "{v0}\nAxes: {v1} · Dimensions: {v2} · Type: {v3}",
    "  · исключён": "  · excluded", "  · яркая область": "  · bright region",
    "Native · исходный пространственный масштаб": "Native · source spatial scale",
    "Точная принадлежность · белые пиксели относятся к выбранному тайлу": "Exact ownership · white pixels belong to the selected tile",
    "Файл разметки отсутствует": "Annotation file missing", "Нужен полигон YOLO с минимум тремя точками": "YOLO polygon needs at least three points",
    "Размеченных полигонов: {v0}": "Annotated polygons: {v0}", "Пустой TXT · размеченных объектов нет": "Empty TXT · no annotated objects",
    "Ошибка разметки: ": "Annotation error: ", "В выбранном пикселе нет тайла": "No tile owns the selected pixel",
    "Выделите тайлы или введите их ID/диапазоны.": "Select tiles or enter their IDs/ranges.", "Исключение: ": "Exclusion: ", "Возврат: ": "Restore: ",
    "Проверка тайлов завершена: ": "Tile review completed: ", "Подготовьте или подключите набор.": "Prepare or open a dataset.",
    "Разметка ещё не импортирована": "No annotations have been imported", "Активных тайлов": "Active tiles",
    "Всего": "Total", "С разметкой": "Annotated", "Пустых TXT": "Empty TXT", "Без TXT": "Missing TXT",
    "Некорректных TXT": "Invalid TXT", "Неизвестные имена": "Unknown filenames", "Ошибки": "Errors",
    "Полигонов": "Polygons", "Корректных TXT": "Valid TXT", "Лишних TXT": "Extra TXT",
    "Отсутствующие TXT": "Missing TXT", "Пустые TXT": "Empty TXT", "Размеченные TXT": "Annotated TXT",
    "Проверка разметки завершена": "Annotation check completed", "Ошибка проверки: ": "Validation error: ",
    "Результаты требуют пересчёта: разметка или состав тайлов изменились": "Results need recalculation: annotations or active tiles have changed",
    "Выберите набор для просмотра результатов": "Select a dataset to view results",
    "{v0} объектов · {v1}": "{v0} objects · {v1}", "Результаты обновлены": "Results refreshed",
    "Не удалось открыть CSV: ": "Could not open CSV: ",
    "Объект {v0} · {v1} · {v2}": "Object {v0} · {v1} · {v2}",
    "Сохранённая маска объекта отсутствует": "Saved object mask is missing", "Некорректный идентификатор объекта": "Invalid object ID",
    "Папка ещё не создана.": "The folder has not been created yet.", "Сначала рассчитайте признаки.": "Extract features first.",
    "Экспорт результатов": "Export results", "CSV сохранён: ": "CSV saved: ",
    "Разметка или состав тайлов изменились. Пересчитайте признаки перед экспортом.": "Annotations or active tiles have changed. Recalculate features before exporting.",
    "Экспортировано объектов: {v0} · {v1}": "Exported objects: {v0} · {v1}",
    " · запуск…": " · starting…", "Запуск: ": "Starting: ", "Останавливается…": "Stopping…",
    "Задача завершилась ошибкой": "The job failed", "Результат: ": "Result: ", "Неизвестная ошибка": "Unknown error",
    "Ошибка: ": "Error: ", "Ошибка · подробности в журнале": "Error · see the log", "Ошибка процесса: ": "Process error: ",
    "Остановлено · завершённые результаты сохранены": "Stopped · completed results were retained", "Задача": "Job", " · завершено": " · completed",
    "Обработчик не подтвердил результат": "The worker did not confirm a result", "Код завершения: {v0}": "Exit code: {v0}",
    "Задача не завершена: ": "Job incomplete: ", "Не удалось перечитать проект: ": "Could not reload project: ",
    "Останавливается после текущей операции…": "Stopping after the current operation…",
    "Запрошена безопасная остановка. Текущая операция может требовать времени.": "Safe stop requested. The current operation may take time to finish.",
    "Задача выполняется": "A job is running",
    "Остановить задачу и закрыть приложение после безопасного завершения текущей операции?": "Stop the job and close the application after the current operation finishes safely?",
    "Этот проект уже открыт в другом окне SoLoData. Закройте его или выберите другой проект.": "This project is already open in another SoLoData window. Close it there or choose a different project.",
}


_RU = {english: russian for russian, english in _EN.items()}


def get_language():
    return _language


def set_language(language):
    global _language
    if language not in LANGUAGES:
        raise ValueError("Supported interface languages are en, ru and he")
    _language = language


def tr(text, language=None, **values):
    language = language or _language
    if language == "ru":
        translated = _RU.get(text, text)
    elif language == 'he':
        canonical = _EN.get(text, text)
        translated = translate_hebrew(canonical)
    else:
        translated = _EN.get(text, text)
    return translated.format(**values) if values else translated


def register_translations(english_to_russian, *, hebrew=None):
    """Allow additional shared widget catalogues to register canonical text."""
    _EN.update({russian: english for english, russian in english_to_russian.items()})
    _RU.update(english_to_russian)
    if hebrew:
        HEBREW_TRANSLATIONS.update(hebrew)


def supported_languages():
    return LANGUAGES


register_translations({
    "Full screen": "Во весь экран", "Exit full screen": "Выйти из полного экрана",
    "Full screen · double-click or F11; Esc to close": "Во весь экран: двойной щелчок или F11; Esc — закрыть",
    "Bilateral denoising": "Bilateral-сглаживание", "White top-hat": "White top-hat",
    "Gamma correction": "Гамма-коррекция", "Morphological closing": "Морфологическое замыкание",
    "Protective dilation": "Защитное расширение", "Segmentation": "Сегментация",
    "Skipping bilateral filter": "Bilateral-фильтр пропущен",
    "Skipping white top-hat": "White top-hat пропущен",
    "Skipping gamma correction": "Гамма-коррекция пропущена",
    "Closing protective gaps": "Замыкание разрывов защитной маски",
    "Skipping protective closing": "Замыкание защитной маски пропущено",
    "Adding protective buffer": "Добавление защитного буфера",
    "Skipping protective dilation": "Защитное расширение пропущено",
    "Denoising": "Сглаживание", "Subtracting background": "Вычитание фона",
    "Enhancing contrast": "Гамма-преобразование", "Building protective mask": "Создание защитной маски",
    "Filtering complete": "Фильтрация завершена",
    "Language": "Язык", "No prepared datasets": "Нет подготовленных наборов",
    "Create a tile dataset on Preparation, or open a folder prepared earlier.":
        "Создайте набор на странице «Подготовка» или откройте ранее подготовленную папку.",
    "Open prepared tile dataset — select a dataset folder, not its parent":
        "Открыть подготовленные тайлы — выберите папку конкретного набора, не родительскую папку",
    "Open a dataset folder containing model PNGs, native, valid_masks and overview. This skips filtering and slicing.":
        "Откройте папку ранее подготовленного pipeline набора с модельными PNG, native, valid_masks и overview. Фильтрация и нарезка выполняться не будут.",
    "Manual object classes": "Ручные классы объектов", "Class": "Класс", "Unclassified": "Без класса",
    "Save class": "Сохранить класс", "Save and next": "Сохранить и дальше", "Previous": "Назад",
    "Next": "Дальше", "Next unclassified": "Следующий без класса", "Export training CSV": "Экспорт обучающей таблицы",
    "{assigned} / {total} objects classified": "Классифицировано: {assigned} / {total}",
    "Select an object from the results table": "Выберите объект в таблице результатов",
    "{tile} · Object {object}": "{tile} · Объект {object}",
    "Recalculate current results before assigning classes": "Пересчитайте актуальные результаты перед присвоением классов",
    "Manual classes are saved separately from segmentation labels": "Ручные классы сохраняются отдельно от разметки сегментации",
    "Particle": "Частица", "Fiber": "Волокно", "Agglomeration": "Агломерация",
    "Crossed tubes": "Перекрещенные трубочки", "Self-crossed tube": "Пересечение трубочки самой собой",
    "Adhered objects": "Несколько слипшихся объектов", "All classes": "Все классы", "Source class": "Исходный класс",
    "Manual class": "Ручной класс", "Manual class ID": "ID ручного класса", "Reviewed": "Проверен",
    "Search by tile or object": "Поиск по тайлу или объекту", "No results": "Нет результатов",
    "Objects: {visible} / {total}": "Объекты: {visible} / {total}",
    "Fit to window": "По размеру окна", "Select an image to preview": "Выберите изображение для просмотра",
    "Loading preview…": "Загрузка предпросмотра…", "Image missing": "Изображение отсутствует",
    "Could not open image: {error}": "Не удалось открыть изображение: {error}",
    "Features": "Признаки", "Manual class saved": "Ручной класс сохранён",
    "No unclassified objects match the current filters": "Нет объектов без класса в текущем фильтре",
    "Only classified objects": "Только объекты с классом",
    "Export training data": "Экспорт обучающих данных",
    "Exported {rows} objects to {path}": "Экспортировано {rows} объектов: {path}",
    "No unique slicing manifest was found.": "Не найден однозначный manifest нарезки.",
    "Could not read the tile ownership mask.": "Не удалось прочитать маску принадлежности тайла.",
    "The dataset has no current feature table.": "У набора нет актуальной таблицы признаков.",
    "Recalculate features: annotations or active tiles have changed.": "Пересчитайте признаки: разметка или состав тайлов изменились.",
    "Recalculate features before exporting the training table.": "Пересчитайте признаки перед экспортом обучающей таблицы.",
    "Processing was stopped by the user.": "Обработка остановлена пользователем.",
    "Validating the saved dataset": "Проверка сохранённого набора", "Add and select source TIFFs.": "Добавьте и выберите исходные TIFF.",
    "Reusing a verified dataset": "Проверенный набор используется повторно", "Preparing {name}": "Подготовка {name}",
    "Processing stopped.": "Обработка остановлена.", "Dataset processed": "Набор обработан",
    "Preparation did not finish. See the execution log.": "Подготовка не завершилась. Подробности в журнале выполнения.",
    "Choose a folder containing text annotation files.": "Выберите папку с текстовыми файлами разметки.",
    "Validating annotation polygons": "Проверка полигонов разметки", "Annotation errors:\n": "Разметка содержит ошибки:\n",
    "Unknown object extraction mode.": "Неизвестный режим получения объектов.",
    "Fix annotation errors before extracting features.": "Исправьте ошибки разметки перед расчётом.",
    "Some active tiles have no annotation files.": "Для части активных тайлов отсутствуют файлы разметки.",
    "Import annotations first, or select automatic object detection.": "Сначала импортируйте разметку или выберите автоматическое выделение объектов.",
    "Select a TIFF to preview.": "Выберите TIFF для предпросмотра.",
    "Reading a crop for preview": "Чтение фрагмента для предпросмотра", "Unknown action: {action}": "Неизвестная операция: {action}",
    "YOLO segmentation TXT folder": "Папка с TXT в формате YOLO segmentation",
    "Image is missing": "Изображение отсутствует", "Could not open image: {message}": "Не удалось открыть изображение: {message}",
    "Class {id}": "Класс {id}", "Search by tile, object or class": "Поиск по тайлу, объекту или классу",
    "Source: {class_name}": "Исходный: {class_name}", "Manual: {class_name}": "Ручной: {class_name}",
    "Yes": "Да", "Source class ID": "ID исходного класса", "Tile": "Тайл", "Object": "Объект",
    "Source dataset": "Исходный набор", "Area, px²": "Площадь, px²", "AR (major / minor axis)": "AR (большая / малая ось)",
    "Solidity": "Плотность формы", "Euler number": "Число Эйлера", "Skeleton endpoints": "Концы скелета",
    "Branch pixels": "Пиксели ветвления", "Measurement space": "Пространство измерения",
    "Source px / model px": "Исходных px / модельный px", "Area, µm²": "Площадь, µm²",
    "Sphere": "Сфера", "Curve": "Кривая", "Self-intersecting curve": "Самопересекающаяся кривая",
    "Intersecting curves": "Пересекающиеся кривые", "Unknown": "Неизвестный",
    "Invalid object tile name": "Некорректное имя тайла объекта",
    "Object ID must be a positive integer": "ID объекта должен быть положительным целым числом",
    "Object classification requires a saved measurement version": "Классификация объектов требует сохранённой версии измерений",
    "Measurement CSV is missing or outside its measurement directory": "CSV измерений отсутствует или находится вне папки измерений",
    "Measurement CSV has invalid object identity columns": "Некорректные столбцы идентификаторов объектов в CSV измерений",
    "Scientific measurement CSV must not contain manual targets": "CSV научных измерений не должен содержать ручные целевые метки",
    "Measurement CSV contains duplicate object identities": "CSV измерений содержит повторяющиеся идентификаторы объектов",
    "Unsupported manual object labels format": "Неподдерживаемый формат ручных классов объектов",
    "Manual labels belong to a different measurement version or CSV": "Ручные классы относятся к другой версии измерений или CSV",
    "Invalid manual object labels": "Некорректные ручные классы объектов",
    "Manual label references an unknown measured object": "Ручной класс ссылается на неизвестный измеренный объект",
    "Invalid manual class or review state": "Некорректный ручной класс или состояние проверки",
    "Manual label object identity mismatch": "Идентификатор объекта ручного класса не совпадает",
    "Unknown manual object class": "Неизвестный ручной класс объекта",
    "The selected object does not exist in this measurement version": "Выбранного объекта нет в этой версии измерений",
    "Manual label output must not be a symlink": "Файл ручных классов не должен быть символической ссылкой",
    "Training export must not overwrite measurement data or manual labels": "Обучающий экспорт не должен перезаписывать измерения или ручные классы",
    "Training export requires feature columns: {columns}": "Обучающий экспорт требует столбцы признаков: {columns}",
    "Feature {feature} must be a finite number for object {object}": "Признак {feature} объекта {object} должен быть конечным числом",
    "Export must not overwrite measurement data, object masks, or manual labels": "Экспорт не должен перезаписывать измерения, маски объектов или ручные классы",
    "No": "Нет", "source_pixels": "Исходные пиксели", "tile_pixels": "Пиксели тайла",
})
