"""Practical advice shown alongside the versioned parameter reference.

Each description is written in English, Russian and Hebrew.
Keys match the settings catalog. The Help dialog combines these examples with
the separate reference for purpose, validation and factory defaults.
"""

GUIDANCE = {
    'channel': (
        'A color or multichannel TIFF can store several brightness images at each position. In Preparation, select a source and preview the chosen channel. For ordinary RGB, 0 is red, 1 is green and 2 is blue. Use the channel that contains your signal. When preparing several checked TIFFs together, verify that the same channel index makes sense for each file.',
        'В цветном или многоканальном TIFF на одну позицию приходится несколько значений яркости. В «Подготовке» выберите исходник и запустите предпросмотр выбранного канала. Для обычного RGB 0 — красный, 1 — зелёный, 2 — синий. Выбирайте канал, в котором видны нужные структуры. При пакетной обработке проверьте, что один и тот же номер подходит всем отмеченным файлам.',
        'ב־TIFF צבעוני או רב־ערוצי יכולים להיות כמה ערכי בהירות בכל מיקום. בהכנה בחרו מקור והפעילו תצוגה מקדימה של הערוץ הנבחר. ב־RGB רגיל 0 הוא אדום, 1 ירוק ו־2 כחול. בחרו ערוץ שמכיל את האות הדרוש. בעיבוד אצווה בדקו שאותו מספר ערוץ מתאים לכל הקבצים המסומנים.'),
    'plane': (
        'A stack can store successive depths or time points. In Preparation, choose the index of the one image you want to process. Index 0 selects the first image. For a single 2D image, leave it at 0. Preview again after changing the index and confirm that the chosen depth or time point is visible.',
        'Стек может содержать изображения на разных глубинах или в разные моменты времени. В «Подготовке» выберите номер изображения для обработки. Номер 0 соответствует первому. Для одиночного 2D-изображения оставьте 0. После смены номера повторите предпросмотр и проверьте нужную глубину или кадр.',
        'ערימה יכולה להכיל תמונות בעומקים או בזמנים שונים. בהכנה בחרו את מספר התמונה לעיבוד. מספר 0 בוחר את הראשונה. לתמונה דו־ממדית יחידה השאירו 0. לאחר שינוי המספר הפעילו שוב תצוגה מקדימה ובדקו את העומק או הזמן שנבחר.'),
    'pixel_size_um': (
        'Use From TIFF metadata in Preparation if the acquisition software saved a supported pixel size. If a trusted scale bar says 10 µm and spans 20 original pixels, the manual value is 10/20 = 0.5 µm/px. Enter it only for a batch acquired at that scale. After measurement, check that the expected Area_um2 column appears.',
        'В «Подготовке» используйте режим «Из метаданных TIFF», если программа съёмки записала поддерживаемый размер пикселя. Если достоверная масштабная линейка 10 мкм занимает 20 исходных пикселей, ручное значение равно 10/20 = 0,5 мкм/px. Применяйте его к пакету, снятому с этим масштабом. После измерения проверьте, появился ли ожидаемый столбец Area_um2.',
        'בהכנה השתמשו במטא־נתוני TIFF אם תוכנת הצילום שמרה גודל פיקסל נתמך. אם סרגל אמין של 10 מיקרומטר משתרע על 20 פיקסלי מקור, הערך הידני הוא 10/20 = 0.5 מיקרומטר לפיקסל. השתמשו בו לאצווה שצולמה באותו קנה מידה. אחרי המדידה בדקו שעמודת Area_um2 מופיעה.'),
    'target_size': (
        'Choose a side length appropriate for the model images you intend to annotate. A change affects both search distances and the output canvas. Prepare a new version, check large objects in Model and Native, then use annotation files that belong to that version.',
        'Выберите сторону поля, подходящую для изображений, которые будете размечать. Размер задаёт и поле модельного PNG, и расстояния поиска границ. Подготовьте новую версию, проверьте крупные объекты в видах «Модель» и «Native» и используйте разметку, созданную для этой версии.',
        'בחרו אורך צלע מתאים לתמונות המודל שתרצו לתייג. שינוי משפיע על מרחקי החיפוש ועל משטח הפלט. הכינו גרסה חדשה, בדקו עצמים גדולים בתצוגות המודל והמקור והשתמשו בתיוגים של אותה גרסה.'),
    'search_window_end': (
        'With a 1500 px tile, enter 1400 and check that the right/down slider reaches 100 px. Choose a shift and prepare the same source in a new run. Inspect the search GIF or boundary map. Dijkstra also uses the new initial window.',
        'При тайле 1500 введите 1400 и проверьте, что ползунок вправо или вниз доходит до 100 px. Выберите сдвиг и заново подготовьте тот же исходник. Проверьте GIF поиска или карту границ. Дейкстра тоже использует новое первое окно.',
        'באריח בגודל 1500 הזינו 1400 ובדקו שהמחוון ימינה או למטה מגיע ל־100 פיקסלים. בחרו הזזה והכינו שוב את אותו מקור בריצה חדשה. בדקו את הנפשת החיפוש או מפת הגבולות. גם דייקסטרה משתמש בחלון הראשון החדש.'),
    'straight_shift_left': (
        'Leave the left/up limit on Automatic to use the original trials. For a manual comparison, set it to 0, prepare the same source again and inspect the search GIFs or tile boundaries.',
        'Оставьте для сдвига влево и вверх автоматическое значение, чтобы использовать прежние пробы. Для сравнения задайте 0, заново подготовьте тот же исходник и проверьте GIF поиска или границы тайлов.',
        'השאירו את הגבול שמאלה ולמעלה במצב אוטומטי כדי להשתמש בניסיונות המקוריים. להשוואה ידנית הגדירו 0, הכינו שוב את אותו מקור ובדקו את הנפשות החיפוש או את גבולות האריחים.'),
    'straight_shift_right': (
        'When the first window is blocked, a positive right/down limit lets the straight search try the far side. Try 30 px at tile size 1500, prepare a new version and compare boundaries or search GIFs on the same source.',
        'Если первое окно перекрыто, положительный предел позволяет поискать прямой проход правее или ниже. Попробуйте 30 px при размере 1500, подготовьте новую версию и сравните границы или GIF поиска на том же исходнике.',
        'אם החלון הראשון חסום, גבול חיובי ימינה ולמטה מאפשר לחפש מעבר ישר בצד הרחוק. נסו 30 פיקסלים בגודל אריח 1500, הכינו גרסה חדשה והשוו גבולות או הנפשות חיפוש באותו מקור.'),
    'overview_size': (
        'Use this when the overview is too small to locate regions or too expensive to store. Compare two map sizes using the same tile set or otherwise identical preparation settings. Inspect individual object detail in the Native tile view.',
        'Меняйте размер, если на карте трудно найти нужный участок или если карта занимает слишком много места. Сравните два размера для одного набора либо при одинаковых остальных настройках подготовки. Детали отдельного объекта проверяйте на тайле в исходном масштабе.',
        'שנו את הגודל כאשר קשה לאתר אזורים במפה או כשהיא תופסת יותר מדי מקום. השוו שני גדלים באותו מערך או בהגדרות הכנה זהות ביתר הפרטים. לפרטי עצם עברו לתצוגת האריח בקנה המידה המקורי.'),
    'bilateral_d': (
        'The diameter limits the neighborhood examined around each pixel. Start with 9 and compare the same faint fiber and background patch at 5. Check both whether the background smooths out and whether the fiber edges remain distinct.',
        'Диаметр ограничивает размер окрестности вокруг пикселя. Начните с 9 и сравните те же слабое волокно и участок фона при 5. Проверьте, стал ли фон ровнее и остались ли границы волокна различимыми.',
        'הקוטר מגביל את גודל הסביבה הנבדקת סביב כל פיקסל. התחילו ב־9 והשוו את אותו סיב חלש ואת אותו אזור רקע בערך 5. בדקו אם הרקע נעשה חלק ואם גבולות הסיב נותרו ברורים.'),
    'bilateral_sigma_color': (
        'This is a brightness tolerance. If a dark background and a faint bright object begin to blend, compare a smaller value with the default 45. Leave the diameter and spatial sigma fixed for that comparison.',
        'Это допуск по разнице яркости. Если тёмный фон и слабый светлый объект начинают сливаться, сравните меньшее значение с заводским 45. Диаметр и пространственную сигму оставьте одинаковыми в обоих просмотрах.',
        'זו סבילות להפרשי בהירות. אם רקע כהה ועצם בהיר וחלש מתמזגים, השוו ערך קטן יותר לברירת המחדל 45. השאירו את הקוטר והסיגמה המרחבית קבועים בהשוואה.'),
    'bilateral_sigma_space': (
        'Spatial sigma controls how quickly a neighbor’s influence falls with distance within the chosen diameter. Compare the filtered image at the same zoom and with the same diameter. Check fine structure and background texture together.',
        'Пространственная сигма задаёт, насколько быстро ослабевает вклад соседа с расстоянием внутри выбранного диаметра. Сравнивайте фильтрацию в одном масштабе и при одном диаметре. Смотрите одновременно на мелкие структуры и текстуру фона.',
        'הסיגמה המרחבית קובעת כמה מהר השפעת שכן פוחתת עם המרחק בתוך הקוטר שנבחר. השוו את התמונה המסוננת באותו זום ובאותו קוטר. בדקו מבנים עדינים ומרקם רקע יחד.'),
    'tophat_radius': (
        'The radius controls the scale used to estimate background. Radius 85 gives a 171×171 footprint. Compare regions containing both broad background variation and bright objects. Look for residual background and for large structures whose interiors become less visible.',
        'Радиус задаёт масштаб, на котором оценивается фон. Радиус 85 даёт область 171×171. Сравните участки, где есть и плавный перепад фона, и яркие объекты. Посмотрите, сколько фона осталось и не стали ли хуже видны внутренние части крупных структур.',
        'הרדיוס שולט בקנה המידה של אומדן הרקע. רדיוס 85 נותן מסגרת 171×171. השוו אזורים עם שינויי רקע רחבים ועצמים בהירים. בדקו שאריות רקע והאם פנים מבנים גדולים נעשה פחות ברור.'),
    'gamma': (
        'Compare gamma 1 and 1.2 with the other filters fixed. For example, a brightness of 64 on the 0–255 scale becomes about 80 at 1.2. Compare both the filtered view and Protective mask. Brightening a weak fiber can also make nearby background enter the mask.',
        'Сравните гамму 1 и 1,2 при одинаковых остальных фильтрах. Например, яркость 64 по шкале 0–255 при 1,2 становится примерно 80. Посмотрите и на отфильтрованное изображение, и на защитную маску. Вместе со слабым волокном в маску может попасть осветлённый фон рядом с ним.',
        'השוו גאמה 1 ו־1.2 כשהמסננים האחרים קבועים. לדוגמה, בהירות 64 בסולם 0–255 נעשית בערך 80 בערך 1.2. בדקו גם את התמונה המסוננת וגם את מסכת ההגנה. הבהרת סיב חלש יכולה להכניס למסכה גם רקע סמוך.'),
    'otsu_safety_factor': (
        'Use the Protective mask preview. If faint stretches of a fiber are missing, compare a smaller factor. If large areas of background join nearby objects, compare a larger factor. Once the calculated threshold reaches its floor of 10, further reductions of the factor leave it at 10.',
        'Смотрите вкладку «Защитная маска». Если слабые участки волокна пропадают, сравните меньший коэффициент. Если большие области фона соединяют соседние объекты, сравните больший. Когда вычисленный порог доходит до нижней границы 10, дальнейшее уменьшение коэффициента оставляет порог равным 10.',
        'בדקו את מסכת ההגנה. אם קטעי סיב חלשים חסרים, השוו מקדם קטן יותר. אם אזורי רקע גדולים מחברים עצמים סמוכים, השוו מקדם גדול יותר. כאשר הסף המחושב מגיע לרצפה 10, הקטנה נוספת של המקדם משאירה אותו ב־10.'),
    'bridge_kernel_size': (
        'Closing connects short dark gaps in the white regions of the protective mask. Compare the same broken fiber and a pair of nearby fibers. A larger kernel can bridge the break and can also connect the separate pair. Use odd sizes so the ellipse has a central pixel.',
        'Замыкание соединяет короткие тёмные разрывы в белых областях защитной маски. Сравните одно волокно с разрывом и два соседних волокна. Более крупное ядро может закрыть разрыв и одновременно соединить раздельную пару. Нечётный размер даёт эллипсу центральный пиксель.',
        'סגירה מגשרת על פערים כהים קצרים באזורים הלבנים של מסכת ההגנה. השוו סיב עם פער וזוג סיבים סמוכים. גרעין גדול יותר יכול לסגור את הפער וגם לחבר את הזוג הנפרד. גודל אי־זוגי נותן לאליפסה פיקסל מרכזי.'),
    'buffer_kernel_size': (
        'Dilation adds white pixels around protected regions to give the route extra clearance. At size 5 the ellipse extends two pixels from the center along its axes. Compare narrow background gaps in Protective mask and inspect whether adjacent protected regions merge.',
        'Расширение добавляет белые пиксели вокруг защищённых областей, чтобы оставить запас для маршрута. При размере 5 эллипс тянется на два пикселя от центра вдоль осей. Сравните узкие промежутки фона на защитной маске и проверьте, не слились ли соседние области.',
        'הרחבה מוסיפה פיקסלים לבנים סביב האזורים המוגנים כדי להגדיל מרווח למסלול. בגודל 5 האליפסה משתרעת שני פיקסלים מהמרכז לאורך הצירים. השוו מרווחי רקע צרים במסכת ההגנה ובדקו אם אזורים סמוכים התאחדו.'),
    'min_corridor_width': (
        'A corridor is a straight strip of background pixels wide enough for the proposed cut. On a dense image, compare the overview boundaries after preparing a new version. The slicer can try a narrower corridor and then use a routed seam when straight search fails.',
        'Коридор — прямая полоса фоновых пикселей, в которой можно провести границу. Для плотного изображения сравните границы на карте после подготовки новой версии. Нарезка может проверить более узкий коридор, а при неудаче прямого поиска проложить маршрут.',
        'מסדרון הוא רצועה ישרה של פיקסלי רקע שמספיקה לקו חיתוך. בתמונה צפופה השוו את גבולות הסקירה לאחר הכנת גרסה חדשה. האלגוריתם יכול לבדוק מסדרון צר יותר ואז לחפש מסלול כשהחיפוש הישר נכשל.'),
    'seam_repulsion_power': (
        'This matters when the slicer has to route a seam through the background. A greater power makes distant free pixels cheaper relative to those near a protected object. Compare route geometry on the same image while keeping the mask settings fixed.',
        'Параметр действует, когда нарезка прокладывает границу по фону. При большей степени свободные пиксели вдали от защищённого объекта обходятся дешевле относительно близких. Сравнивайте форму маршрута на одном изображении при одинаковой защитной маске.',
        'הערך משפיע כאשר האלגוריתם מתכנן מסלול חיתוך ברקע. חזקה גבוהה יותר מוזילה פיקסלים פנויים רחוקים יחסית לקרובים לעצם מוגן. השוו צורת מסלול באותה תמונה עם אותה מסכת הגנה.'),
    'oversized_policy': (
        'If a protected component forces a crop larger than the model canvas, preserve keeps the crop at source resolution and fits a reduced copy in the model canvas. Use error if your workflow requires the preparation to stop for oversized crops. Inspect the Native and Model versions of large regions before annotating.',
        'Если защищённая компонента требует фрагмента больше модельного поля, preserve сохраняет фрагмент в исходном разрешении и помещает уменьшенную копию в модельное поле. Режим error подходит, когда при таком фрагменте обработку нужно остановить. Перед разметкой сравните исходный и модельный виды крупных участков.',
        'אם רכיב מוגן מחייב חיתוך גדול ממשטח המודל, preserve שומר את החיתוך ברזולוציית המקור ומתאים עותק מוקטן למשטח המודל. השתמשו ב־error כשהעבודה מחייבת לעצור במקרה כזה. לפני תיוג בדקו את תצוגות המקור והמודל של אזורים גדולים.'),
    'min_clean_threshold': (
        'This floor applies inside object outlines. It also sets the initial contour-search threshold on tiles with missing TXT in automatic mode. If verification crops include background, compare a higher value. If weak parts disappear, compare a lower one. Check the same tiles before trusting changes in Area or skeleton features.',
        'Это нижняя граница порога внутри контуров объекта. В автоматическом режиме она также задаёт начальный порог поиска контуров на тайлах без TXT. Если в проверочных фрагментах много фона, сравните более высокий порог. Если пропадают слабые части объекта, сравните более низкий. Смотрите те же тайлы перед сравнением площади и признаков скелета.',
        'זהו סף תחתון בתוך קווי מתאר של עצמים. במצב אוטומטי הוא משמש גם סף התחלתי לחיפוש מתארים באריחים ללא TXT. אם פרגמנטי האימות כוללים רקע, השוו ערך גבוה יותר. אם חלקים חלשים נעלמים, השוו ערך נמוך יותר. בדקו אותם אריחים לפני השוואת שטח ותכונות שלד.'),
    'tier2_threshold_factor': (
        'This multiplier adapts the cutoff to each candidate outline. With local Otsu 30, factor 0.70 and a floor of 25, the final threshold is 25 because 21 is below the floor. If changing the factor appears to do nothing, check whether the floor is already controlling the result.',
        'Множитель подстраивает порог под каждый контур. При локальном Otsu 30, коэффициенте 0,70 и нижней границе 25 итоговый порог равен 25, потому что 21 меньше нижней границы. Если смена коэффициента не даёт заметного эффекта, проверьте, не задаётся ли результат уже нижней границей.',
        'המקדם מתאים את הסף לכל קו מתאר מועמד. עם Otsu מקומי 30, מקדם 0.70 ורצפה 25, הסף הסופי הוא 25 כי 21 נמוך מהרצפה. אם שינוי המקדם אינו משפיע, בדקו אם הרצפה כבר קובעת את התוצאה.'),
    'min_sub_object_area': (
        'Apply this after pixel cleanup. For example, if one outline yields components of 18 and 45 pixels, a limit of 30 keeps the 45-pixel component. Lower the limit only after checking whether small fragments are meaningful or background noise.',
        'Порог площади действует после очистки пикселей. Если из одного контура получились компоненты по 18 и 45 пикселей, при пороге 30 останется компонента из 45. Прежде чем снижать порог, проверьте, есть ли среди мелких фрагментов нужные объекты или это шум.',
        'הסף חל אחרי ניקוי הפיקסלים. לדוגמה, אם מתאר אחד נותן רכיבים של 18 ו־45 פיקסלים, סף 30 שומר את הרכיב בן 45 הפיקסלים. לפני הורדת הסף בדקו אם הפרגמנטים הקטנים משמעותיים או רעש רקע.'),
    'save_raw_tiles': (
        'Enable this to keep a matching crop of the original selected channel for comparison with the filtered crop. The extra files use more disk space. Inspect matching tile IDs when comparing the two versions.',
        'Включите, если нужна копия того же фрагмента из исходного канала для сравнения с фильтрованным. Дополнительные файлы займут место на диске. При сравнении сопоставляйте одинаковые ID тайлов.',
        'הפעילו כדי לשמור חיתוך תואם מהערוץ המקורי להשוואה לחיתוך המסונן. הקבצים הנוספים תופסים מקום בכונן. השוו אריחים עם אותו מזהה.'),
    'enable_animations': (
        'Use the GIFs to understand where the slicer looked for a cut. Start with one image to check the time and disk cost. Read the frames as search windows and the accepted route. Use the final overview and ownership to inspect the actual assigned regions.',
        'GIF помогают понять, где нарезка искала границу. Начните с одного изображения, чтобы оценить время и объём файлов. Кадры показывают окна поиска и принятый маршрут. Фактическое распределение пикселей смотрите по итоговой карте и маске принадлежности.',
        'השתמשו ב־GIF להבנת המקומות שבהם האלגוריתם חיפש חיתוך. התחילו מתמונה אחת להערכת זמן ונפח. המסגרות מציגות חלונות חיפוש ומסלול שהתקבל. בדקו את השיוך בפועל בסקירה ובמסכת השיוך הסופית.'),
    'save_coverage_masks': (
        'Enable this if a later model workflow needs to know how much of each output pixel belongs to the tile. Intermediate gray means partial coverage in the model image. For source-resolution inspection, open Ownership in Tiles.',
        'Включите, если следующему этапу работы с моделью нужно знать, какая доля каждого выходного пикселя принадлежит тайлу. Промежуточный серый означает частичное покрытие на модельном изображении. Для проверки в исходном разрешении откройте маску принадлежности в «Тайлах».',
        'הפעילו אם שלב המודל זקוק לחלק של כל פיקסל פלט השייך לאריח. אפור ביניים פירושו כיסוי חלקי בתמונת המודל. לבדיקה ברזולוציית המקור פתחו את מסכת השיוך בדף האריחים.'),
    'animation_max_trial_frames': (
        'This limits trial frames in search GIFs when animation saving is enabled. A smaller limit makes the sequence shorter and can leave out intermediate attempts. Compare GIFs to diagnose the search and use the overview for the final boundaries.',
        'Ограничивает число пробных кадров в GIF, когда включено сохранение анимаций. Меньший предел укорачивает последовательность и может пропустить промежуточные попытки. Используйте GIF для разбора поиска, а итоговые границы проверяйте по обзорной карте.',
        'מגביל מסגרות ניסיון ב־GIF כאשר שמירת הנפשות פעילה. מגבלה קטנה יותר מקצרת את הרצף ועשויה להשמיט ניסיונות ביניים. השתמשו ב־GIF לבדיקת החיפוש ובסקירה לבדיקת הגבולות הסופיים.'),
    'enable_bilateral': (
        'Compare this switch on and off before tuning the three bilateral controls. Check a faint structure and a background region at the same zoom. When smoothing is off, its diameter and sigma values have no effect.',
        'Сравните включённое и выключенное сглаживание, прежде чем настраивать три параметра bilateral. Посмотрите слабую структуру и фон в одинаковом масштабе. При отключённом фильтре диаметр и обе сигмы не влияют на результат.',
        'השוו בין מצב פעיל לכבוי לפני כיוון שלוש בקרות הסינון הבילטרלי. בדקו מבנה חלש ואזור רקע באותו זום. כשהמסנן כבוי, לקוטר ולערכי הסיגמה אין השפעה.'),
    'enable_tophat': (
        'Compare a region with uneven illumination before and after enabling this step. The switch controls both background subtraction and the subsequent contrast stretch. Check faint objects and broad bright structures as well as the background.',
        'Сравните участок с неравномерным освещением при выключенном и включённом фильтре. Переключатель управляет и вычитанием фона, и последующим растяжением контраста. Проверьте слабые объекты, широкие светлые структуры и фон.',
        'השוו אזור עם תאורה לא אחידה כשהשלב כבוי ופעיל. המתג שולט בהסרת הרקע וגם במתיחת הניגודיות אחריה. בדקו עצמים חלשים, מבנים בהירים רחבים ואת הרקע.'),
    'enable_gamma': (
        'Switch gamma off to compare the result of the preceding filters with the brightness remapping. Check whether faint structures become easier to see and whether more background enters Protective mask.',
        'Выключите гамму, чтобы сравнить результат предыдущих фильтров с преобразованием яркости. Проверьте, стали ли заметнее слабые структуры и не попало ли больше фона в защитную маску.',
        'כבו גאמה כדי להשוות את תוצאת המסננים הקודמים למיפוי הבהירות. בדקו אם קל יותר לראות מבנים חלשים ואם יותר רקע נכנס למסכת ההגנה.'),
    'enable_closing': (
        'Compare a visibly broken protected structure with closing off and on. Also inspect gaps between separate structures. If closing connects nearby objects across the background, compare a smaller closing kernel.',
        'Сравните защищённую структуру с заметным разрывом при выключенном и включённом замыкании. Посмотрите и на промежутки между отдельными структурами. Если замыкание соединяет соседние объекты через фон, сравните ядро меньшего размера.',
        'השוו מבנה מוגן עם פער נראה כשהסגירה כבויה ופעילה. בדקו גם מרווחים בין מבנים נפרדים. אם הסגירה מחברת עצמים סמוכים דרך הרקע, השוו גרעין סגירה קטן יותר.'),
    'enable_dilation': (
        'Toggle this to see how much margin the protective mask adds around a structure. If neighboring regions merge when it is enabled, compare a smaller dilation kernel. Evaluate the result in Protective mask and then in the tile overview.',
        'Переключите расширение, чтобы увидеть, какой запас добавляется вокруг структуры. Если соседние области сливаются при включении, сравните ядро меньшего размера. Оцените результат сначала на защитной маске, затем на карте тайлов.',
        'החליפו מצב כדי לראות כמה מרווח מסכת ההגנה מוסיפה סביב מבנה. אם אזורים סמוכים מתמזגים כשההרחבה פעילה, השוו גרעין קטן יותר. בדקו תחילה במסכת ההגנה ואחר כך בסקירת האריחים.'),
}
