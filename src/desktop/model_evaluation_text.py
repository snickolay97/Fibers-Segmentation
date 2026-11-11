"""Localized strings shared by the model training page and worker."""

from .i18n import register_translations

# Keep worker diagnostics and widget captions in the same catalog so an error
# reported through the job protocol uses the same terms as the training page.
_TEXT = {
    'Rename selected model…': ('Переименовать выбранную модель…', 'שינוי שם המודל שנבחר…'),
    'Display name (up to 80 characters). Leave blank to reset.': (
        'Имя модели до 80 символов. Пустое поле вернёт стандартное имя.',
        'שם תצוגה עד 80 תווים. שדה ריק מחזיר את שם ברירת המחדל.'),
    'Depth and tuning': ('Глубина и подбор', 'עומק וכוונון'),
    'Open table in a separate window…': ('Открыть таблицу отдельно…', 'פתיחת טבלה בחלון נפרד…'),
    'Evaluation metrics': ('Сводка оценок', 'סיכום מדדי הערכה'),
    'Drag to resize the summary and detail tables.': (
        'Перетащите разделитель, чтобы изменить высоту сводки и деталей.',
        'גררו את המפריד כדי לשנות את גובה הסיכום והפרטים.'),
    'Each row is a candidate. The highest pooled validation macro-F1 wins. In a tie, the first candidate wins.': (
        'Каждая строка — кандидат. Побеждает наибольший macro-F1 по объединённым прогнозам проверочных блоков. При равенстве выбирается первый кандидат.',
        'כל שורה היא מועמד. הערך הגבוה ביותר של macro-F1 על תחזיות התיקוף המאוחדות מנצח. בשוויון נבחר המועמד הראשון.'),
    'There are no validation trials in this report.': (
        'В этом отчёте нет результатов подбора по проверочным блокам.', 'אין בדוח הזה תוצאות מניסויי תיקוף.'),
    'Selected': ('Выбран', 'נבחר'),
    'Split criterion': ('Критерий разбиения', 'קריטריון פיצול'),
    'Depth limit': ('Предел глубины', 'מגבלת עומק'),
    'Minimum leaf size': ('Минимум объектов в листе', 'גודל עלה מזערי'),
    'Features per split': ('Признаков на разбиение', 'תכונות לפיצול'),
    'Pooled macro-F1': ('Общий macro-F1', 'macro-F1 מאוחד'),
    'Fold {number}': ('Блок {number}', 'קפל {number}'),
    'All predictors': ('Все признаки', 'כל התכונות'),
    'Node depth': ('Глубина узла', 'עומק הצומת'),
    'Yes → node': ('Да → узел', 'כן ← צומת'),
    'No → node': ('Нет → узел', 'לא ← צומת'),
    'Class at node': ('Класс в узле', 'מחלקה בצומת'),
    'Model training': ('Обучение модели', 'אימון מודל'),
    'Review new objects…': ('Проверка новых объектов…', 'בדיקת עצמים חדשים…'),
    'Split criterion — {criterion}': (
        'Критерий разбиения узла — {criterion}', 'מדד פיצול צומת — {criterion}'),
    'Entropy': ('Энтропия', 'אנטרופיה'),
    'Best validation macro-F1 with {criterion} — {score:.6f}': (
        'Лучший macro-F1 на валидации с критерием {criterion} — {score:.6f}',
        'ציון macro-F1 הטוב ביותר בתיקוף עם {criterion} — {score:.6f}'),
    'Training data': ('Данные для обучения', 'נתוני אימון'),
    'Split method': ('Способ разбиения', 'שיטת חלוקה'),
    'Whole TIFFs / experiments': ('Целые TIFF / эксперименты', 'קובצי TIFF או ניסויים שלמים'),
    'Stratified objects (same-source check)': (
        'По объектам с учётом классов (те же снимки)', 'חלוקה לפי מחלקות עצמים (אותם מקורות)'),
    'Trees in forest': ('Деревьев в лесу', 'מספר עצים ביער'),
    'Object classes to train': ('Классы объектов для обучения', 'מחלקות עצמים לאימון'),
    'Same-source object test. Scores apply to these TIFFs.': (
        'Тест по объектам. Оценки относятся к этим TIFF.', 'בדיקה לפי עצמים. הציונים מתייחסים לקובצי TIFF אלה.'),
    'Integer class counts produce a different test fraction from 20%.': (
        'При целочисленных размерах классов доля теста отличается от 20%.',
        'כאשר מספר העצמים בכל מחלקה שלם, שיעור הבדיקה שונה מ־20%.'),
    'Object fold {number}': ('Фолд по объектам {number}', 'קפל עצמים {number}'),
    'No reviewed objects in selected classes': (
        'Нет проверенных объектов выбранных классов', 'אין עצמים מתויגים במחלקות שנבחרו'),
    'Selected classes without reviewed objects (IDs {ids}).': (
        'В выбранных классах нет проверенных объектов (ID {ids}).', 'במחלקות שנבחרו אין עצמים מתויגים (מזהים {ids}).'),
    'Select at least two supported object classes.': (
        'Выберите минимум два поддерживаемых класса объектов.', 'בחרו לפחות שתי מחלקות עצמים נתמכות.'),
    'Select a supported split method.': ('Выберите допустимый способ разбиения.', 'בחרו שיטת חלוקה נתמכת.'),
    'Use {low}–{high} trees in the forest.': (
        'Укажите от {low} до {high} деревьев в лесу.', 'הזינו {low}–{high} עצים ביער.'),
    'Object K-fold needs at least K training objects in each class. Reduce K or select other classes.': (
        'Для K фолдов по объектам нужно минимум K обучающих объектов каждого класса. Уменьшите K или выберите другие классы.',
        'תיקוף K לפי עצמים דורש לפחות K עצמי אימון בכל מחלקה. הקטינו את K או בחרו מחלקות אחרות.'),
    'No test objects remain after reserving training examples for every class.': (
        'После выделения обучающих примеров для каждого класса объектов для теста не осталось.',
        'לא נותרו עצמים לבדיקה לאחר שמירת דוגמאות אימון לכל מחלקה.'),
    'Open training table…': ('Открыть обучающую таблицу…', 'פתיחת טבלת אימון…'),
    'Use project datasets': ('Использовать наборы проекта', 'שימוש במערכי הפרויקט'),
    'Training tables (*.xlsx *.csv)': ('Обучающие таблицы (*.xlsx *.csv)', 'טבלאות אימון (*.xlsx *.csv)'),
    'Reading reviewed training table': ('Чтение проверенной обучающей таблицы', 'קריאת טבלת אימון מתויגת'),
    'Save selected model…': ('Сохранить выбранную модель…', 'שמירת המודל שנבחר…'),
    'Fitted models (*.joblib)': ('Обученные модели (*.joblib)', 'מודלים מאומנים (*.joblib)'),
    'Model saved.': ('Модель сохранена.', 'המודל נשמר.'),
    'Use the .joblib extension.': ('Используйте расширение .joblib.', 'השתמשו בסיומת ‎.joblib.'),
    'Choose a destination outside saved evaluation folders.': (
        'Выберите место за пределами папок сохранённых оценок.', 'בחרו יעד מחוץ לתיקיות ההערכות השמורות.'),
    'Choose either a training table or project datasets.': (
        'Выберите обучающую таблицу или наборы проекта.', 'בחרו טבלת אימון או מערכי פרויקט.'),
    'Choose a .xlsx or .csv training table.': (
        'Выберите обучающую таблицу .xlsx или .csv.', 'בחרו טבלת אימון מסוג ‎.xlsx או ‎.csv.'),
    'The training table contains duplicate column names.': (
        'В обучающей таблице повторяются имена столбцов.', 'בטבלת האימון יש שמות עמודות כפולים.'),
    'Training table requires columns: {columns}.': (
        'Для обучающей таблицы нужны столбцы {columns}.', 'בטבלת האימון נדרשות העמודות {columns}.'),
    'Invalid manual class, source or predictors on training table row {row}.': (
        'Некорректный ручной класс, исходник или признаки в строке {row} обучающей таблицы.',
        'מחלקה ידנית, מקור או תכונות לא תקינים בשורה {row} בטבלת האימון.'),
    'Duplicate reviewed object on training table row {row}.': (
        'Повтор размеченного объекта в строке {row} обучающей таблицы.',
        'עצם מתויג כפול בשורה {row} בטבלת האימון.'),
    'Use only one measurement dataset per TIFF in the training table.': (
        'Включайте в обучающую таблицу только один набор измерений на каждый TIFF.',
        'כללו בטבלת האימון מערך מדידה אחד בלבד לכל TIFF.'),
    'A measurement dataset in the training table refers to more than one TIFF.': (
        'Один набор измерений в обучающей таблице ссылается на несколько TIFF.',
        'מערך מדידה אחד בטבלת האימון מפנה לכמה קובצי TIFF.'),
    'The training table changed while it was being read.': (
        'Обучающая таблица изменилась во время чтения.', 'טבלת האימון השתנתה בזמן הקריאה.'),
    'Split plan': ('План разбиения', 'תוכנית חלוקה'),
    'Model comparison': ('Сравнение моделей', 'השוואת מודלים'),
    'Select one measured dataset per TIFF. Enter the same group for related TIFFs. Imported tiles require a confirmed group.': (
        'Выберите один измеренный набор на TIFF. Для связанных TIFF укажите общую группу. Импортированные тайлы требуют подтверждения группы.',
        'בחרו מערך מדידות אחד לכל TIFF. הזינו אותה קבוצה לקובצי TIFF קשורים. אריחים מיובאים דורשים אישור קבוצה.'),
    'Area in source pixels²': ('Площадь в пикселях исходника²', 'שטח בפיקסלי מקור בריבוע'),
    'Area in µm²': ('Площадь в мкм²', 'שטח במיקרומטר רבוע'),
    'Area units': ('Единицы площади', 'יחידות שטח'),
    'Random seed': ('Случайное зерно', 'זרע אקראי'),
    'Cross-validation off': ('Кросс-валидация выключена', 'תיקוף צולב כבוי'),
    'Training-only K-fold': ('K-фолдов на обучающей части', 'תיקוף K בחלק האימון בלבד'),
    'Class distributions…': ('Распределения по классам…', 'התפלגויות לפי מחלקה…'),
    'Saved evaluations': ('Сохранённые оценки', 'הערכות שמורות'),
    'Confusion matrix': ('Матрица ошибок', 'מטריצת בלבול'),
    'Model for this matrix — {model}. Rows are reviewed classes. Columns are predictions.': (
        'Модель в этой матрице — «{model}». Строки — ручные классы, столбцы — прогнозы.',
        'המודל במטריצה זו הוא ״{model}״. השורות הן המחלקות הידניות והעמודות הן התחזיות.'),
    'Model details': ('Детали модели', 'פרטי מודל'),
    'Depth limit — {depth}': ('Предел глубины — {depth}', 'מגבלת עומק — {depth}'),
    'No preset limit': ('без заданного предела', 'ללא תקרה מוגדרת'),
    'Actual tree depth — {depth}': ('Фактическая глубина дерева — {depth}', 'עומק העץ בפועל — {depth}'),
    'Requested number of trees — {count}': ('Задано деревьев — {count}', 'מספר עצים שהתבקש — {count}'),
    'Fitted trees — {count}. Actual depths — {minimum} to {maximum}.': (
        'Обучено деревьев — {count}. Фактические глубины — от {minimum} до {maximum}.',
        'עצים שאומנו — {count}. עומקים בפועל — {minimum} עד {maximum}.'),
    'Selected by validation macro-F1 — {score:.6f}. The first candidate wins an exact tie.': (
        'Выбор по проверочному macro-F1 — {score:.6f}. При точном равенстве побеждает первый вариант.',
        'הבחירה נעשתה לפי macro-F1 בתיקוף — {score:.6f}. בשוויון מדויק נבחר המועמד הראשון.'),
    'Cross-validation is off. Fixed settings were used.': (
        'Кросс-валидация выключена. Использованы фиксированные настройки.',
        'התיקוף הצולב כבוי. נעשה שימוש בהגדרות קבועות.'),
    'Final fit — {seconds:.3f} s': (
        'Финальное обучение — {seconds:.3f} с', 'אימון סופי — {seconds:.3f} שניות'),
    'Tuning — {count} fits, {seconds:.3f} s of fitting in total': (
        'Подбор — {count} обучений, суммарное время обучения {seconds:.3f} с',
        'כיוונון — {count} אימונים, {seconds:.3f} שניות אימון בסך הכול'),
    'Object inspection': ('Проверка объекта', 'בדיקת עצם'),
    'All incorrect predictions': ('Все ошибки выбранной модели', 'כל השגיאות של המודל הנבחר'),
    'Tree wrong, forest correct': ('Дерево ошиблось, лес прав', 'העץ שגה והיער צדק'),
    'Forest wrong, tree correct': ('Лес ошибся, дерево право', 'היער שגה והעץ צדק'),
    'Preview 80/20 split': ('Проверить разбиение 80/20', 'תצוגה מקדימה לחלוקת 80/20'),
    'Train and evaluate': ('Обучить и оценить', 'אימון והערכה'),
    'Dataset': ('Набор', 'מערך נתונים'),
    'Source': ('Исходник', 'מקור'),
    'Group override · double-click to edit': ('Группа · двойной щелчок для ввода', 'קבוצה · לחיצה כפולה לעריכה'),
    'Unconfirmed': ('Не подтверждён', 'לא אושר'),
    'Select an evaluation…': ('Выберите оценку…', 'בחרו הערכה…'),
    'Preview the plan before training.': ('Проверьте план перед обучением.', 'בדקו את התוכנית לפני האימון.'),
    'Working…': ('Выполняется…', 'מתבצע…'),
    'Plan ready.': ('План готов.', 'התוכנית מוכנה.'),
    'Evaluation saved.': ('Оценка сохранена.', 'ההערכה נשמרה.'),
    'Unsupported evaluation report.': ('Версия отчёта не поддерживается.', 'גרסת הדוח אינה נתמכת.'),
    'Demonstration only. No independent test groups.': ('Демонстрация. Независимой тестовой группы нет.', 'הדגמה בלבד. אין קבוצת בדיקה עצמאית.'),
    'Train {train} · Test {test} ({fraction}%)': ('Обучение {train} · Тест {test} ({fraction}%)', 'אימון {train} · בדיקה {test} ({fraction}%)'),
    'Whole groups produce a different test fraction from 20%.': ('При сохранении целых групп доля теста отличается от 20%.', 'שמירה על קבוצות שלמות יוצרת שיעור בדיקה שונה מ־20%.'),
    'Training groups': ('Обучающие группы', 'קבוצות אימון'),
    'Validation groups': ('Группы валидации', 'קבוצות תיקוף'),
    'Test groups': ('Тестовые группы', 'קבוצות בדיקה'),
    'Group': ('Группа', 'קבוצה'),
    'Split': ('Часть', 'חלוקה'),
    'Train': ('Обучение', 'אימון'),
    'Test': ('Тест', 'בדיקה'),
    'Validation': ('Валидация', 'תיקוף'),
    'Model': ('Модель', 'מודל'),
    'Test objects': ('Объектов в тесте', 'עצמים בבדיקה'),
    'Actual class': ('Ручной класс', 'מחלקה ידנית'),
    'Precision': ('Точность класса', 'דיוק מחלקה'),
    'Recall': ('Полнота класса', 'כיסוי מחלקה'),
    'Row percentages': ('Проценты по строкам', 'אחוזים לפי שורה'),
    'Tree nodes': ('Узлы дерева', 'צומתי העץ'),
    'Classes absent from test': ('Классы без объектов в тесте', 'מחלקות שאינן במבחן'),
    'Classes with more test than training objects': (
        'Классы, в которых тестовых объектов больше, чем обучающих', 'מחלקות עם יותר עצמי בדיקה מעצמי אימון'),
    'Node': ('Узел', 'צומת'),
    'Rule': ('Правило', 'כלל'),
    'Objects': ('Объекты', 'עצמים'),
    'Groups': ('Группы', 'קבוצות'),
    'Leaf': ('Лист', 'עלה'),
    'Test permutation importance · decrease in macro-F1': ('Важность на тесте по перестановкам · снижение macro-F1', 'חשיבות לפי ערבוב במבחן · ירידה ב־macro-F1'),
    'Install scikit-learn from requirements.txt in the application environment.': (
        'Установите scikit-learn из requirements.txt в окружении приложения.',
        'התקינו scikit-learn מתוך requirements.txt בסביבת היישום.'),
    'Tile': ('Тайл', 'אריח'),
    'Object': ('Объект', 'עצם'),
    'Saved object image unavailable.': ('Сохранённое изображение объекта недоступно.', 'תמונת העצם השמורה אינה זמינה.'),
    'All groups': ('Все группы', 'כל הקבוצות'),
    'dummy': ('Частый класс', 'המחלקה השכיחה'),
    'tree': ('Дерево решений', 'עץ החלטה'),
    'forest': ('Случайный лес', 'יער אקראי'),
    'Checking selected measurements': ('Проверка выбранных измерений', 'בדיקת המדידות שנבחרו'),
    'Fitting and evaluating models': ('Обучение и оценка моделей', 'אימון והערכת מודלים'),
    'included': ('Включён', 'נכלל'),
    'Missing or stale measurements': ('Измерения отсутствуют или устарели', 'מדידות חסרות או לא עדכניות'),
    'No reviewed objects': ('Нет ручных меток', 'אין עצמים שסווגו ידנית'),
    'Confirm source or experiment': ('Подтвердите исходник или эксперимент', 'אשרו מקור או ניסוי'),
    'Select a supported area unit.': ('Выберите допустимые единицы площади.', 'בחרו יחידות שטח נתמכות.'),
    'Select only one measurement dataset per original TIFF, including copies.': (
        'Выберите один набор измерений на исходный TIFF с учётом копий.', 'בחרו מערך מדידות אחד לכל TIFF מקורי, כולל עותקים.'),
    'One TIFF has conflicting experiment groups.': ('У одного TIFF указаны разные группы эксперимента.', 'לאותו TIFF שויכו קבוצות ניסוי שונות.'),
    'Missing or invalid predictors in {dataset}. Check area units and calibration.': (
        'Некорректные или отсутствующие признаки в {dataset}. Проверьте единицы площади и калибровку.',
        'במערך {dataset} יש תכונות חסרות או לא תקינות. בדקו את יחידות השטח והכיול.'),
    'Use a seed from 0 to 2147483647 and K from 2 to 10.': (
        'Допустимы зерно от 0 до 2147483647 и K от 2 до 10.', 'השתמשו בזרע בין 0 ל־2147483647 וב־K בין 2 ל־10.'),
    'The data or split changed. Preview the plan again.': (
        'Данные или разбиение изменились. Проверьте план заново.', 'הנתונים או החלוקה השתנו. בדקו את התוכנית מחדש.'),
    'Select datasets with reviewed objects and confirmed sources.': (
        'Выберите наборы с ручными метками и подтверждёнными исходниками.', 'בחרו מערכים עם סיווג ידני ומקורות מאומתים.'),
    'Cross-validation needs multiple training groups.': ('Для кросс-валидации нужно несколько обучающих групп.', 'תיקוף צולב דורש כמה קבוצות אימון.'),
    'Model comparison needs at least two reviewed classes.': ('Для сравнения моделей нужны минимум два размеченных класса.', 'השוואת מודלים דורשת לפחות שתי מחלקות מתויגות.'),
    'No group holdout can keep all reviewed classes in training.': (
        'При разбиении по группам невозможно оставить все размеченные классы в обучении.',
        'בחלוקה לפי קבוצות אי אפשר להשאיר את כל המחלקות המתויגות באימון.'),
    'Cross-validation needs at least K independent training groups.': (
        'Для кросс-валидации нужно не менее K независимых обучающих групп.', 'תיקוף צולב דורש לפחות K קבוצות אימון עצמאיות.'),
    'Cross-validation needs each class in at least two training groups.': (
        'Для кросс-валидации каждый класс должен встречаться минимум в двух обучающих группах.',
        'תיקוף צולב דורש שכל מחלקה תופיע לפחות בשתי קבוצות אימון.'),
    'No group holdout supports these folds with every class in each training fold.': (
        'Не найдено групповое разбиение, при котором все классы входят в обучение каждого фолда. Измените K, выключите кросс-валидацию или добавьте размеченные группы.',
        'לא נמצאה חלוקה לקבוצות שבה כל המחלקות מופיעות באימון של כל קפל. שנו את K, כבו תיקוף צולב או הוסיפו קבוצות מתויגות.'),
}

register_translations({key: values[0] for key, values in _TEXT.items()},
                      hebrew={key: values[1] for key, values in _TEXT.items()})
