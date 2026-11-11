"""Choose reviewed mask classes and use saved pixel models on a native tile."""

from html import escape
from pathlib import Path

from src.default_settings import MODEL_DEFAULTS
from src.object_classes import OBJECT_CLASS_CATALOG
from .i18n import register_translations, tr
from .input_safety import install_parameter_wheel_guard
from .model_evaluation import FOREST_TREE_COUNT_RANGE
from .model_evaluation_ui import _class_name
from .qt import QtCore, QtGui, QtWidgets


_TEXT = {
    'Pixel segmentation…': ('Сегментация по пикселям…', 'פילוח לפי פיקסלים…'),
    'Train pixel model': ('Обучить модель пикселей', 'אימון מודל פיקסלים'),
    'Apply pixel model': ('Применить модель пикселей', 'החלת מודל פיקסלים'),
    'Apply to selected tile': ('Применить к выбранному тайлу', 'החלה על האריח שנבחר'),
    'Number of trees': ('Число деревьев', 'מספר עצים'),
    'Native masks with reviewed classes are the training input. The Excel features are used on the Model training page.': (
        'Для обучения нужны native-маски с проверенными классами. Признаки из Excel используются на странице «Обучение модели».',
        'קלט האימון הוא מסכות מקור עם מחלקות שעברו סקירה. תכונות Excel משמשות בדף אימון המודל.'),
    'Choose measurement datasets and foreground classes': (
        'Выберите наборы измерений и классы переднего плана',
        'בחרו מערכי מדידות ומחלקות קדמה'),
    'Current tile: {tile}': ('Текущий тайл: {tile}', 'אריח נוכחי: {tile}'),
    'Select an active native tile before applying a pixel model.': (
        'Выберите активный native-тайл перед применением модели пикселей.',
        'בחרו אריח מקור פעיל לפני החלת מודל הפיקסלים.'),
    'Select a saved pixel model': ('Выберите сохранённую модель пикселей', 'בחרו מודל פיקסלים שמור'),
    'Pixel model saved: {path}': ('Модель пикселей сохранена: {path}', 'מודל הפיקסלים נשמר: {path}'),
    'Pixel class map saved: {path}': ('Карта классов пикселей сохранена: {path}', 'מפת מחלקות הפיקסלים נשמרה: {path}'),
    'Pixel segmentation overlay': ('Наложение классов пикселей', 'שכבת פילוח פיקסלים'),
}
register_translations({key: value[0] for key, value in _TEXT.items()},
                      hebrew={key: value[1] for key, value in _TEXT.items()})


def overlay_legend(colors, parent):
    parts = []
    for label, rgb in colors.items():
        color = QtGui.QColor(*rgb).name()
        parts.append(f'<span style="color:{color}">■</span> {escape(_class_name(label))}')
    legend = QtWidgets.QLabel(' &nbsp; '.join(parts), parent)
    legend.setTextFormat(QtCore.Qt.TextFormat.RichText)
    legend.setWordWrap(True)
    return legend


class PixelSegmentationDialog(QtWidgets.QDialog):
    """Return a worker action for a training run or a prediction."""

    def __init__(self, project, dataset, record, parent=None):
        super().__init__(parent)
        self.request = None
        self.setWindowTitle(tr('Pixel segmentation…'))
        self.resize(640, 510)
        layout = QtWidgets.QVBoxLayout(self)
        hint = QtWidgets.QLabel(tr('Native masks with reviewed classes are the training input. The Excel features are used on the Model training page.'))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        tabs = QtWidgets.QTabWidget()
        layout.addWidget(tabs, 1)
        train_page = QtWidgets.QWidget()
        tabs.addTab(train_page, tr('Train pixel model'))
        train_layout = QtWidgets.QVBoxLayout(train_page)
        train_layout.addWidget(QtWidgets.QLabel(tr('Choose measurement datasets and foreground classes')))
        self.datasets = QtWidgets.QListWidget()
        train_layout.addWidget(self.datasets, 1)
        current_id = dataset['id'] if dataset else None
        for source in project.datasets:
            if not source.get('results_current'):
                continue
            item = QtWidgets.QListWidgetItem(source['name'])
            item.setData(QtCore.Qt.ItemDataRole.UserRole, source['id'])
            item.setCheckState(QtCore.Qt.CheckState.Checked if source['id'] == current_id
                               else QtCore.Qt.CheckState.Unchecked)
            self.datasets.addItem(item)
        classes = QtWidgets.QGridLayout()
        self.classes = {}
        for index, entry in enumerate(OBJECT_CLASS_CATALOG):
            label = entry['id']
            check = QtWidgets.QCheckBox(_class_name(label))
            check.setChecked(label in (0, 1))
            classes.addWidget(check, index // 2, index % 2)
            self.classes[label] = check
        train_layout.addLayout(classes)
        self.trees = QtWidgets.QSpinBox()
        self.trees.setRange(*FOREST_TREE_COUNT_RANGE)
        self.trees.setValue(MODEL_DEFAULTS['forest_tree_count'])
        controls = QtWidgets.QFormLayout()
        controls.addRow(tr('Number of trees'), self.trees)
        train_layout.addLayout(controls)
        self.train = QtWidgets.QPushButton(tr('Train pixel model'))
        self.train.clicked.connect(self._train)
        train_layout.addWidget(self.train)
        self.datasets.itemChanged.connect(self._validate)
        for check in self.classes.values():
            check.toggled.connect(self._validate)
        self._validate()

        apply_page = QtWidgets.QWidget()
        tabs.addTab(apply_page, tr('Apply pixel model'))
        apply_layout = QtWidgets.QVBoxLayout(apply_page)
        self.model = QtWidgets.QComboBox()
        apply_layout.addWidget(QtWidgets.QLabel(tr('Select a saved pixel model')))
        apply_layout.addWidget(self.model)
        root = Path(project.workspace) / 'pixel_segmentation'
        for artifact in sorted(root.glob('Model_*/model.joblib'), reverse=True):
            self.model.addItem(artifact.parent.name, str(artifact))
        self.tile = record if dataset and record and record.get('native_filename') and not record.get('excluded') else None
        apply_layout.addWidget(QtWidgets.QLabel(tr('Current tile: {tile}', tile=self.tile['id']) if self.tile else
                                              tr('Select an active native tile before applying a pixel model.')))
        apply = QtWidgets.QPushButton(tr('Apply to selected tile'))
        apply.setEnabled(bool(self.tile and self.model.count()))
        apply.clicked.connect(lambda: self._submit('apply_pixel_segmentation', dataset_id=current_id,
                                                   tile_id=self.tile['id'], model_path=self.model.currentData()))
        apply_layout.addWidget(apply)
        apply_layout.addStretch()
        actions = QtWidgets.QHBoxLayout()
        guide = QtWidgets.QPushButton('?')
        guide.setAccessibleName(tr('Pixel segmentation…'))
        guide.clicked.connect(self._show_help)
        actions.addWidget(guide)
        actions.addStretch()
        cancel = QtWidgets.QPushButton(tr('Close'))
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        layout.addLayout(actions)
        help_shortcut = QtGui.QShortcut(QtGui.QKeySequence('F1'), self)
        help_shortcut.activated.connect(self._show_help)
        self._help_center = None
        install_parameter_wheel_guard(self)

    def _selected_datasets(self):
        return [item.data(QtCore.Qt.ItemDataRole.UserRole)
                for index in range(self.datasets.count()) if
                (item := self.datasets.item(index)).checkState() == QtCore.Qt.CheckState.Checked]

    def _validate(self, *_):
        self.train.setEnabled(bool(self._selected_datasets()) and any(check.isChecked() for check in self.classes.values()))

    def _train(self):
        self._submit('train_pixel_segmentation', dataset_ids=self._selected_datasets(),
                     class_ids=[label for label, check in self.classes.items() if check.isChecked()],
                     forest_tree_count=self.trees.value(), seed=42)

    def _submit(self, action, **options):
        self.request = action, options
        self.accept()

    def _show_help(self):
        from .help_center import HelpCenter
        if self._help_center is None:
            self._help_center = HelpCenter(parent=self)
        self._help_center.open_topic('pixel_segmentation')
