"""Worked examples for the model training page and its diagnostic charts."""

from src.default_settings import MODEL_DEFAULTS


_TREE_LIMITS = MODEL_DEFAULTS['tree_candidate_limits']
_TREE_PAIRS = ', '.join(f'({depth}, {leaf})' for depth, leaf in _TREE_LIMITS)
_TREE_DEPTH, _TREE_LEAF = _TREE_LIMITS[0]
_FOREST_LEAF = MODEL_DEFAULTS['forest_candidate_limits'][0][2]
_CANDIDATES = len(_TREE_LIMITS) * len(MODEL_DEFAULTS['split_criteria'])

_TOPICS = {
    'tree_impurity': (
        ('Impurity criteria in a tree', 'Критерии информативности дерева', 'מדדי אי־טוהר בעץ'),
        (
            (
                ('Start with a group of objects', 'Начните с группы объектов', 'מתחילים מקבוצת עצמים'),
                (
                    'A tree separates objects by asking yes-or-no questions about their features. For example, “Is Solidity at most 0.82?” The group of training objects that reaches a question is called a node. The question sends each object into one of two smaller groups. A terminal group is a leaf. It supplies a prediction based on the classes that reached it.',
                    'Дерево разделяет объекты вопросами, на которые можно ответить «да» или «нет». Например, «Solidity не больше 0,82?». Группа обучающих объектов, дошедшая до вопроса, называется узлом. Ответ отправляет объект в одну из двух групп. Конечная группа называется листом. По классам объектов в листе дерево делает прогноз.',
                    'העץ מפריד עצמים בעזרת שאלות כן או לא על התכונות שלהם. לדוגמה, ״האם Solidity לכל היותר 0.82?״ קבוצת עצמי האימון שהגיעה לשאלה נקראת צומת. התשובה מעבירה את העצם לאחת משתי קבוצות. קבוצה סופית נקראת עלה. העץ מנבא לפי המחלקות של העצמים שהגיעו לעלה.',
                ),
            ),
            (
                ('Read the horizontal axis', 'Что означает ось X', 'מה מציג ציר X'),
                (
                    'Imagine a node with 10 objects and just two possible classes, particle and fiber. Let p be the fraction of particles. At p = 0.2 there are 2 particles and 8 fibers. At p = 0.5 there are 5 of each. At p = 0 or 1 all objects belong to one class. The graph lets you compare those possible mixes of classes.',
                    'Представьте узел из 10 объектов двух классов, частиц и волокон. Пусть p — доля частиц. При p = 0,2 в узле 2 частицы и 8 волокон. При p = 0,5 их поровну. При p = 0 или 1 все объекты одного класса. График показывает, как меняются значения критериев при разном составе группы.',
                    'דמיינו צומת עם 10 עצמים משתי מחלקות, חלקיקים וסיבים. נסמן את שיעור החלקיקים ב־p. כאשר p = 0.2 יש 2 חלקיקים ו־8 סיבים. כאשר p = 0.5 יש 5 מכל מחלקה. כאשר p = 0 או 1 כל העצמים שייכים למחלקה אחת. התרשים מראה כיצד המדדים משתנים עם הרכב הקבוצה.',
                ),
            ),
            (
                ('Read the three curves', 'Что показывают три кривые', 'מה מציגות שלוש העקומות'),
                (
                    'Blue Gini is the chance that two independent draws from this mix have different classes. Orange Shannon entropy measures uncertainty about the class. One bit is the uncertainty of a yes-or-no answer when both answers are equally likely. The dashed curve is the fraction you would get wrong by always guessing the most common class in the node. For 2 particles and 8 fibers, the three values are 0.32, about 0.72 bits and 0.20. At 50/50 the mix is strongest and the values are 0.50, 1 bit and 0.50. All three reach zero at either end. Compare values along the same curve because the scales have different meanings.',
                    'Синяя кривая Gini показывает вероятность получить разные классы при двух независимых случайных выборах из этой группы. Оранжевая кривая — энтропия Шеннона. Она показывает, насколько трудно угадать класс по одним долям. Один бит соответствует неопределённости ответа «да» или «нет», когда оба ответа равновероятны. Пунктир показывает долю ошибок, если всем объектам назначать самый частый класс узла. Для 2 частиц и 8 волокон значения равны 0,32, примерно 0,72 бита и 0,20. При 50/50 классы смешаны сильнее всего, значения равны 0,50, 1 биту и 0,50. На обоих концах все три значения равны нулю. Сравнивайте значения вдоль одной кривой, поскольку у них разный смысл.',
                    'עקומת ג׳יני הכחולה היא ההסתברות לקבל מחלקות שונות בשתי הגרלות עצמאיות מהקבוצה. העקומה הכתומה, אנטרופיית שאנון, מודדת את אי־הוודאות לגבי המחלקה. ביט אחד הוא אי־הוודאות של תשובת כן או לא כאשר שתי התשובות סבירות באותה מידה. הקו המקווקו מציג את שיעור השגיאות אם מנבאים תמיד את המחלקה השכיחה בצומת. ל־2 חלקיקים ו־8 סיבים הערכים הם 0.32, כ־0.72 ביט ו־0.20. ביחס 50/50 הערבוב מרבי והערכים הם 0.50, ביט אחד ו־0.50. בשני הקצוות כל המדדים שווים לאפס. השוו ערכים לאורך אותה עקומה כי למדדים יש משמעויות שונות.',
                ),
            ),
            (
                ('How the tree chooses a question', 'Как дерево выбирает вопрос', 'איך העץ בוחר שאלה'),
                (
                    'The tree tries thresholds and compares how much they reduce the class mix. Suppose the node starts with 4 particles and 6 fibers, giving Gini 0.48. One threshold puts 2 particles on the left (Gini 0) and 2 particles plus 6 fibers on the right (Gini 0.375). The left contains 2 of 10 objects and the right contains 8 of 10. After the split the weighted Gini is 0.2 × 0 + 0.8 × 0.375 = 0.30. The decrease is 0.48 − 0.30 = 0.18. A larger decrease is better when comparing allowable splits of the same node.',
                    'Дерево перебирает пороги и сравнивает, насколько уменьшается смешение классов. Пусть в исходном узле 4 частицы и 6 волокон. Его Gini равен 0,48. Один из порогов отправил влево 2 частицы (Gini равен 0), а вправо 2 частицы и 6 волокон (Gini равен 0,375). Слева 2 из 10 объектов, справа 8 из 10. Поэтому после разделения взвешенный Gini равен 0,2 × 0 + 0,8 × 0,375 = 0,30. Снижение составляет 0,48 − 0,30 = 0,18. Среди допустимых разделений этого узла дерево ищет то, которое даёт наибольшее снижение.',
                    'העץ מנסה ספים ומשווה בכמה הם מקטינים את ערבוב המחלקות. נניח שבצומת יש 4 חלקיקים ו־6 סיבים, ולכן ג׳יני שווה 0.48. סף אחד שולח שמאלה 2 חלקיקים (ג׳יני 0), וימינה 2 חלקיקים ו־6 סיבים (ג׳יני 0.375). משמאל יש 2 מתוך 10 עצמים ומימין 8 מתוך 10. ג׳יני המשוקלל אחרי הפיצול הוא 0.2 × 0 + 0.8 × 0.375 = 0.30. הירידה היא 0.48 − 0.30 = 0.18. מבין הפיצולים המותרים באותו צומת העץ מחפש את הירידה הגדולה ביותר.',
                ),
            ),
            (
                ('Formulas and where they are used', 'Формулы и где они применяются', 'נוסחאות והשימוש בהן'),
                (
                    'For any number of classes, pₖ is the fraction of class k in the node. Add the terms for every class to get Gini = 1 − Σpₖ² or entropy = −Σpₖ log₂(pₖ). An absent class adds zero. The dashed reference is 1 − the largest class fraction. SoLoData uses Gini or entropy to build the tree and measures prediction quality separately on held-out objects.',
                    'Для любого числа классов pₖ — доля класса k в узле. Складывая вклады всех классов, получаем Gini = 1 − Σpₖ² или энтропию = −Σpₖ log₂(pₖ). Отсутствующий класс даёт нулевой вклад. Пунктир равен единице минус доля самого частого класса. SoLoData строит дерево по Gini или энтропии, а качество прогнозов измеряет отдельно на отложенных объектах.',
                    'בכל מספר של מחלקות, pₖ הוא שיעור המחלקה k בצומת. סכימת התרומות של כל המחלקות נותנת ג׳יני = 1 − Σpₖ² או אנטרופיה = −Σpₖ log₂(pₖ). מחלקה חסרה תורמת אפס. הקו המקווקו שווה לאחת פחות שיעור המחלקה השכיחה ביותר. SoLoData בונה את העץ לפי ג׳יני או אנטרופיה, ומודדת בנפרד את איכות התחזיות על עצמים שנשמרו לבדיקה.',
                ),
            ),
        ),
    ),
    'model_fit': (
        ('Tree depth and training time', 'Глубина дерева и время обучения', 'עומק העץ וזמן האימון'),
        (
            (
                ('Give the results more room', 'Увеличьте область результатов', 'הגדילו את אזור התוצאות'),
                (
                    'In Model comparison, drag the horizontal divider to change the heights of the summary and detail tabs. Drag a column header boundary to change its width. Open table in a separate window lets you choose the metrics, confusion matrix, tuning, tree nodes or object inspection. Each window scrolls independently and follows the current report and model. Click a prediction cell in the separate confusion matrix to open its objects in a separate table.',
                    'В «Сравнении моделей» перетаскивайте горизонтальный разделитель, чтобы изменить высоту сводки и вкладок деталей. Ширина столбцов меняется за границы заголовков. В меню «Открыть таблицу отдельно…» выберите сводку, матрицу ошибок, подбор, узлы дерева или проверку объектов. У каждого окна своя прокрутка, а данные следуют за выбранной оценкой и моделью. Щелчок по ячейке прогнозов в отдельной матрице открывает её объекты в отдельной таблице.',
                    'בהשוואת מודלים גררו את המפריד האופקי כדי לשנות את גובה הסיכום ולשוניות הפרטים. גררו את הגבול בכותרת עמודה כדי לשנות את רוחבה. בפתיחת טבלה בחלון נפרד בחרו סיכום, מטריצת בלבול, כוונון, צומתי עץ או בדיקת עצמים. לכל חלון גלילה משלו והנתונים מתעדכנים לפי הדוח והמודל הנבחרים. לחיצה על תא תחזיות במטריצה הנפרדת פותחת את העצמים שלו בטבלה נפרדת.',
                ),
            ),
            (
                ('Compare candidate depths and follow the final tree', 'Сравните глубины и пройдите по итоговому дереву', 'השוו עומקים ועקבו אחר העץ הסופי'),
                (
                    'In Model comparison, select Tree or Random forest and open Depth and tuning. Each row shows one set of limits and its validation macro-F1. The selected row uses the highest score from all validation predictions combined. The score can differ from the average of the individual folds. New reports show the fold scores too. For example, a selected depth limit of 5 allows up to five splits on a path. The fitted tree may stop earlier if a split cannot improve the separation or would leave too few objects in a child. See the actual depth in Model details.',
                    'В «Сравнении моделей» выберите дерево или лес и откройте «Глубина и подбор». В каждой строке — один набор ограничений и его проверочный macro-F1. Побеждает наибольшая оценка по всем проверочным прогнозам вместе. Она может отличаться от среднего оценок отдельных блоков. Новые отчёты показывают также оценки блоков. Например, выбранный предел 5 разрешает до пяти разбиений на одном пути. Дерево может остановиться раньше, если разбиение не улучшает разделение классов или оставит слишком мало объектов в одной из веток. Фактическая глубина указана в «Деталях модели».',
                    'בהשוואת מודלים בחרו עץ או יער ופתחו עומק וכוונון. בכל שורה מופיעה קבוצת מגבלות אחת וציון macro-F1 בתיקוף. נבחר הציון הגבוה ביותר מכל תחזיות התיקוף יחד. הוא עשוי להיות שונה מממוצע ציוני הקפלים. דוחות חדשים מציגים גם ציוני קפלים. לדוגמה, מגבלה 5 מאפשרת עד חמישה פיצולים במסלול. העץ עשוי לעצור מוקדם יותר אם הפיצול לא ישפר את ההפרדה או ישאיר מעט מדי עצמים בענף. העומק בפועל מופיע בפרטי המודל.',
                ),
            ),
            (
                ('Read the questions and name the models', 'Прочитайте вопросы и дайте моделям имена', 'קראו את השאלות ותנו שמות למודלים'),
                (
                    'Select Tree and open Tree nodes. Start at node 0. For a rule such as Area ≤ 30, a value of 30 follows Yes and a value of 31 follows No. Follow the indicated node numbers until Leaf, where the tree returns the listed class. Older reports show the questions here and the full indented tree under Model details. Use Rename selected model to name each fitted tree or forest. A blank name restores the standard label. The new name appears in the model picker for Review new objects and is suggested for export.',
                    'Выберите дерево и откройте «Узлы дерева». Начните с узла 0. Если правило «Area ≤ 30», значение 30 ведёт по ветке «Да», а 31 — по ветке «Нет». Переходите по номерам узлов до листа, где дерево выдаёт указанный класс. В старых отчётах здесь видны вопросы, а полное дерево с отступами находится в «Деталях модели». Кнопка «Переименовать выбранную модель…» задаёт имя отдельно дереву и лесу. Пустое поле возвращает стандартное имя. Новое имя видно в выборе модели для проверки объектов и предлагается при экспорте.',
                    'בחרו עץ ופתחו צומתי עץ. התחילו בצומת 0. בכלל Area ≤ 30, הערך 30 עובר בענף כן והערך 31 בענף לא. עקבו אחר מספרי הצמתים עד לעלה, שבו העץ מחזיר את המחלקה המוצגת. בדוחות ישנים מופיעות כאן השאלות והעץ המלא מופיע עם הזחה בפרטי המודל. שינוי שם המודל שנבחר מאפשר לתת שם נפרד לעץ וליער. שדה ריק מחזיר את שם ברירת המחדל. השם החדש מופיע בבחירת מודל לבדיקת עצמים ומוצע בייצוא.',
                ),
            ),
            (
                ('Which criterion wins, Gini or entropy?', 'Как выбирается критерий, Gini или энтропия', 'איך נבחר הקריטריון, ג׳יני או אנטרופיה?'),
                (
                    'There are two decisions. Inside one candidate model, the chosen criterion decides which question best separates the objects at a node. Every node of that candidate uses the same criterion. To choose the final settings with K-fold tuning on, SoLoData compares complete candidates by their validation macro-F1. For example, if the best Gini tree scores 0.93 and the best entropy tree scores 0.95 on the same validation folds, the final tree uses entropy. The forest is selected separately. Gini candidates come first in an exact tie. With tuning off, the app uses the fixed Gini setting. Open Model details to see the choice and the best validation score for each criterion.',
                    'Здесь два решения. Внутри одного варианта модели выбранный критерий подсказывает, какой вопрос лучше разделит объекты в узле. Все узлы этого варианта используют один критерий. При включённых K-фолдах SoLoData сравнивает готовые варианты по проверочному macro-F1. Например, если лучшее дерево с Gini получило 0,93, а лучшее дерево с энтропией — 0,95 на тех же фолдах, для финального дерева выбирается энтропия. Для леса выбор делается отдельно. При точном равенстве первым идёт вариант с Gini. Без подбора действует фиксированная настройка Gini. В «Деталях модели» показаны выбранный критерий и лучшие оценки для обоих критериев.',
                    'יש שתי החלטות. בתוך מועמד אחד, הקריטריון שנבחר קובע איזו שאלה מפרידה בצורה הטובה ביותר בין העצמים בצומת. כל הצמתים במועמד משתמשים באותו קריטריון. כשכיוונון עם K קפלים פעיל, SoLoData משווה את המועמדים המלאים לפי macro-F1 בתיקוף. לדוגמה, אם העץ הטוב ביותר עם ג׳יני קיבל 0.93 והעץ הטוב ביותר עם אנטרופיה קיבל 0.95 באותם קפלים, העץ הסופי ישתמש באנטרופיה. היער נבחר בנפרד. בשוויון מדויק מועמדי ג׳יני מופיעים ראשונים. כשהכיוונון כבוי משתמשים בג׳יני הקבוע. פתחו פרטי מודל כדי לראות את הבחירה ואת ציון התיקוף הטוב ביותר לכל קריטריון.',
                ),
            ),
            (
                ('Depth counts questions along a path', 'Глубина — число вопросов по пути', 'עומק הוא מספר השאלות במסלול'),
                (
                    'Depth is the largest number of questions an object can pass through on its way to a leaf. A depth limit of 3 (max_depth) allows at most 3 questions along any path. A branch can end sooner if its objects already share a class or if no split leaves enough examples on both sides. The minimum number of examples in a leaf is min_samples_leaf. A tree with just one leaf has depth 0.',
                    'Глубина — наибольшее число вопросов, на которые объект отвечает по пути к листу. Ограничение глубины 3 (max_depth) допускает до трёх вопросов на каждом пути. Ветвь может закончиться раньше, если в ней остался один класс или ни один порог не оставляет достаточно примеров с каждой стороны. Минимальное число примеров в листе задаёт min_samples_leaf. У дерева из одного листа глубина 0.',
                    'עומק הוא מספר השאלות המרבי שעצם עובר בדרך לעלה. מגבלת עומק 3 (max_depth) מאפשרת עד שלוש שאלות בכל מסלול. ענף יכול להסתיים מוקדם יותר אם נותרה בו מחלקה אחת או אם אין סף שמשאיר מספיק דוגמאות בשני הצדדים. min_samples_leaf קובע את מספר הדוגמאות המזערי בעלה. עומק עץ שמכיל רק עלה אחד הוא 0.',
                ),
            ),
            (
                ('When cross-validation is off', 'Когда кросс-валидация выключена', 'כאשר התיקוף הצולב כבוי'),
                (
                    f'SoLoData fits one decision tree with Gini, depth limit {_TREE_DEPTH} and at least {_TREE_LEAF} objects per leaf. It fits one forest with the requested number of trees, Gini, no preset depth cap and at least {_FOREST_LEAF} samples per leaf. Even without a depth cap, each tree stops splitting where the data or leaf-size limit requires it.',
                    f'SoLoData обучает одно дерево с Gini, ограничением глубины {_TREE_DEPTH} и минимумом {_TREE_LEAF} объекта в листе. Для леса используются выбранное число деревьев, Gini, глубина без заданного предела и минимум {_FOREST_LEAF} примера в листе. Разбиения в каждом дереве прекращаются, когда этого требуют состав объектов и ограничение на размер листа.',
                    f'SoLoData מאמנת עץ החלטה אחד עם ג׳יני, מגבלת עומק {_TREE_DEPTH} ולפחות {_TREE_LEAF} עצמים לעלה. היער מאומן עם מספר העצים שנבחר, ג׳יני, עומק ללא תקרה מוגדרת ולפחות {_FOREST_LEAF} דוגמאות לעלה. כל עץ מפסיק להתפצל כאשר הרכב הנתונים או מגבלת גודל העלה מחייבים זאת.',
                ),
            ),
            (
                ('When K-fold tuning is on', 'Как K-фолды подбирают глубину', 'איך תיקוף K בוחר עומק'),
                (
                    f'The tree tries these pairs of depth limit and minimum leaf size in this order. {_TREE_PAIRS}. SoLoData tries the full list with Gini and again with entropy, for {_CANDIDATES} candidates. Each candidate fits K times using the training partition. Each time a different fold supplies the validation predictions. Those predictions are pooled into one validation macro-F1 per candidate. The highest score wins and an exact tie goes to the first candidate. The selected settings are then fitted on the entire training partition and checked once on the test partition.',
                    f'Для дерева перебираются пары «предел глубины, минимум в листе» в таком порядке. {_TREE_PAIRS}. Программа проходит список сначала с Gini, затем с энтропией. Получается {_CANDIDATES} вариантов. Каждый вариант обучается K раз на обучающей выборке. Каждый раз другая её часть служит для проверки. Программа собирает эти прогнозы вместе и считает по ним один проверочный macro-F1 для варианта. Побеждает наибольшее значение, при точном равенстве — первый вариант в списке. С выбранными настройками дерево обучается на всей обучающей выборке, а затем один раз проверяется на тестовой.',
                    f'לעץ נבדקים זוגות של מגבלת עומק וגודל עלה מזערי בסדר הבא. {_TREE_PAIRS}. SoLoData עוברת על הרשימה עם ג׳יני ואז עם אנטרופיה, בסך הכול {_CANDIDATES} מועמדים. כל מועמד מאומן K פעמים על חלק האימון. בכל פעם קפל אחר משמש לתיקוף. התחזיות נאספות יחד לציון macro-F1 אחד של תיקוף לכל מועמד. הציון הגבוה ביותר זוכה ובשוויון מדויק נבחר הראשון ברשימה. עם ההגדרות שנבחרו מאמנים על כל חלק האימון ובודקים פעם אחת על חלק הבדיקה.',
                ),
            ),
            (
                ('When two candidates tie', 'Когда два варианта набрали одинаковую оценку', 'כאשר לשני מועמדים אותו ציון'),
                (
                    'Suppose entropy with settings (8, 5) and (3, 5) produces exactly the same highest validation score. The app selects (8, 5) because it appears earlier. The fitted tree can still have depth 3. Its actual depth depends on how far useful, allowed splits carry the training objects.',
                    'Допустим, варианты с энтропией (8, 5) и (3, 5) получили в точности одинаковую лучшую оценку. Программа выбирает (8, 5), потому что эта пара раньше в списке. Обученное дерево при этом может иметь глубину 3. Она зависит от того, сколько допустимых разделений дерево смогло сделать на обучающих объектах.',
                    'נניח שהמועמדים עם אנטרופיה (8, 5) ו־(3, 5) קיבלו בדיוק אותו ציון תיקוף מרבי. היישום בוחר (8, 5) כי הוא מופיע קודם. עומק העץ שנבנה עדיין יכול להיות 3. העומק בפועל תלוי בכמה פיצולים מותרים העץ מצא בעצמי האימון.',
                ),
            ),
            (
                ('Why a forest can finish quickly', 'Почему лес может обучиться быстро', 'למה אימון היער יכול להסתיים מהר'),
                (
                    'Each tree in the forest learns from a sample drawn with replacement from the current training rows. A few hundred rows with six numeric features take little work per tree. The forest combines the class probabilities from all its trees. With tuning enabled, each forest candidate uses the number of trees you entered. For example, 8 candidates × 3 folds means 24 forest fits, then one final fit. At 200 trees per fit, this builds 5000 trees across the run, and the final forest contains 200.',
                    'Каждое дерево леса учится на случайной выборке из текущих обучающих строк. При таком отборе одна строка может попасть в выборку несколько раз. Если строк всего несколько сотен и признаков шесть, работы на одно дерево мало. Для прогноза лес объединяет вероятности классов от всех своих деревьев. При подборе каждый вариант использует указанное вами число деревьев. Например, 8 вариантов × 3 фолда дают 24 обучения леса, затем ещё одно финальное. При 200 деревьях на один лес за весь запуск строится 5000 деревьев, а в итоговой модели их 200.',
                    'כל עץ ביער לומד ממדגם של שורות האימון הנוכחיות שנדגם עם החזרה. לכן שורה יכולה להופיע במדגם יותר מפעם אחת. כמה מאות שורות ושש תכונות מספריות מצריכות מעט עבודה לכל עץ. היער משלב את הסתברויות המחלקות של כל העצים. בכיוונון כל מועמד ליער משתמש במספר העצים שהזנתם. לדוגמה, 8 מועמדים × 3 קפלים נותנים 24 אימוני יער ואז אימון סופי נוסף. עם 200 עצים בכל אימון נבנים 5000 עצים לאורך ההרצה, והיער הסופי מכיל 200.',
                ),
            ),
            (
                ('Where to check your run', 'Где проверить свой запуск', 'איפה בודקים את ההרצה'),
                (
                    'Choose a saved evaluation, select Decision tree or Random Forest and open Model details. The depth limit is the chosen setting. The actual depth of the fitted tree or range of depths in the forest describes what grew. New reports also show the number of fitted trees, the number of validation fits and fitting time in seconds. The final fit and validation fits are timed separately. Reading the data, predicting, calculating metrics and saving the model take additional time. Older reports retain the selected settings and the validation scores that were recorded then.',
                    'Выберите сохранённую оценку, затем «Дерево решений» или «Случайный лес» и откройте «Детали модели». Предел глубины — выбранная настройка. Фактическая глубина дерева или диапазон глубин в лесу показывают, что выросло при обучении. Новые отчёты также показывают фактическое число деревьев, число обучений при подборе и время в секундах. Финальное обучение и обучения при подборе измеряются отдельно. Чтение данных, прогнозы, расчёт метрик и сохранение занимают дополнительное время. В старых отчётах доступны выбранные настройки и записанные тогда оценки подбора.',
                    'בחרו הערכה שמורה, בחרו עץ החלטה או יער אקראי ופתחו פרטי מודל. מגבלת העומק היא ההגדרה שנבחרה. העומק בפועל של העץ או טווח העומקים ביער מתארים את מה שנבנה. דוחות חדשים מציגים גם את מספר העצים בפועל, מספר אימוני התיקוף וזמן האימון בשניות. זמן האימון הסופי וזמני אימוני התיקוף נמדדים בנפרד. קריאת נתונים, חיזוי, חישוב מדדים ושמירה נמשכים זמן נוסף. בדוחות ישנים זמינים ההגדרות וציוני הכיוונון שנרשמו אז.',
                ),
            ),
        ),
    ),
    'confusion_matrix': (
        ('How to read the confusion matrix', 'Как читать матрицу ошибок', 'איך קוראים את מטריצת הבלבול'),
        (
            (
                ('Read the row first, then the column', 'Сначала строка, потом столбец', 'קודם שורה, אחר כך עמודה'),
                (
                    'In Model comparison, choose the model above the table. Each test object contributes one count. The row says which class you assigned by hand, and the column says what the selected model predicted. Matching class names on the diagonal mean a correct answer. An off-diagonal cell shows a specific confusion. Here is an example with 21 particles and 26 fibers in the test.',
                    'В «Сравнении моделей» сначала выберите модель над таблицей. Каждый объект теста добавляет единицу в одну ячейку. Строка показывает класс, который вы присвоили вручную, а столбец — прогноз выбранной модели. На диагонали названия классов совпадают, и ответ верный. Ячейка вне диагонали показывает, какие классы перепутаны. В примере в тесте 21 частица и 26 волокон.',
                    'בהשוואת מודלים בחרו תחילה את המודל מעל הטבלה. כל עצם בדיקה מוסיף ספירה אחת לתא אחד. השורה מציינת את המחלקה שקבעתם ידנית והעמודה מציינת את תחזית המודל הנבחר. באלכסון שמות המחלקות תואמים והתחזית נכונה. תא מחוץ לאלכסון מראה אילו מחלקות התבלבלו. בדוגמה יש בבדיקה 21 חלקיקים ו־26 סיבים.',
                ),
            ),
            (
                ('What happened in this example', 'Что произошло в этом примере', 'מה קרה בדוגמה'),
                (
                    'The Most frequent baseline learned that fiber was the more common class in training. It called every test object a fiber. The 21 in the Particle row and Fiber column are 21 missed particles. The 26 on the Fiber diagonal are the 26 correctly predicted fibers. Choose Decision tree or Random Forest to see their own results.',
                    'Базовая модель «Частый класс» определила, что в обучении чаще встречалось волокно, и назвала волокнами все объекты теста. Число 21 в строке «Частица» и столбце «Волокно» означает 21 пропущенную частицу. Число 26 на диагонали — 26 правильно определённых волокон. Выберите дерево или лес, чтобы увидеть их результаты.',
                    'מודל הייחוס ״המחלקה השכיחה״ מצא שסיב היה המחלקה השכיחה באימון. הוא קרא לכל עצם בבדיקה סיב. 21 בשורת החלקיק ובעמודת הסיב מציינים 21 חלקיקים שהוחמצו. 26 באלכסון הסיב מציינים 26 סיבים שסווגו נכון. בחרו עץ החלטה או יער אקראי כדי לראות את התוצאות שלהם.',
                ),
            ),
            (
                ('Recall asks what you found. Precision asks how much to trust a label.', 'Полнота показывает, сколько нашли. Точность — сколько прогнозов подтвердилось.', 'כיסוי שואל כמה נמצא. דיוק שואל כמה תחזיות אושרו.'),
                (
                    'For recall, divide the diagonal count by the row total. All 26 real fibers were found, so fiber recall is 26/26 = 1.000. Particle recall is 0/21 = 0.000. For class precision, divide the diagonal count by the column total. Of the 47 predictions of fiber, 26 were correct, so fiber precision is 26/47 ≈ 0.553. The dash for particle precision means there were zero particle predictions. Recall is undefined if the test has no actual objects of the class.',
                    'Для полноты делите число верных ответов на сумму строки. Найдены все 26 настоящих волокон, поэтому полнота волокна равна 26/26 = 1,000. Для частиц она равна 0/21 = 0,000. Для точности класса делите число верных ответов на сумму столбца. Из 47 прогнозов «волокно» подтвердились 26, поэтому точность волокна равна 26/47 ≈ 0,553. Прочерк у точности частицы означает, что модель ни разу не предсказала частицу. Полнота не определена, если в тесте нет ни одного объекта этого класса.',
                    'לכיסוי מחלקים את המספר באלכסון בסכום השורה. כל 26 הסיבים האמיתיים נמצאו, לכן כיסוי הסיבים הוא 26/26 = 1.000. כיסוי החלקיקים הוא 0/21 = 0.000. לדיוק מחלקה מחלקים את המספר באלכסון בסכום העמודה. מתוך 47 תחזיות ״סיב״, 26 היו נכונות, לכן דיוק הסיבים הוא 26/47 ≈ 0.553. מקף בדיוק החלקיקים מציין אפס תחזיות ״חלקיק״. הכיסוי אינו מוגדר כאשר אין בבדיקה עצם אמיתי מהמחלקה.',
                ),
            ),
            (
                ('How one score summarizes both classes', 'Как одна оценка учитывает оба класса', 'איך ציון אחד מסכם את שתי המחלקות'),
                (
                    'F1 rewards finding a class and making few false alarms. For that class, take twice the number of correct matches and divide by twice that number plus the missed objects and false alarms. In this example, fiber F1 is 52/(52 + 0 + 21) ≈ 0.712, and particle F1 is 0. Macro-F1 gives every class that is present in the test equal weight, so the mean is about 0.356. Compare the same test set across models and inspect the counts for rare classes.',
                    'F1 учитывает и то, сколько объектов класса найдено, и то, сколько лишних объектов модель туда отнесла. Для одного класса удвойте число верных ответов и поделите на это удвоенное число плюс пропуски и ложные срабатывания. В примере F1 волокна равен 52/(52 + 0 + 21) ≈ 0,712, а F1 частицы равен 0. Macro-F1 даёт одинаковый вес каждому классу, который есть в тесте. Получается среднее около 0,356. Сравнивайте модели на одном тесте и проверяйте числа объектов редких классов.',
                    'F1 מתגמל מציאה של עצמי המחלקה ומעט התרעות שווא. עבור מחלקה, מכפילים את מספר ההתאמות הנכונות בשתיים ומחלקים במספר הכפול בתוספת העצמים שהוחמצו והתרעות השווא. בדוגמה F1 של סיב הוא 52/(52 + 0 + 21) ≈ 0.712 ושל חלקיק הוא 0. Macro-F1 נותן משקל שווה לכל מחלקה שמופיעה בבדיקה, ולכן הממוצע הוא כ־0.356. השוו מודלים על אותה בדיקה ובדקו את מספרי העצמים במחלקות נדירות.',
                ),
            ),
            (
                ('Inspect the objects behind a count', 'Как увидеть объекты за числом', 'איך רואים את העצמים שמאחורי הספירה'),
                (
                    'Click a matrix cell to open the objects it counts. For example, click 21 to inspect the particles called fibers. Row percentages shows how each actual class was distributed among predictions. In this example, 21 of 21 particles called fiber becomes 100% in that cell. The Per-class recall chart shows the diagonal share for each class and n shows how many actual test objects support it.',
                    'Нажмите ячейку матрицы, чтобы открыть список объектов за этим числом. Например, ячейка 21 откроет частицы, названные волокнами. «Проценты по строкам» показывают, как прогнозы распределились внутри каждого ручного класса. В примере все 21 частица названы волокнами, поэтому в этой ячейке будет 100%. На графике «Полнота по классам» показана доля диагонали в каждой строке, а n — число тестовых объектов этого ручного класса.',
                    'לחצו על תא במטריצה כדי לפתוח את רשימת העצמים שהוא סופר. לדוגמה, לחיצה על 21 תפתח את החלקיקים שסווגו כסיבים. אחוזים לפי שורה מראים איך התחזיות מתחלקות בתוך כל מחלקה ידנית. בדוגמה 21 מתוך 21 חלקיקים שנקראו סיבים יופיעו כ־100% בתא הזה. תרשים הכיסוי לפי מחלקה מציג את החלק היחסי של האלכסון בכל שורה, ו־n הוא מספר עצמי הבדיקה של אותה מחלקה ידנית.',
                ),
            ),
        ),
    ),
    'permutation_importance': (
        ('Permutation importance of features', 'Перестановочная важность признаков', 'חשיבות תכונות לפי ערבוב'),
        (
            (
                ('Imagine mixing up one column', 'Представьте, что перепутали один столбец', 'דמיינו ערבוב של עמודה אחת'),
                (
                    'Suppose the trained forest scores 0.80 macro-F1 on the test objects. Now redistribute the Area values at random among those same objects. Leave their reviewed classes and all other columns in place. Ask the same fitted forest for predictions again. If macro-F1 falls to 0.68, the drop for this shuffle is 0.12. This checks how much the forest relied on that column for these predictions.',
                    'Допустим, обученный лес получил на тесте macro-F1 0,80. Теперь случайно поменяем значения площади Area местами между теми же объектами. Ручные классы и остальные столбцы остаются на своих местах. Тот же обученный лес снова выдаёт прогнозы. Если macro-F1 упал до 0,68, снижение в этой попытке равно 0,12. Так мы проверяем, насколько лес опирался на этот столбец в этих прогнозах.',
                    'נניח שהיער המאומן קיבל macro-F1 של 0.80 על עצמי הבדיקה. כעת מערבבים באקראי את ערכי השטח Area בין אותם עצמים. המחלקות הידניות וכל שאר העמודות נשארות במקומן. מבקשים תחזיות שוב מאותו יער מאומן. אם macro-F1 יורד ל־0.68, הירידה בערבוב הזה היא 0.12. כך בודקים עד כמה היער הסתמך על העמודה בתחזיות האלו.',
                ),
            ),
            (
                ('Read the bar and its whiskers', 'Как читать полосу и отметки разброса', 'איך קוראים את העמודה ואת סימוני הפיזור'),
                (
                    'SoLoData repeats the shuffle five times per feature on the same test objects. The bar shows the average drop. The whiskers span one standard deviation on either side of the mean and describe variation between the five shuffles. A bar pointing to the left means the score improved on average when the column was shuffled. That can happen by chance on a small test.',
                    'SoLoData пять раз перемешивает каждый признак на одних и тех же тестовых объектах. Полоса показывает среднее снижение. Отметки по краям охватывают по одному стандартному отклонению от среднего и показывают разброс между пятью перемешиваниями. Полоса влево означает, что после перемешивания оценка в среднем выросла. На маленьком тесте такое может случиться случайно.',
                    'SoLoData חוזרת על הערבוב חמש פעמים לכל תכונה באותם עצמי בדיקה. העמודה מציגה את הירידה הממוצעת. סימוני הפיזור משתרעים סטיית תקן אחת לכל צד של הממוצע ומראים שונות בין חמשת הערבובים. עמודה שמאלה פירושה שהציון עלה בממוצע אחרי הערבוב. בבדיקה קטנה זה יכול לקרות במקרה.',
                ),
            ),
            (
                ('What a small drop can mean', 'Что может означать небольшой эффект', 'מה יכולה להעיד ירידה קטנה'),
                (
                    'If two features carry similar information, the untouched column can still help when the other one is shuffled. So a small drop may reflect redundancy. This chart describes the forest from the current saved evaluation and its test set. Use separate TIFFs or experiments to check whether the pattern repeats.',
                    'Если два признака несут похожую информацию, второй столбец может помочь даже после перемешивания первого. Поэтому небольшой эффект иногда объясняется сходством признаков. График относится к лесу из открытой сохранённой оценки и к её тестовой выборке. Чтобы проверить, повторяется ли результат, нужны отдельные TIFF или эксперименты.',
                    'אם שתי תכונות נושאות מידע דומה, העמודה שנותרה במקומה עדיין יכולה לעזור אחרי ערבוב השנייה. לכן ירידה קטנה יכולה לנבוע ממידע חופף. התרשים מתאר את היער מההערכה השמורה שנפתחה ואת קבוצת הבדיקה שלה. השתמשו בקובצי TIFF או בניסויים נפרדים כדי לבדוק אם הדפוס חוזר.',
                ),
            ),
        ),
    ),
    'evaluation_gallery': (
        ('Split gallery', 'Галерея разбиения', 'גלריית החלוקה'),
        (
            (
                ('Which objects went where?', 'Какие объекты куда попали', 'לאיזה חלק הוקצו העצמים?'),
                (
                    'Open Split gallery from the split plan or model comparison. Choose training, held-out test, or the validation part of a numbered fold. Training displays the manual class recorded in the snapshot. For the final test, the prediction and the manual class are separate. Reveal the manual class when you want to compare them. A validation fold shows membership for tuning. The final model has been fitted on all training objects, including those validation rows.',
                    'Откройте «Галерею разбиения» из плана или сравнения моделей. Выберите обучение, отложенный тест или проверочную часть фолда с нужным номером. В обучении виден ручной класс из снимка данных. В тесте прогноз и ручной класс показаны отдельно. Откройте ручной класс, когда хотите сверить их. Вкладка фолда показывает, какие объекты служили для подбора. Финальная модель училась на всех обучающих объектах, включая эти строки.',
                    'פתחו גלריית חלוקה מתוכנית החלוקה או מהשוואת המודלים. בחרו אימון, בדיקה שמורה או חלק התיקוף של קפל ממוספר. באימון מוצגת המחלקה הידנית מתמונת הנתונים. בבדיקה התחזית והמחלקה הידנית נפרדות. חשפו את המחלקה הידנית כדי להשוות. תצוגת קפל מראה אילו עצמים שימשו לכיוונון. המודל הסופי אומן על כל עצמי האימון, לרבות שורות התיקוף האלה.',
                ),
            ),
            (
                ('When does the program use a class label?', 'Когда используется ручной класс', 'מתי היישום משתמש במחלקה הידנית?'),
                (
                    'For fitting, training rows supply both features and manual classes. To predict a validation or test object, the fitted model receives its numeric features. The program then compares the prediction with the manual class to score it. The split planner also uses class counts to balance the parts. Final test labels are kept out of fitting and tuning.',
                    'При обучении программа берёт признаки и ручные классы обучающих объектов. Для прогноза на валидации или тесте обученная модель получает числовые признаки объекта. Затем программа сравнивает прогноз с ручным классом и считает оценку. Планировщик также использует числа по классам для балансировки частей. Ручные классы финального теста остаются за пределами обучения и подбора.',
                    'באימון היישום מקבל את התכונות והמחלקות הידניות של עצמי האימון. כדי לחזות עצם בתיקוף או בבדיקה המודל המאומן מקבל את התכונות המספריות שלו. לאחר מכן היישום משווה את התחזית למחלקה הידנית ומחשב ציון. מתכנן החלוקה משתמש גם בספירות לפי מחלקה כדי לאזן את החלקים. המחלקות הידניות של הבדיקה הסופית נשמרות מחוץ לאימון ולכיוונון.',
                ),
            ),
            (
                ('Where the images come from', 'Откуда берутся изображения', 'מה מקור התמונות?'),
                (
                    'Select an object to see its saved binary mask below the details. Use the ← and → buttons or keyboard arrows to move through the filtered list. The keyboard arrows control the text cursor or selector while search or a selector has focus. A saved review crop is shown if only that image is available. For a training table exported to Excel or CSV, the gallery uses its measurement reference, tile, object ID and feature values to locate the original mask in this project. A row without a verified match still shows its details. Drag the dividers to resize the list, text and image. The window size and divider positions are remembered.',
                    'Выберите объект, чтобы увидеть его бинарную маску под описанием. Кнопки и клавиши ← и → переходят между объектами с учётом фильтров. Когда фокус в поле поиска или раскрывающемся списке, клавиши управляют этим полем. Если доступен только сохранённый контрольный фрагмент, галерея покажет его. Для экспортированного Excel или CSV галерея сверяет ссылку на версию измерений, тайл, ID объекта и признаки, чтобы открыть исходную маску из проекта. Если соответствие не подтверждено, доступны сведения о строке. Перетаскивайте разделители между списком, текстом и изображением. Размер окна и положение разделителей запоминаются.',
                    'בחרו עצם כדי לראות את המסכה הבינארית השמורה מתחת לפרטים. לחצני ← ו־→ או מקשי החצים עוברים בין העצמים ברשימה המסוננת. כשהמיקוד בחיפוש או בבורר, מקשי החצים שולטים בשדה זה. אם נשמר רק חיתוך ביקורת, הוא יוצג במקום המסכה. בטבלת Excel או CSV שיוצאה, הגלריה בודקת את ההפניה לגרסת המדידה, האריח, מזהה העצם וערכי התכונות כדי לפתוח את המסכה המקורית בפרויקט. כשאין התאמה מאומתת, פרטי השורה עדיין מוצגים. גררו את המפרידים כדי לשנות את גודל הרשימה, הטקסט והתמונה. גודל החלון ומיקומי המפרידים נשמרים.',
                ),
            ),
        ),
    ),
    'object_prediction_review': (
        ('Review predictions on new objects', 'Проверка прогнозов на новых объектах', 'בדיקת תחזיות על עצמים חדשים'),
        (
            (
                ('Inspect masks in a matrix cell', 'Просмотрите маски из ячейки матрицы', 'בדקו מסכות בתא במטריצה'),
                (
                    'Click a cell with a count to filter the mask list to its reference class and prediction. Inspect the images and both classes, then change or clear the decision as needed. If a correction changes the reference class, the mask moves to the new cell immediately. Show all masks clears the filter.',
                    'Нажмите на ячейку с числом, чтобы оставить в списке маски с этой парой правильного класса и прогноза. Посмотрите изображения и оба класса, затем при необходимости исправьте или снимите отметку. Если правильный класс изменился, маска сразу перейдёт в другую ячейку. «Показать все маски» сбрасывает фильтр.',
                    'לחצו על תא עם מספר כדי לסנן את המסכות לפי מחלקת הייחוס והתחזית. בדקו את התמונות ואת שתי המחלקות ועדכנו או נקו את ההחלטה לפי הצורך. אם מחלקת הייחוס משתנה, המסכה עוברת מיד לתא אחר. הצגת כל המסכות מנקה את הסינון.',
                ),
            ),
            (
                ('Prepare and run the review set', 'Как создать проверочный набор', 'איך מכינים קבוצת בדיקה?'),
                (
                    'Measure the masks on the chosen tiles and leave the manual classes empty. In Model training, open Review new objects. Pick a saved decision tree or random forest from this project, the measurement dataset and the tiles. Predict on checked tiles takes a snapshot of the measured objects without manual classes. The model can predict only the classes it learned. If a particle-and-fiber model sees a third type, review the forced prediction as an error.',
                    'Измерьте маски на нужных тайлах и оставьте ручные классы пустыми. В «Обучении модели» откройте «Проверка новых объектов…». Выберите сохранённое дерево или лес из этого проекта, набор измерений и тайлы. «Получить прогнозы на отмеченных тайлах» сохраняет снимок измеренных объектов без ручного класса. Модель выбирает из классов, на которых училась. Если модели частиц и волокон попался объект третьего типа, пометьте такой прогноз как ошибку.',
                    'מדדו את המסכות באריחים שנבחרו והשאירו את המחלקות הידניות ריקות. באימון מודל פתחו בדיקת עצמים חדשים. בחרו עץ החלטה או יער אקראי שמור מהפרויקט, מערך מדידות ואריחים. חיזוי באריחים המסומנים שומר תמונת מצב של העצמים המדודים ללא מחלקה ידנית. המודל בוחר רק מבין המחלקות שלמד. אם מודל לחלקיקים וסיבים רואה סוג שלישי, סמנו את התחזית הכפויה כשגויה.',
                ),
            ),
            (
                ('Make and reopen decisions', 'Как поставить отметку и вернуться к проверке', 'איך מסמנים וחוזרים לבדיקה?'),
                (
                    'Inspect the saved mask and intensity crop alongside the predicted name. Correct confirms the prediction as the reference class. With Incorrect, choose the correct class from the catalog, including classes the model did not learn. Cancel to leave the previous decision in place. Clear decision removes the mark and its class. Reopen your work from Saved prediction reviews. The decisions and reference classes are stored separately from training labels.',
                    'Смотрите сохранённую маску, фрагмент яркости и прогноз модели. «Верно» подтверждает прогноз и принимает этот класс за эталон. После нажатия «Ошибка» выберите правильный класс из каталога. Можно выбрать и класс, на котором модель не обучалась. Отмена оставляет прежнюю отметку. «Снять отметку» удаляет решение и его класс. Вернуться к работе можно через «Сохранённые проверки прогнозов». Отметки и эталонные классы хранятся отдельно от обучающей разметки.',
                    'בדקו את המסכה השמורה ואת חיתוך העוצמה לצד תחזית המודל. לחיצה על נכון מאשרת את התחזית כמחלקת ייחוס. בלחיצה על שגוי בחרו את המחלקה הנכונה מהקטלוג, כולל מחלקות שהמודל לא למד. ביטול שומר את ההחלטה הקודמת. ניקוי החלטה מסיר את הסימון ואת המחלקה שלו. אפשר לחזור לעבודה דרך בדיקות תחזית שמורות. ההחלטות ומחלקות הייחוס נשמרות בנפרד מתוויות האימון.',
                ),
            ),
            (
                ('Read the numbers in context', 'Что означают числа проверки', 'איך מפרשים את המספרים?'),
                (
                    'If you reviewed 10 of 30 masks and accepted 8, the summary shows 8 of 10 confirmed and 20 pending. In Confusion matrix, rows are the reference classes and columns are model predictions. If a fiber was predicted as a particle, it adds one to the Fiber row and Particle column. Confirmations fall on the diagonal. The matrix counts masks with a reference class. Old errors without one remain in the summary. Reopen them and click Incorrect again to fill in the class. The matrix covers reviewed masks that were already measured, so missed masks are outside its scope.',
                    'Если вы проверили 10 из 30 масок и подтвердили 8, в сводке будет 8 из 10 подтверждённых и 20 без отметки. В «Матрице ошибок» строки — эталонные классы, столбцы — прогнозы модели. Если модель назвала волокно частицей, единица добавится в строку «Волокно» и столбец «Частица». Подтверждённые ответы попадают на диагональ. Матрица учитывает маски с эталонным классом. Старые ошибки без класса остаются в сводке. Откройте их и снова нажмите «Ошибка», чтобы указать класс. Матрица охватывает уже измеренные и проверенные маски. Пропущенные маски в неё не входят.',
                    'אם בדקתם 10 מתוך 30 מסכות ואישרתם 8, בסיכום יופיעו 8 מתוך 10 מאושרות ו־20 ממתינות. במטריצת הבלבול השורות הן מחלקות הייחוס והעמודות הן תחזיות המודל. סיב שסווג כחלקיק מוסיף אחד לשורת סיב ולעמודת חלקיק. אישורים מופיעים באלכסון. המטריצה סופרת מסכות עם מחלקת ייחוס. שגיאות ישנות ללא מחלקת ייחוס נשארות בסיכום. פתחו אותן ולחצו שוב על שגוי כדי לבחור מחלקה. המטריצה כוללת מסכות שכבר נמדדו ונבדקו, ולכן מסכות שהוחמצו אינן נכללות.',
                ),
            ),
        ),
    ),
}


def install(topics, guided, related, translate):
    """Register separately searchable lessons and their navigation links."""
    for key, (title, sections) in _TOPICS.items():
        topics[key] = dict(title=translate(*title), paragraphs=(), parameters=())
        guided[key] = tuple((translate(*heading), translate(*paragraph)) for heading, paragraph in sections)

    particle = translate('Particle', 'Частица', 'חלקיק')
    fiber = translate('Fiber', 'Волокно', 'סיב')
    topics['confusion_matrix']['example_table'] = (
        (translate('Reviewed class', 'Ручной класс', 'מחלקה ידנית'),
         translate('Predicted particle', 'Прогноз «Частица»', 'תחזית חלקיק'),
         translate('Predicted fiber', 'Прогноз «Волокно»', 'תחזית סיב')),
        ((particle, '0', '21'), (fiber, '0', '26')),
    )
    related['model_evaluation'] += ('model_fit', 'confusion_matrix', 'evaluation_gallery', 'object_prediction_review')
    related['training_charts'] += ('tree_impurity', 'confusion_matrix', 'permutation_importance')
    related['tree_impurity'] = ('training_charts', 'model_fit')
    related['model_fit'] = ('model_evaluation', 'tree_impurity', 'confusion_matrix')
    related['confusion_matrix'] = ('model_evaluation', 'training_charts', 'permutation_importance')
    related['permutation_importance'] = ('training_charts', 'confusion_matrix')
    related['evaluation_gallery'] = ('model_evaluation', 'confusion_matrix', 'object_prediction_review')
    related['object_prediction_review'] = ('model_evaluation', 'evaluation_gallery', 'confusion_matrix')
