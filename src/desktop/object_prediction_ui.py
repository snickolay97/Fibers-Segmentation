"""Launch an unlabelled object prediction and inspect the saved audit."""

from collections import Counter
from pathlib import Path

from src.object_classes import OBJECT_CLASS_CATALOG
from .i18n import register_translations, tr
from .input_safety import install_parameter_wheel_guard
from .model_evaluation_ui import _class_name, _fill, _table
from .model_names import model_display_name
from .object_labels import object_key
from .qt import QtCore, QtGui, QtWidgets
from .widgets import ImageViewer


_TEXT = {
    'Review new objects…': ('Проверка новых объектов…', 'בדיקת עצמים חדשים…'),
    'Run the selected saved model on measured objects with no manual class. Check the tiles to include.': (
        'Примените выбранную сохранённую модель к измеренным объектам без ручного класса. Отметьте нужные тайлы.',
        'הפעילו את המודל השמור שנבחר על עצמים מדודים ללא מחלקה ידנית. סמנו את האריחים שייכללו.'),
    'Saved model': ('Сохранённая модель', 'מודל שמור'),
    'Predict on checked tiles': ('Получить прогнозы на отмеченных тайлах', 'חיזוי באריחים המסומנים'),
    'Saved prediction reviews': ('Сохранённые проверки прогнозов', 'בדיקות תחזית שמורות'),
    'Open review': ('Открыть проверку', 'פתיחת בדיקה'),
    'No saved tree or forest is available. Train a model and save an evaluation first.': (
        'Сохранённого дерева или леса пока нет. Сначала обучите модель и сохраните оценку.',
        'אין עדיין עץ או יער שמור. תחילה אמנו מודל ושמרו הערכה.'),
    'No active tiles with saved measurements': ('Нет активных тайлов с сохранёнными измерениями', 'אין אריחים פעילים עם מדידות שמורות'),
    'Select all tiles': ('Выбрать все тайлы', 'בחירת כל האריחים'),
    'Clear tile selection': ('Снять выделение тайлов', 'ניקוי בחירת האריחים'),
    'Exact binary mask': ('Точная бинарная маска', 'מסכה בינארית מדויקת'),
    'Saved intensity crop': ('Сохранённый фрагмент яркости', 'חיתוך עוצמה שמור'),
    'Predicted class': ('Прогноз модели', 'מחלקה חזויה'),
    'Correct prediction': ('Верно', 'נכון'),
    'Incorrect prediction': ('Ошибка', 'שגוי'),
    'Choose the correct class for this mask.': (
        'Выберите правильный класс этой маски.', 'בחרו את המחלקה הנכונה למסכה הזו.'),
    'Correct class': ('Правильный класс', 'המחלקה הנכונה'),
    'Review summary': ('Сводка проверки', 'סיכום הבדיקה'),
    'Rows are reviewed classes. Columns are model predictions. Masks counted: {count}.': (
        'Строки — правильные классы. Столбцы — прогнозы модели. Масок в матрице: {count}.',
        'השורות הן המחלקות הנכונות. העמודות הן תחזיות המודל. מספר המסכות במטריצה: {count}.'),
    'Old errors without a correct class: {count}. Click Incorrect again on those masks to include them.': (
        'Старых ошибок без правильного класса: {count}. Чтобы добавить их в матрицу, снова нажмите «Ошибка» у этих масок.',
        'שגיאות ישנות ללא מחלקה נכונה: {count}. לחצו שוב על שגוי במסכות האלה כדי לכלול אותן.'),
    'Correct class not recorded': ('Правильный класс не указан', 'המחלקה הנכונה לא תועדה'),
    'Click a nonzero count to inspect its masks.': (
        'Нажмите на ячейку с ненулевым числом, чтобы просмотреть её маски.', 'לחצו על ספירה שאינה אפס כדי לבדוק את המסכות שלה.'),
    'Reference {actual} → prediction {predicted} · masks: {count}': (
        'Правильный класс {actual} → прогноз {predicted} · масок: {count}',
        'מחלקת ייחוס {actual} ← תחזית {predicted} · מסכות: {count}'),
    'Show all masks': ('Показать все маски', 'הצגת כל המסכות'),
    'Clear decision': ('Снять отметку', 'ניקוי החלטה'),
    'Pending': ('Без отметки', 'ממתין'),
    'Reviewed {reviewed} of {total}. Confirmed {correct} of {reviewed} reviewed ({percent}).': (
        'Проверено {reviewed} из {total}. Подтверждено {correct} из {reviewed} проверенных ({percent}).',
        'נבדקו {reviewed} מתוך {total}. אושרו {correct} מתוך {reviewed} שנבדקו ({percent}).'),
    '{model} · classes available to this model — {classes}': (
        '{model} · модель выбирает из классов {classes}', '{model} · המחלקות הזמינות למודל הן {classes}'),
    'This source was used in the original training or test.': (
        'Этот исходник уже использовался при обучении или в исходном тесте.', 'מקור זה שימש באימון או בבדיקה המקוריים.'),
    'Independence from the training sources could not be verified.': (
        'Независимость от обучающих исходников не подтверждена.', 'לא ניתן לאמת עצמאות ממקורות האימון.'),
    'This TIFF differs from the TIFFs in the saved evaluation. Check that the experiments are independent.': (
        'Этот TIFF отличается от TIFF в сохранённой оценке. Убедитесь, что эксперименты независимы.',
        'TIFF זה שונה מקובצי ה־TIFF בהערכה השמורה. ודאו שהניסויים עצמאיים.'),
    'Recorded in training': ('Объект был в обучении', 'העצם היה באימון'),
    'Recorded in the original test': ('Объект был в исходном тесте', 'העצם היה בבדיקה המקורית'),
    'Previous object': ('Предыдущий объект', 'העצם הקודם'),
    'Next object': ('Следующий объект', 'העצם הבא'),
    'Total predicted': ('Всего прогнозов', 'סך כל התחזיות'),
    'Confirmed among reviewed': ('Подтверждено среди проверенных', 'אושרו מתוך אלו שנבדקו'),
    'No saved image is available for this object.': (
        'Сохранённого изображения этого объекта нет.', 'אין תמונה שמורה לעצם זה.'),
}
register_translations({key: val[0] for key, val in _TEXT.items()},
                      hebrew={key: val[1] for key, val in _TEXT.items()})

_ROLE = QtCore.Qt.ItemDataRole.UserRole
_CHECKED = QtCore.Qt.CheckState.Checked
_DECISIONS = {'correct': 'Correct prediction', 'incorrect': 'Incorrect prediction'}


class _ReviewDialog(QtWidgets.QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr('Review new objects…'))
        self._help = None
        self.layout_root = QtWidgets.QVBoxLayout(self)
        shortcut = QtGui.QShortcut(QtGui.QKeySequence('F1'), self)
        shortcut.activated.connect(self._show_help)

    def _footer(self):
        actions = QtWidgets.QHBoxLayout()
        guide = QtWidgets.QPushButton('?')
        guide.setAccessibleName(tr('Help'))
        guide.clicked.connect(self._show_help)
        actions.addWidget(guide)
        actions.addStretch()
        close = QtWidgets.QPushButton(tr('Close'))
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        self.layout_root.addLayout(actions)
        install_parameter_wheel_guard(self)

    def _show_help(self):
        from .help_center import HelpCenter
        if self._help is None:
            self._help = HelpCenter(self)
        self._help.open_topic('object_prediction_review')


class PredictionSetupDialog(_ReviewDialog):
    """Choose a project dataset, tiles and a saved object classifier."""

    def __init__(self, project, parent=None, *, preferred_model=None):
        super().__init__(parent)
        self.resize(700, 570)
        self.project = project
        self.request = self.review_path = None
        hint = QtWidgets.QLabel(tr(
            'Run the selected saved model on measured objects with no manual class. Check the tiles to include.'))
        hint.setWordWrap(True)
        self.layout_root.addWidget(hint)
        form = QtWidgets.QFormLayout()
        self.models, self.datasets = QtWidgets.QComboBox(), QtWidgets.QComboBox()
        self.models.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        workspace = Path(project.workspace)
        for report in sorted((workspace / 'model_evaluations').glob('Evaluation_*/report.json'), reverse=True):
            for model in ('tree', 'forest'):
                if report.with_name(model + '.joblib').is_file():
                    choice = (str(report), model)
                    self.models.addItem(f'{report.parent.name} · {model_display_name(report, model)}', choice)
                    if choice == preferred_model:
                        self.models.setCurrentIndex(self.models.count() - 1)
        for dataset in project.datasets:
            if dataset.get('last_csv') and dataset.get('results_current'):
                self.datasets.addItem(dataset['name'], dataset['id'])
                if dataset['id'] == project.active_dataset_id:
                    self.datasets.setCurrentIndex(self.datasets.count() - 1)
        form.addRow(tr('Saved model'), self.models)
        form.addRow(tr('Dataset'), self.datasets)
        self.layout_root.addLayout(form)
        self.tiles = QtWidgets.QListWidget()
        self.layout_root.addWidget(self.tiles, 1)
        choices = QtWidgets.QHBoxLayout()
        for key, checked in (('Select all tiles', True), ('Clear tile selection', False)):
            button = QtWidgets.QPushButton(tr(key))
            button.clicked.connect(lambda _clicked=False, yes=checked: self._check_tiles(yes))
            choices.addWidget(button)
        choices.addStretch()
        self.layout_root.addLayout(choices)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        self.layout_root.addWidget(self.status)
        self.predict = QtWidgets.QPushButton(tr('Predict on checked tiles'))
        self.predict.clicked.connect(self._submit)
        self.layout_root.addWidget(self.predict)
        self.history = QtWidgets.QComboBox()
        for report in sorted((workspace / 'object_predictions').glob('Prediction_*/report.json'), reverse=True):
            self.history.addItem(report.parent.name, str(report))
        previous = QtWidgets.QHBoxLayout()
        previous.addWidget(QtWidgets.QLabel(tr('Saved prediction reviews')))
        previous.addWidget(self.history, 1)
        resume = QtWidgets.QPushButton(tr('Open review'))
        resume.setEnabled(bool(self.history.count()))
        resume.clicked.connect(self._resume)
        previous.addWidget(resume)
        self.layout_root.addLayout(previous)
        self.datasets.currentIndexChanged.connect(self._load_tiles)
        self.tiles.itemChanged.connect(self._update)
        self._load_tiles()
        self._footer()

    def _load_tiles(self):
        from .service import tile_records
        self.tiles.clear()
        self.status.clear()
        ident = self.datasets.currentData()
        if ident is not None:
            try:
                for record in tile_records(self.project.get_dataset(ident)):
                    if record.get('excluded'):
                        continue
                    name = Path(record['filename']).stem
                    item = QtWidgets.QListWidgetItem(name)
                    item.setCheckState(_CHECKED)
                    self.tiles.addItem(item)
            except (OSError, ValueError, KeyError, TypeError) as error:
                self.tiles.clear()
                self.status.setText(str(error))
        if not self.status.text() and not self.models.count():
            self.status.setText(tr('No saved tree or forest is available. Train a model and save an evaluation first.'))
        elif not self.status.text() and not self.tiles.count():
            self.status.setText(tr('No active tiles with saved measurements'))
        self._update()

    def _selected_tiles(self):
        return [item.text() for i in range(self.tiles.count())
                if (item := self.tiles.item(i)).checkState() == _CHECKED]

    def _check_tiles(self, checked):
        with QtCore.QSignalBlocker(self.tiles):
            for index in range(self.tiles.count()):
                self.tiles.item(index).setCheckState(_CHECKED if checked else QtCore.Qt.CheckState.Unchecked)
        self._update()

    def _update(self, *_):
        self.predict.setEnabled(bool(self.models.count() and self.datasets.count() and self._selected_tiles()))

    def _submit(self):
        evaluation, model = self.models.currentData()
        self.request = dict(evaluation_path=evaluation, model_key=model,
                            dataset_id=self.datasets.currentData(), tile_names=self._selected_tiles())
        self.accept()

    def _resume(self):
        self.review_path = self.history.currentData()
        self.accept()


class PredictionReviewDialog(_ReviewDialog):
    """Record approval or rejection of each frozen prediction as a separate audit."""

    def __init__(self, project, path, parent=None):
        super().__init__(parent)
        from .object_prediction import load_prediction, load_review
        self.project, self.path = project, path
        report = load_prediction(project, path)
        self.rows = report['snapshot']['rows']
        self.decisions = load_review(project, path)
        self.workspace = Path(project.workspace).resolve()
        dataset, = report['snapshot']['datasets']
        from .evaluation_crops import EvaluationCrops
        self._crops = EvaluationCrops(self.workspace)
        self._results_dir = dataset['results_dir']
        self.mask_root = (self.workspace / dataset['results_dir'] / 'verification_masks').resolve()
        model = report['model']
        self.model_classes = tuple(model['classes'])
        self.cell_filter = None
        self.resize(1180, 850)
        scope = {
            'same_source': 'This source was used in the original training or test.',
            'different_source': 'This TIFF differs from the TIFFs in the saved evaluation. Check that the experiments are independent.',
        }
        model_report = model.get('report_path')
        model_name = (model_display_name(self.workspace / model_report, model['name'])
                      if model_report else tr(model['name']))
        note = QtWidgets.QLabel(tr('{model} · classes available to this model — {classes}',
                                  model=model_name,
                                  classes=', '.join(_class_name(label) for label in model['classes']))
                                + '\n' + tr(scope.get(model.get('source_overlap'),
                                                    'Independence from the training sources could not be verified.')))
        note.setWordWrap(True)
        note.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.layout_root.addWidget(note)
        filter_bar = QtWidgets.QHBoxLayout()
        self.filter_note = QtWidgets.QLabel()
        self.filter_note.setWordWrap(True)
        self.filter_note.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        filter_bar.addWidget(self.filter_note, 1)
        self.clear_filter = QtWidgets.QPushButton(tr('Show all masks'))
        self.clear_filter.clicked.connect(lambda: self._set_cell_filter(None))
        self.clear_filter.setEnabled(False)
        filter_bar.addWidget(self.clear_filter)
        self.layout_root.addLayout(filter_bar)

        splitter = QtWidgets.QSplitter()
        self.objects = QtWidgets.QListWidget()
        self.objects.setMinimumWidth(230)
        splitter.addWidget(self.objects)
        self.mask = ImageViewer(empty_text=tr('No saved image is available for this object.'))
        self.crop = ImageViewer(empty_text=tr('No saved image is available for this object.'))
        self.mask.view.setBackgroundBrush(QtGui.QColor('#34454d'))
        self.finished.connect(self._clear_previews)
        for viewer, title in ((self.mask, 'Exact binary mask'), (self.crop, 'Saved intensity crop')):
            box = QtWidgets.QGroupBox(tr(title))
            layout = QtWidgets.QVBoxLayout(box)
            layout.addWidget(viewer)
            splitter.addWidget(box)
            viewer.loaded.connect(self._image_loaded)
        splitter.setSizes([280, 420, 420])
        self.layout_root.addWidget(splitter, 1)

        self.caption = QtWidgets.QLabel()
        self.caption.setWordWrap(True)
        self.caption.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.layout_root.addWidget(self.caption)
        actions = QtWidgets.QHBoxLayout()
        for key, step in (('Previous object', -1), ('Next object', 1)):
            button = QtWidgets.QPushButton(tr(key))
            button.clicked.connect(lambda _clicked=False, offset=step: self._move(offset))
            actions.addWidget(button)
        actions.addStretch()
        self.mark_buttons = []
        icons = {'correct': QtWidgets.QStyle.StandardPixmap.SP_DialogApplyButton,
                 'incorrect': QtWidgets.QStyle.StandardPixmap.SP_DialogCancelButton}
        for key, decision in (*[(text, value) for value, text in _DECISIONS.items()], ('Clear decision', None)):
            button = QtWidgets.QPushButton(tr(key))
            if decision in icons:
                button.setIcon(self.style().standardIcon(icons[decision]))
            button.clicked.connect(lambda _clicked=False, value=decision: self._mark(value))
            actions.addWidget(button)
            self.mark_buttons.append(button)
        self.layout_root.addLayout(actions)

        self.counts = QtWidgets.QLabel()
        self.layout_root.addWidget(self.counts)
        tabs = QtWidgets.QTabWidget()
        self.stats = _table()
        tabs.addTab(self.stats, tr('Review summary'))
        matrix_page = QtWidgets.QWidget()
        matrix_layout = QtWidgets.QVBoxLayout(matrix_page)
        self.matrix_hint = QtWidgets.QLabel()
        self.matrix_hint.setWordWrap(True)
        self.matrix = _table()
        self.matrix.cellClicked.connect(self._open_cell)
        matrix_layout.addWidget(self.matrix_hint)
        matrix_layout.addWidget(self.matrix)
        tabs.addTab(matrix_page, tr('Confusion matrix'))
        tabs.setMaximumHeight(270)
        self.layout_root.addWidget(tabs)
        for row in self.rows:
            self.objects.addItem(self._item_text(row))
        self.objects.currentRowChanged.connect(self._select)
        self._update_counts()
        self.objects.setCurrentRow(next((i for i, row in enumerate(self.rows) if not self._decision(row)), 0))
        self._footer()

    def _decision(self, row):
        return self._review(row).get('decision')

    def _review(self, row):
        return self.decisions.get(object_key(row['tile_name'], row['object_id']), {})

    def _actual(self, row):
        review = self._review(row)
        return row['predicted'] if review.get('decision') == 'correct' else review.get('actual_class')

    def _open_cell(self, row, column):
        cell = self.matrix.item(row, column)
        if column > 0 and cell is not None and cell.text() != '0':
            self._set_cell_filter((self.actual_classes[row], self.model_classes[column - 1]))

    def _set_cell_filter(self, pair):
        self.cell_filter = pair
        self.clear_filter.setEnabled(pair is not None)
        visible = []
        for index, row in enumerate(self.rows):
            matches = pair is None or (self._actual(row), row['predicted']) == pair
            self.objects.item(index).setHidden(not matches)
            if matches:
                visible.append(index)
        self.filter_note.setText('' if pair is None else tr(
            'Reference {actual} → prediction {predicted} · masks: {count}',
            actual=_class_name(pair[0]), predicted=_class_name(pair[1]), count=len(visible)))
        if self.objects.currentRow() not in visible:
            self.objects.setCurrentRow(visible[0] if visible else -1)

    def _clear_previews(self, _result):
        self.mask.clear()
        self.crop.clear()

    def _item_text(self, row):
        return f"{row['tile_name']} · #{row['object_id']}\n{_class_name(row['predicted'])} · {tr(_DECISIONS.get(self._decision(row), 'Pending'))}"

    def _move(self, offset):
        index = self.objects.currentRow()
        stop = len(self.rows) if offset > 0 else -1
        for candidate in range(index + offset, stop, offset):
            if 0 <= candidate < len(self.rows) and not self.objects.item(candidate).isHidden():
                self.objects.setCurrentRow(candidate)
                break

    def _select(self, index):
        for button in self.mark_buttons:
            button.setEnabled(False)
        if not 0 <= index < len(self.rows):
            self.caption.clear()
            self._clear_previews(None)
            return
        row = self.rows[index]
        self._show_caption(row)
        for viewer, field in ((self.mask, 'mask_path'), (self.crop, 'crop_path')):
            relative = row.get(field)
            try:
                filename = (self.workspace / relative).resolve() if relative else None
            except (OSError, RuntimeError):
                filename = None
            if (filename and self.mask_root in filename.parents
                    and self.workspace in filename.parents and filename.is_file()):
                viewer.set_image(filename, ruler_scale=self._crops.ruler_scale(
                    self._results_dir, row['tile_name'], row['object_id']))
            else:
                viewer.clear(tr('No saved image is available for this object.'))

    def _show_caption(self, row):
        warning = {'train': 'Recorded in training', 'test': 'Recorded in the original test'}
        caption = (f"{row['tile_name']} · #{row['object_id']}\n{tr('Predicted class')} — "
                   f"{_class_name(row['predicted'])} · {tr(_DECISIONS.get(self._decision(row), 'Pending'))}")
        if self._decision(row):
            actual = self._actual(row)
            caption += ('\n' + tr('Correct class not recorded') if actual is None
                        else f"\n{tr('Correct class')} — {_class_name(actual)}")
        if row.get('evaluation_overlap') in warning:
            caption += '\n' + tr(warning[row['evaluation_overlap']])
        self.caption.setText(caption)

    def _image_loaded(self, *_):
        for button in self.mark_buttons:
            button.setEnabled(True)

    def _mark(self, decision):
        from .object_prediction import save_review
        index = self.objects.currentRow()
        if not 0 <= index < len(self.rows):
            return
        row = self.rows[index]
        actual_class = None
        if decision == 'incorrect':
            choices = {_class_name(entry['id']): entry['id'] for entry in OBJECT_CLASS_CATALOG
                       if entry['id'] != row['predicted']}
            names = list(choices)
            previous = self._review(row).get('actual_class')
            current = names.index(_class_name(previous)) if previous is not None else 0
            name, accepted = QtWidgets.QInputDialog.getItem(
                self, tr('Correct class'), tr('Choose the correct class for this mask.'),
                names, current, False)
            if not accepted:
                return
            actual_class = choices[name]
        try:
            self.decisions = save_review(self.project, self.path, row['tile_name'], row['object_id'],
                                         decision, actual_class=actual_class)
        except (OSError, ValueError, TypeError, KeyError) as error:
            QtWidgets.QMessageBox.warning(self, tr('Review new objects…'), str(error))
            return
        self.objects.item(index).setText(self._item_text(row))
        self._show_caption(row)
        self._update_counts()
        if self.cell_filter is not None:
            self._set_cell_filter(self.cell_filter)
        elif decision is not None:
            self._move(1)

    def _update_counts(self):
        by_class = {}
        confusion = Counter()
        for row in self.rows:
            predicted = row['predicted']
            review = self._review(row)
            decision = review.get('decision')
            by_class.setdefault(predicted, Counter())[decision] += 1
            actual = self._actual(row)
            if actual is not None:
                confusion[actual, predicted] += 1
        correct = sum(c['correct'] for c in by_class.values())
        reviewed = correct + sum(c['incorrect'] for c in by_class.values())
        self.counts.setText(tr('Reviewed {reviewed} of {total}. Confirmed {correct} of {reviewed} reviewed ({percent}).',
                               reviewed=reviewed, total=len(self.rows), correct=correct,
                               percent=self._percentage(correct, reviewed)))
        _fill(self.stats, [tr(key) for key in ('Predicted class', 'Total predicted', *_DECISIONS.values(),
                                               'Pending', 'Confirmed among reviewed')],
              [(_class_name(label), sum(counts.values()), counts['correct'], counts['incorrect'], counts[None],
                self._percentage(counts['correct'], counts['correct'] + counts['incorrect']))
               for label, counts in sorted(by_class.items())])
        counted = sum(confusion.values())
        hint = tr('Rows are reviewed classes. Columns are model predictions. Masks counted: {count}.',
                  count=counted)
        hint += ' ' + tr('Click a nonzero count to inspect its masks.')
        if reviewed > counted:
            hint += '\n' + tr('Old errors without a correct class: {count}. Click Incorrect again on those masks to include them.',
                              count=reviewed - counted)
        self.matrix_hint.setText(hint)
        self.actual_classes = sorted(set(self.model_classes) | {actual for actual, _ in confusion})
        _fill(self.matrix, [tr('Correct class'), *map(_class_name, self.model_classes)],
              [(_class_name(actual), *(confusion[actual, predicted] for predicted in self.model_classes))
               for actual in self.actual_classes])

    @staticmethod
    def _percentage(correct, reviewed):
        return f'{correct / reviewed:.1%}' if reviewed else '—'
