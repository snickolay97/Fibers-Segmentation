"""Localized captions for the model evaluation charts."""

from .i18n import register_translations


_TEXT = {
    'Data charts…': ('Графики данных…', 'תרשימי נתונים…'),
    'Performance charts…': ('Графики качества…', 'תרשימי ביצועים…'),
    'Help for this chart': ('Справка по этому графику', 'עזרה לתרשים זה'),
    'Class counts': ('Число объектов по классам', 'מספר עצמים לפי מחלקה'),
    'Train and test counts': ('Классы в обучении и тесте', 'מחלקות באימון ובבדיקה'),
    'Features by class': ('Признаки по классам', 'תכונות לפי מחלקה'),
    'Impurity criteria': ('Критерии информативности', 'מדדי אי־טוהר'),
    'Per-class recall': ('Полнота по классам', 'כיסוי לפי מחלקה'),
    'Permutation importance': ('Перестановочная важность', 'חשיבות לפי ערבוב'),
    'Reviewed objects: {count}. Pearson r measures linear association. A dash marks an undefined coefficient.': (
        'Объектов с ручным классом — {count}. Корреляция Пирсона r измеряет линейную связь. Прочерк обозначает неопределённый коэффициент.',
        'מספר העצמים שסווגו ידנית הוא {count}. המתאם r של פירסון מודד קשר ליניארי. מקף מציין מקדם שאינו מוגדר.'),
    'Counts include all reviewed objects in the preview. A zero means the class is absent.': (
        'Включены все объекты предпросмотра с ручной меткой. Ноль означает отсутствие класса.',
        'הספירות כוללות את כל העצמים שסווגו ידנית בתצוגה המקדימה. אפס מציין שמחלקה חסרה.'),
    'Blue shows training counts and orange shows test counts.': (
        'Синим показано обучение, оранжевым — тест.',
        'כחול מציין את מספר העצמים באימון וכתום את מספרם בבדיקה.'),
    'No valid split is available. See Split plan for the reason.': (
        'Допустимого разбиения нет. Причина указана в плане разбиения.',
        'אין חלוקה תקינה. הסיבה מופיעה בתוכנית החלוקה.'),
    'Feature histograms use the same bin edges for all classes in the selected group.': (
        'На гистограмме признака границы интервалов общие для всех классов выбранной группы.',
        'ההיסטוגרמות משתמשות באותם גבולות תאים לכל המחלקות בקבוצה שנבחרה.'),
    'Imagine a group of 10 objects. At p = 0.2 there are 2 particles and 8 fibers. The curves show three ways to describe the class mix.': (
        'Представьте группу из 10 объектов. При p = 0,2 в ней 2 частицы и 8 волокон. Три кривые по-разному описывают, насколько смешаны классы.',
        'דמיינו קבוצה של 10 עצמים. כאשר p = 0.2 יש בה 2 חלקיקים ו־8 סיבים. שלוש העקומות מתארות בדרכים שונות עד כמה המחלקות מעורבבות.'),
    'Higher macro-F1 is better. The displayed test score averages F1 across the classes present in the test set.': (
        'Чем выше macro-F1, тем лучше. На графике усреднены F1 по классам, представленным в тесте.',
        'ערך macro-F1 גבוה יותר עדיף. הציון בתרשים הוא ממוצע F1 על פני המחלקות שמופיעות בבדיקה.'),
    'Recall is the fraction of correctly predicted objects within each true class. n is the test support.': (
        'Полнота — доля верных прогнозов среди объектов данного ручного класса. n — число таких объектов в тесте.',
        'כיסוי הוא שיעור התחזיות הנכונות מתוך העצמים במחלקה האמיתית. n הוא מספר העצמים מאותה מחלקה בבדיקה.'),
    'Random Forest on the test set. Bars show mean macro-F1 decrease after shuffling a feature, with ±1 standard deviation over shuffles.': (
        'Случайный лес на тесте. Показано среднее снижение macro-F1 после перемешивания признака и ±1 стандартное отклонение по перестановкам.',
        'יער אקראי בחלק הבדיקה. העמודות מציגות ירידה ממוצעת ב־macro-F1 לאחר ערבוב תכונה וסטיית תקן אחת לכל כיוון על פני הערבובים.'),
    'No test scores are available for this evaluation.': (
        'Для этой оценки нет тестовых метрик.', 'אין ציוני בדיקה להערכה זו.'),
    'Permutation importance was not recorded for this evaluation.': (
        'В этой оценке перестановочная важность не сохранена.', 'חשיבות לפי ערבוב לא נשמרה בהערכה זו.'),
}

register_translations({key: values[0] for key, values in _TEXT.items()},
                      hebrew={key: values[1] for key, values in _TEXT.items()})
