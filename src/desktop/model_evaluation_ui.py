"""Project-wide model training, holdout reports and error inspection."""

from collections import Counter
import json
from pathlib import Path
import os
import shutil
import tempfile

from src.object_classes import OBJECT_CLASS_CATALOG
from src.default_settings import MODEL_DEFAULTS
from .help import attach_help, help_label
from .i18n import get_language, tr
from .input_safety import install_parameter_wheel_guard
from . import model_chart_text, model_evaluation_text
from .model_evaluation import CLASS_IDS, FOREST_TREE_COUNT_RANGE
from .model_names import model_alias, model_display_name, save_model_name
from .model_split_gallery import ModelSplitGallery
from .qt import QtCore, QtGui, QtWidgets, show_centered_window
from .storage_names import readable_name
from .widgets import ImageViewer


USER_ROLE = QtCore.Qt.ItemDataRole.UserRole
CHECKED = QtCore.Qt.CheckState.Checked


def _class_name(label):
    entry = OBJECT_CLASS_CATALOG[int(label)]
    if get_language() == 'he':
        return ('חלקיק', 'סיב', 'צינור בחצייה עצמית', 'צינורות מצטלבים',
                'אגלומרט', 'עצמים צמודים')[int(label)]
    return entry['label_ru' if get_language() == 'ru' else 'label_en']


def _table():
    table = QtWidgets.QTableWidget()
    table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
    table.verticalHeader().hide()
    table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    return table


def _fill(table, headers, rows):
    fit_columns = table.property('fitNewColumns') and (
        table.columnCount() != len(headers)
        or any(table.horizontalHeaderItem(j) is None or table.horizontalHeaderItem(j).text() != title
               for j, title in enumerate(headers)))
    table.clear()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            table.setItem(i, j, QtWidgets.QTableWidgetItem(str(value)))
    if fit_columns:
        table.resizeColumnsToContents()


def _configure_comparison_view(view):
    view.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
    view.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
    view.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)


def _comparison_table():
    table = _table()
    _configure_comparison_view(table)
    table.setProperty('fitNewColumns', True)
    return table


class ModelEvaluationPage(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.window = parent
        self.project_path = None
        self.signature = None
        self.payload = None
        self.current_result = None
        self.current_result_path = None
        self.training_file = None
        self._busy = False
        self._dataset_ids = None
        self._table_windows = {}
        layout = QtWidgets.QVBoxLayout(self)
        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.inputs = QtWidgets.QWidget()
        self.tabs.addTab(self.inputs, tr('Training data'))
        inputs = QtWidgets.QVBoxLayout(self.inputs)
        file_actions = QtWidgets.QHBoxLayout()
        open_file = QtWidgets.QPushButton(tr('Open training table…'))
        open_file.clicked.connect(self.open_training_file)
        file_actions.addWidget(attach_help(open_file, 'model_evaluation'))
        self.use_datasets = QtWidgets.QPushButton(tr('Use project datasets'))
        self.use_datasets.clicked.connect(lambda: self.set_training_file(None))
        file_actions.addWidget(attach_help(self.use_datasets, 'model_evaluation'))
        file_actions.addWidget(help_label('model_evaluation'))
        self.file_label = QtWidgets.QLabel()
        self.file_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        file_actions.addWidget(self.file_label, 1)
        inputs.addLayout(file_actions)
        self.datasets = _table()
        self.datasets.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked |
                                     QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed)
        self.datasets.itemChanged.connect(self.invalidate)
        inputs.addWidget(self.datasets)
        hint = QtWidgets.QLabel(tr('Select one measured dataset per TIFF. Enter the same group for related TIFFs. Imported tiles require a confirmed group.'))
        hint.setWordWrap(True)
        inputs.addWidget(hint)
        controls = QtWidgets.QHBoxLayout()
        self.area = QtWidgets.QComboBox()
        self.area.addItem(tr('Area in source pixels²'), 'Area')
        self.area.addItem(tr('Area in µm²'), 'Area_um2')
        self.seed = QtWidgets.QSpinBox()
        self.seed.setRange(0, 2**31 - 1)
        self.seed.setValue(42)
        self.cv = QtWidgets.QComboBox()
        self.cv.addItem(tr('Cross-validation off'), 0)
        for k in range(2, 11):
            self.cv.addItem(f'K = {k}', k)
        for label, field, signal in [
            ('Area units', self.area, self.area.currentIndexChanged),
            ('Random seed', self.seed, self.seed.valueChanged),
            ('Training-only K-fold', self.cv, self.cv.currentIndexChanged),
        ]:
            controls.addWidget(QtWidgets.QLabel(tr(label)))
            controls.addWidget(attach_help(field, 'model_evaluation'))
            signal.connect(self.invalidate)
        controls.addStretch()
        inputs.addLayout(controls)

        evaluation_controls = QtWidgets.QHBoxLayout()
        self.split_mode = QtWidgets.QComboBox()
        self.split_mode.addItem(tr('Whole TIFFs / experiments'), 'group')
        self.split_mode.addItem(tr('Stratified objects (same-source check)'), 'object')
        self.split_mode.setCurrentIndex(self.split_mode.findData(MODEL_DEFAULTS['split_mode']))
        self.forest_tree_count = QtWidgets.QSpinBox()
        self.forest_tree_count.setRange(*FOREST_TREE_COUNT_RANGE)
        self.forest_tree_count.setValue(MODEL_DEFAULTS['forest_tree_count'])
        for label, field, signal in [
            ('Split method', self.split_mode, self.split_mode.currentIndexChanged),
            ('Trees in forest', self.forest_tree_count, self.forest_tree_count.valueChanged),
        ]:
            evaluation_controls.addWidget(QtWidgets.QLabel(tr(label)))
            evaluation_controls.addWidget(attach_help(field, 'model_evaluation'))
            signal.connect(self.invalidate)
        evaluation_controls.addStretch()
        inputs.addLayout(evaluation_controls)

        class_group = QtWidgets.QGroupBox(tr('Object classes to train'))
        class_layout = QtWidgets.QGridLayout(class_group)
        self.train_classes = {}
        for index, label in enumerate(CLASS_IDS):
            field = QtWidgets.QCheckBox(_class_name(label))
            field.setChecked(True)
            field.toggled.connect(self.invalidate)
            self.train_classes[label] = field
            class_layout.addWidget(field, index // 3, index % 3)
        class_layout.addWidget(help_label('model_evaluation'), 0, 3)
        inputs.addWidget(class_group)
        install_parameter_wheel_guard(self)
        self.plan_page = QtWidgets.QWidget()
        self.tabs.addTab(self.plan_page, tr('Split plan'))
        plan_layout = QtWidgets.QVBoxLayout(self.plan_page)
        self.plan_text = QtWidgets.QPlainTextEdit()
        self.plan_text.setReadOnly(True)
        plan_layout.addWidget(self.plan_text, 1)
        self.coverage = _table()
        plan_layout.addWidget(self.coverage, 1)
        self.plot_button = QtWidgets.QPushButton(tr('Data charts…'))
        self.plot_button.clicked.connect(self.show_data_charts)
        self.plot_button.setEnabled(False)
        plot_actions = QtWidgets.QHBoxLayout()
        plot_actions.addWidget(attach_help(self.plot_button, 'training_charts'))
        plot_actions.addWidget(help_label('training_charts'))
        self.plan_gallery = QtWidgets.QPushButton(tr('Split gallery…'))
        self.plan_gallery.clicked.connect(lambda: self.show_split_gallery(self.payload))
        self.plan_gallery.setEnabled(False)
        plot_actions.addWidget(attach_help(self.plan_gallery, 'evaluation_gallery'))
        plot_actions.addWidget(help_label('evaluation_gallery'))
        plot_actions.addStretch()
        plan_layout.addLayout(plot_actions)

        result_page = QtWidgets.QWidget()
        self.tabs.addTab(result_page, tr('Model comparison'))
        result_layout = QtWidgets.QVBoxLayout(result_page)
        report_actions = QtWidgets.QHBoxLayout()
        self.history = QtWidgets.QComboBox()
        self.history.currentIndexChanged.connect(self.open_history)
        report_actions.addWidget(QtWidgets.QLabel(tr('Saved evaluations')))
        report_actions.addWidget(self.history, 1)
        self.models = QtWidgets.QComboBox()
        self.models.currentIndexChanged.connect(self.select_model)
        report_actions.addWidget(self.models)
        self.performance_button = QtWidgets.QPushButton(tr('Performance charts…'))
        self.performance_button.clicked.connect(self.show_performance_charts)
        self.performance_button.setEnabled(False)
        report_actions.addWidget(attach_help(self.performance_button, 'training_charts'))
        report_actions.addWidget(help_label('training_charts'))
        result_layout.addLayout(report_actions)
        self.evaluation_scope = QtWidgets.QLabel()
        self.evaluation_scope.setWordWrap(True)
        result_layout.addWidget(self.evaluation_scope)
        self.metrics = _comparison_table()
        export_actions = QtWidgets.QHBoxLayout()
        self.rename_model = QtWidgets.QPushButton(tr('Rename selected model…'))
        self.rename_model.clicked.connect(self.rename_selected_model)
        self.rename_model.setEnabled(False)
        export_actions.addWidget(attach_help(self.rename_model, 'model_fit'))
        self.save_model = QtWidgets.QPushButton(tr('Save selected model…'))
        self.save_model.clicked.connect(self.export_selected_model)
        self.save_model.setEnabled(False)
        export_actions.addWidget(attach_help(self.save_model, 'model_evaluation'))
        export_actions.addWidget(help_label('model_evaluation'))
        self.report_gallery = QtWidgets.QPushButton(tr('Split gallery…'))
        self.report_gallery.clicked.connect(lambda: self.show_split_gallery(self.current_result))
        self.report_gallery.setEnabled(False)
        export_actions.addWidget(attach_help(self.report_gallery, 'evaluation_gallery'))
        export_actions.addWidget(help_label('evaluation_gallery'))
        export_actions.addStretch()
        self.open_table_button = QtWidgets.QToolButton()
        self.open_table_button.setText(tr('Open table in a separate window…'))
        self.open_table_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.open_table_button.setEnabled(False)
        export_actions.addWidget(attach_help(self.open_table_button, 'model_fit'))
        result_layout.addLayout(export_actions)
        self.details = QtWidgets.QTabWidget()
        self.comparison_split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.comparison_split.addWidget(self.metrics)
        self.comparison_split.addWidget(self.details)
        self.comparison_split.setChildrenCollapsible(False)
        self.comparison_split.setStretchFactor(1, 1)
        self.comparison_split.setSizes([120, 460])
        preferences = getattr(parent, 'preferences', None)
        if preferences is not None:
            state = preferences.value('workspaces/model/comparison')
            if isinstance(state, QtCore.QByteArray):
                self.comparison_split.restoreState(state)
            self.comparison_split.splitterMoved.connect(
                lambda *_: preferences.setValue('workspaces/model/comparison', self.comparison_split.saveState()))
        self.comparison_split.setHandleWidth(9)
        self.comparison_split.handle(1).setToolTip(tr('Drag to resize the summary and detail tables.'))
        result_layout.addWidget(self.comparison_split, 1)
        matrix_page = QtWidgets.QWidget()
        matrix_layout = QtWidgets.QVBoxLayout(matrix_page)
        self.matrix_note = QtWidgets.QLabel()
        self.matrix_note.setWordWrap(True)
        self.matrix_note.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        matrix_layout.addWidget(self.matrix_note)
        self.confusion = _comparison_table()
        self.confusion.cellClicked.connect(self.filter_errors)
        matrix_layout.addWidget(attach_help(self.confusion, 'confusion_matrix'), 1)
        self.percent = QtWidgets.QCheckBox(tr('Row percentages'))
        self.percent.toggled.connect(self.select_model)
        matrix_layout.addWidget(attach_help(self.percent, 'confusion_matrix'))
        self.details.addTab(attach_help(matrix_page, 'confusion_matrix'), tr('Confusion matrix'))
        self.model_details = QtWidgets.QPlainTextEdit()
        self.model_details.setReadOnly(True)
        self.details.addTab(attach_help(self.model_details, 'model_fit'), tr('Model details'))
        tuning_page = QtWidgets.QWidget()
        tuning_layout = QtWidgets.QVBoxLayout(tuning_page)
        self.tuning_note = QtWidgets.QLabel()
        self.tuning_note.setWordWrap(True)
        tuning_layout.addWidget(self.tuning_note)
        self.tuning_table = _comparison_table()
        tuning_layout.addWidget(self.tuning_table)
        self.details.addTab(attach_help(tuning_page, 'model_fit'), tr('Depth and tuning'))
        self.tree_nodes = _comparison_table()
        self.details.addTab(attach_help(self.tree_nodes, 'tree_impurity'), tr('Tree nodes'))
        self.errors = _comparison_table()
        self.errors.cellActivated.connect(self.open_error)
        self.details.addTab(attach_help(self.errors, 'confusion_matrix'), tr('Object inspection'))
        detail_help = help_label('confusion_matrix')
        self.details.setCornerWidget(detail_help)
        self.details.currentChanged.connect(
            lambda index: attach_help(detail_help, self.details.widget(index).property('helpKey'))
            if index >= 0 else None)
        self.error_rows = []
        self.error_filter = QtWidgets.QComboBox()
        self.error_filter.addItem(tr('All incorrect predictions'), 'all')
        self.error_filter.addItem(tr('Tree wrong, forest correct'), 'forest')
        self.error_filter.addItem(tr('Forest wrong, tree correct'), 'tree')
        self.error_filter.currentIndexChanged.connect(self.reset_errors)
        result_layout.addWidget(self.error_filter)
        self.error_filter.hide()
        self.details.currentChanged.connect(
            lambda _index: self.error_filter.setVisible(self.details.currentWidget() is self.errors))

        self._comparison_tables = {
            'metrics': ('Evaluation metrics', self.metrics, 'model_fit'),
            'confusion': ('Confusion matrix', self.confusion, 'confusion_matrix'),
            'tuning': ('Depth and tuning', self.tuning_table, 'model_fit'),
            'tree': ('Tree nodes', self.tree_nodes, 'tree_impurity'),
            'errors': ('Object inspection', self.errors, 'confusion_matrix'),
        }
        table_menu = QtWidgets.QMenu(self.open_table_button)
        for key, (title, _, _) in self._comparison_tables.items():
            table_menu.addAction(tr(title), lambda _checked=False, selected=key: self.show_comparison_table(selected))
        self.open_table_button.setMenu(table_menu)

        actions = QtWidgets.QHBoxLayout()
        self.preview = QtWidgets.QPushButton(tr('Preview 80/20 split'))
        self.preview.clicked.connect(lambda: self.start(True))
        self.train = QtWidgets.QPushButton(tr('Train and evaluate'))
        self.train.clicked.connect(lambda: self.start(False))
        actions.addWidget(self.preview)
        actions.addWidget(self.train)
        self.prediction_review = QtWidgets.QPushButton(tr('Review new objects…'))
        self.prediction_review.clicked.connect(lambda: self.window.open_prediction_review())
        actions.addWidget(attach_help(self.prediction_review, 'object_prediction_review'))
        actions.addWidget(help_label('object_prediction_review'))
        actions.addWidget(help_label('model_evaluation'))
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        actions.addWidget(self.status, 1)
        layout.addLayout(actions)
        self.set_busy(False)

    def refresh(self, project):
        ids = [(d['id'], d.get('name', d['id']), d.get('source_id'), d.get('measurement_signature'))
               for d in project.datasets if d.get('last_csv')]
        if self.project_path == project.path and self._dataset_ids == ids:
            return
        same = self.project_path == project.path
        saved = {self.datasets.item(i, 0).data(USER_ROLE):
                 (self.datasets.item(i, 0).checkState(), self.datasets.item(i, 2).text())
                 for i in range(self.datasets.rowCount())} if same else {}
        self.project_path, self._dataset_ids = project.path, ids
        if not same:
            self.payload = self.current_result = None
            self.current_result_path = None
            self.set_training_file(None)
            self.plan_text.clear()
            self.coverage.clear()
            self.models.clear()
            self.metrics.clear()
            self.evaluation_scope.clear()
            self.evaluation_scope.hide()
            self.plot_button.setEnabled(False)
            self.performance_button.setEnabled(False)
            self.report_gallery.setEnabled(False)
            self.error_rows = []
            self.select_model()
        self.datasets.blockSignals(True)
        _fill(self.datasets, [tr('Dataset'), tr('Source'), tr('Group override · double-click to edit')],
              [(name, source or tr('Unconfirmed'), '') for _, name, source, _ in ids])
        sources = {item['id']: item.get('name', item['id']) for item in project.sources}
        for index, (ident, _, source, _) in enumerate(ids):
            checked, group = saved.get(ident, (CHECKED if source else QtCore.Qt.CheckState.Unchecked, ''))
            item = self.datasets.item(index, 0)
            item.setData(USER_ROLE, ident)
            item.setFlags((item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable) & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            item.setCheckState(checked)
            item = self.datasets.item(index, 1)
            item.setText(sources.get(source, item.text()))
            item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.datasets.item(index, 2).setText(group)
        self.datasets.blockSignals(False)
        self.invalidate()
        self.refresh_history()

    def refresh_history(self, selected=None):
        root = Path(self.window.project.workspace) / 'model_evaluations'
        selected = str(selected) if selected else self.history.currentData()
        self.history.blockSignals(True)
        self.history.clear()
        self.history.addItem(tr('Select an evaluation…'))
        for path in sorted(root.glob('Evaluation_*/report.json'), reverse=True):
            self.history.addItem(path.parent.name, str(path))
        self.history.setCurrentIndex(max(0, self.history.findData(selected)))
        self.history.blockSignals(False)

    def open_history(self):
        path = self.history.currentData()
        if path:
            self.show_result(dict(path=path, preview=False))

    def open_training_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, tr('Open training table…'), self.training_file or self.window.project.workspace,
            tr('Training tables (*.xlsx *.csv)'))
        if path:
            self.set_training_file(path)

    def set_training_file(self, path):
        self.training_file = path
        self.file_label.setText(Path(path).name if path else '')
        self.file_label.setToolTip(path or '')
        self.datasets.setEnabled(not path)
        self.use_datasets.setEnabled(bool(path))
        self.invalidate()

    def invalidate(self):
        """Require a fresh worker preview after any change to the evaluation inputs."""
        self.signature = None
        self.plot_button.setEnabled(False)
        self.plan_gallery.setEnabled(False)
        self.status.setText(tr('Preview the plan before training.'))
        self.set_busy(self._busy)

    def set_busy(self, busy):
        self._busy = busy
        self.inputs.setEnabled(not busy)
        valid_classes = sum(field.isChecked() for field in self.train_classes.values()) >= 2
        self.preview.setEnabled(not busy and valid_classes and bool(self.training_file or self.datasets.rowCount()))
        self.train.setEnabled(not busy and bool(self.signature))
        self.prediction_review.setEnabled(not busy)
        self.rename_model.setEnabled(not busy and self._model_artifact() is not None)

    def start(self, preview):
        selected, groups = [], {}
        if not self.training_file:
            for i in range(self.datasets.rowCount()):
                item = self.datasets.item(i, 0)
                if item.checkState() == CHECKED:
                    ident = item.data(USER_ROLE)
                    selected.append(ident)
                    groups[ident] = self.datasets.item(i, 2).text()
        if preview:
            self.invalidate()
        if self.window.start_job('model_evaluation', dataset_ids=selected, groups=groups,
                                 area=self.area.currentData(), seed=self.seed.value(),
                                 folds=self.cv.currentData(), preview=preview,
                                 planned_signature=self.signature, training_file=self.training_file,
                                 split_mode=self.split_mode.currentData(),
                                 forest_tree_count=self.forest_tree_count.value(),
                                 class_ids=[label for label, field in self.train_classes.items()
                                            if field.isChecked()]):
            self.status.setText(tr('Working…'))

    def show_result(self, summary):
        """Display a worker preview or a saved report with its own snapshot."""
        try:
            data = json.loads(Path(summary['path']).read_text(encoding='utf-8'))
            if data.get('schema_version') != 1:
                raise ValueError(tr('Unsupported evaluation report.'))
            self.payload = data
            self.show_plan(data)
            if summary['preview']:
                self.signature = data['signature'] if data['plan'] else None
                self.tabs.setCurrentIndex(1)
                self.status.setText(data['plan_error'] or tr('Plan ready.'))
            else:
                self.current_result = data
                self.current_result_path = Path(summary['path'])
                self.report_group_names = self.group_names
                self.refresh_history(summary['path'])
                self.show_comparison()
                self.tabs.setCurrentIndex(2)
                self.status.setText(tr('Evaluation saved.'))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.status.setText(str(exc))
        self.set_busy(False)

    def show_plan(self, payload):
        snapshot = payload['snapshot']
        plan = payload['plan']
        classes = payload.get('training_options', {}).get('class_ids') or CLASS_IDS
        by_object = bool(plan and plan.get('split_mode') == 'object')
        self.plot_button.setEnabled(bool(snapshot['rows']))
        self.plan_gallery.setEnabled(bool(plan))
        names = {row['group']: row['group'].split(':', 1)[-1] for row in snapshot['rows']}
        for entry in snapshot['datasets']:
            if entry.get('group', '').startswith(('tiff:', 'file-tiff:')):
                names[entry['group']] = entry['name']
        self.group_names = names
        lines = []
        if plan:
            if plan['demo']:
                lines.append(tr('Demonstration only. No independent test groups.'))
            else:
                lines.append(tr('Train {train} · Test {test} ({fraction}%)',
                                train=len(plan['train']), test=len(plan['test']),
                                fraction=f"{100 * plan['test_fraction']:.1f}"))
                if by_object:
                    lines.append(tr('Same-source object test. Scores apply to these TIFFs.'))
                if abs(plan['test_fraction'] - .20) > .005:
                    lines.append(tr('Integer class counts produce a different test fraction from 20%.')
                                 if by_object else tr('Whole groups produce a different test fraction from 20%.'))
                if not by_object:
                    for key, title in [('train_groups', 'Training groups'), ('test_groups', 'Test groups')]:
                        lines.append(tr(title) + ' · ' + ', '.join(names[g] for g in plan[key]))
                for i, fold in enumerate(plan['folds'], 1):
                    if by_object:
                        lines.append(tr('Object fold {number}', number=i))
                    else:
                        held = sorted({names[snapshot['rows'][j]['group']] for j in fold['test']})
                        lines.append(f"K{i} · {tr('Validation groups')} · " + ', '.join(held))
                    if 'train_counts' in fold:
                        lines.append(self._class_split_counts(fold, tr('Validation')))
                absent = [_class_name(i) for i in classes
                          if plan['train_counts'][str(i)] and not plan['test_counts'][str(i)]]
                if absent:
                    lines.append(tr('Classes absent from test') + ' · ' + ', '.join(absent))
                test_heavy = [_class_name(i) for i in classes
                              if plan['test_counts'][str(i)] > plan['train_counts'][str(i)]]
                if test_heavy:
                    lines.append(tr('Classes with more test than training objects') + ' · ' + ', '.join(test_heavy))
            lines.append(self._class_split_counts(plan, tr('Test')))
        lines.extend(f"{d['name']} · {tr(d['status'])} · {d['reviewed']}/{d['measured']}" for d in snapshot['datasets'])
        self.plan_text.setPlainText('\n'.join(lines))
        groups = {}
        for row in snapshot['rows']:
            groups.setdefault(row['group'], Counter())[row['target']] += 1
        headers = [tr('Group'), tr('Split'), *[_class_name(i) for i in classes]]
        train_groups = set(plan['train_groups']) if plan else set()
        test_groups = set(plan['test_groups']) if plan else set()
        rows = []
        for group, counts in sorted(groups.items()):
            partitions = [tr(partition) for partition, members in [('Train', train_groups), ('Test', test_groups)]
                          if group in members]
            rows.append((names[group], ' + '.join(partitions) or '—', *[counts[i] for i in classes]))
        _fill(self.coverage, headers, rows)

    @staticmethod
    def _class_split_counts(split, other):
        train, test = split['train_counts'], split['test_counts']
        values = ' · '.join(f"{_class_name(label)} {train[label]}/{test[label]}"
                            for label in train if train[label] or test[label])
        return f"{tr('Train')} / {other} · {values}"

    def show_comparison(self):
        report = self.current_result['report']
        self.evaluation_scope.setText(tr('Same-source object test. Scores apply to these TIFFs.')
                                      if report.get('split_mode') == 'object' else '')
        self.evaluation_scope.setVisible(bool(self.evaluation_scope.text()))
        self.performance_button.setEnabled(True)
        self.report_gallery.setEnabled(bool(self.current_result.get('plan')))
        previous_model = self.models.currentData()
        self.models.blockSignals(True)
        self.models.clear()
        for key in report['models']:
            self.models.addItem(model_display_name(self.current_result_path, key), key)
        self.models.setCurrentIndex(max(0, self.models.findData(previous_model)))
        self.models.blockSignals(False)
        _fill(self.metrics, [tr('Model'), 'Macro-F1', tr('Test objects')],
              [(model_display_name(self.current_result_path, key), f"{result['macro_f1']:.3f}" if 'macro_f1' in result else '—',
                len(report['predictions'])) for key, result in report['models'].items()])
        self.select_model()

    def select_model(self):
        key = self.models.currentData()
        self.open_table_button.setEnabled(bool(self.current_result))
        self.save_model.setEnabled(self._model_artifact() is not None)
        self.rename_model.setEnabled(not self._busy and self._model_artifact() is not None)
        if not key or not self.current_result:
            self.confusion.clear()
            self.matrix_note.clear()
            self.percent.setEnabled(False)
            self.model_details.clear()
            self.errors.clear()
            self.tree_nodes.clear()
            self.tuning_table.clear()
            self.tuning_note.clear()
            self._update_table_windows()
            return
        report = self.current_result['report']
        classes = report['classes']
        result = report['models'][key]
        matrix = result.get('confusion')
        self.percent.setEnabled(bool(matrix))
        if matrix:
            self.matrix_note.setText(tr(
                'Model for this matrix — {model}. Rows are reviewed classes. Columns are predictions.',
                model=model_display_name(self.current_result_path, key)))
            headers = [tr('Actual class'), *[_class_name(i) for i in classes],
                       tr('Test objects'), tr('Precision'), tr('Recall')]
            rows = []
            for label, counts in enumerate(matrix):
                # Rows represent actual classes. Column totals are prediction
                # counts for precision, and row totals are support for recall.
                predicted = sum(row[label] for row in matrix)
                support = sum(counts)
                cells = ([f'{100 * count / support:.1f}%' if support else '—' for count in counts]
                         if self.percent.isChecked() else counts)
                rows.append([_class_name(classes[label]), *cells, support,
                             f'{counts[label] / predicted:.3f}' if predicted else '—',
                             f'{counts[label] / support:.3f}' if support else '—'])
            _fill(self.confusion, headers, rows)
        else:
            self.matrix_note.setText(tr('No test scores are available for this evaluation.'))
            _fill(self.confusion, [], [])
        details = self._fit_summary(key, result) if key in ('tree', 'forest') else []
        self._show_tuning(key, result)
        details.append(json.dumps(result['parameters'], ensure_ascii=False, indent=2))
        for group, score in result.get('groups', {}).items():
            details.append(f"{self.report_group_names.get(group, group)} · Macro-F1 {score:.3f}")
        if result['tuning']:
            details.append(tr('Training-only K-fold'))
            details.extend(f"{candidate['macro_f1']:.3f} · {candidate['parameters']}" for candidate in result['tuning'])
        if key == 'tree':
            details.append(report['tree'])
        if result.get('permutation_importance'):
            details.append(tr('Test permutation importance · decrease in macro-F1'))
            details.extend(f"{item['feature']} · {item['mean']:.3f} ± {item['std']:.3f}"
                           for item in result['permutation_importance'])
        nodes = report.get('tree_nodes', [])
        _fill(self.tree_nodes, [tr('Node'), tr('Node depth'), tr('Rule'), tr('Yes → node'), tr('No → node'),
                                tr('Class at node'), tr('Objects'), tr('Groups'),
                                *[_class_name(i) for i in classes]],
              [(node['node'], node.get('depth', '—'),
                f"{node['feature']} ≤ {node['threshold']:.5g}" if node['feature'] else tr('Leaf'),
                '—' if node.get('left') is None else node['left'],
                '—' if node.get('right') is None else node['right'],
                _class_name(node['predicted']) if 'predicted' in node else '—',
                node['objects'], node['groups'], *[node['classes'].get(str(i), 0) for i in classes])
               for node in nodes] if key == 'tree' else [])
        self.model_details.setPlainText('\n'.join(details))
        self.reset_errors()
        self._update_table_windows()

    def show_comparison_table(self, key):
        if not self.current_result:
            return None
        if dialog := self._table_windows.get(key):
            if dialog.isMinimized():
                dialog.showNormal()
            dialog.raise_()
            dialog.activateWindow()
            return dialog

        _, source, help_key = self._comparison_tables[key]
        dialog = QtWidgets.QDialog(self)
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.resize(960, 600)
        layout = QtWidgets.QVBoxLayout(dialog)
        dialog.note = QtWidgets.QLabel()
        dialog.note.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        dialog.note.setWordWrap(True)
        layout.addWidget(dialog.note)
        # Share the item model but give the window its own selection, scroll
        # position and column widths. Report and model changes update both views.
        dialog.table = QtWidgets.QTableView()
        dialog.table.setModel(source.model())
        dialog.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        dialog.table.setAlternatingRowColors(True)
        dialog.table.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        dialog.table.verticalHeader().hide()
        _configure_comparison_view(dialog.table)
        dialog.table.resizeColumnsToContents()
        layout.addWidget(attach_help(dialog.table, help_key), 1)
        if key == 'confusion':
            percent = QtWidgets.QCheckBox(tr('Row percentages'))
            percent.setChecked(self.percent.isChecked())
            percent.toggled.connect(self.percent.setChecked)
            self.percent.toggled.connect(percent.setChecked)
            dialog.percent = percent
            layout.addWidget(attach_help(percent, help_key))
            dialog.table.clicked.connect(self._open_comparison_cell)
        elif key == 'errors':
            dialog.table.activated.connect(lambda index: self.open_error(index.row(), index.column(), parent=dialog))
        if hasattr(self.window, 'show_help'):
            shortcut = QtGui.QShortcut(QtGui.QKeySequence('F1'), dialog)
            shortcut.activated.connect(lambda: self.window.show_help(help_key))
        dialog.finished.connect(lambda _result: self._table_windows.pop(key, None))
        self._table_windows[key] = dialog
        self._update_table_windows()
        show_centered_window(dialog)
        return dialog

    def _update_table_windows(self):
        for key, dialog in self._table_windows.items():
            title = tr(self._comparison_tables[key][0])
            if self.current_result_path:
                title += ' — ' + self.current_result_path.parent.name
                if key != 'metrics' and self.models.currentText():
                    title += ' · ' + self.models.currentText()
            dialog.setWindowTitle(title)
            note = ''
            if key == 'confusion':
                note = self.matrix_note.text()
                dialog.percent.setEnabled(self.percent.isEnabled())
            elif key == 'tuning':
                note = self.tuning_note.text()
            dialog.note.setText(note)
            dialog.note.setVisible(bool(note))

    def _open_comparison_cell(self, index):
        if self.filter_errors(index.row(), index.column()):
            self.show_comparison_table('errors')

    def _show_tuning(self, key, result):
        trials = result['tuning']
        self.tuning_note.setText(tr('Each row is a candidate. The highest pooled validation macro-F1 wins. In a tie, the first candidate wins.')
                                 if trials else tr('There are no validation trials in this report.'))
        if not trials:
            _fill(self.tuning_table, [], [])
            return
        winner = max(range(len(trials)), key=lambda index: trials[index]['macro_f1'])
        folds = len(trials[0].get('fold_macro_f1', ()))
        headers = [tr('Selected'), tr('Split criterion'), tr('Depth limit'), tr('Minimum leaf size')]
        if key == 'forest':
            headers.append(tr('Features per split'))
        headers += [tr('Pooled macro-F1'), *[tr('Fold {number}', number=i + 1) for i in range(folds)]]
        rows = []
        for index, trial in enumerate(trials):
            params = trial['parameters']
            row = [tr('Yes') if index == winner else '', tr('Entropy') if params.get('criterion') == 'entropy' else 'Gini',
                   tr('No preset limit') if params['max_depth'] is None else params['max_depth'],
                   params['min_samples_leaf']]
            if key == 'forest':
                features = params.get('max_features', '—')
                row.append(tr('All predictors') if features is None else features)
            rows.append([*row, f"{trial['macro_f1']:.6f}", *[f'{score:.6f}' for score in trial.get('fold_macro_f1', ())]])
        _fill(self.tuning_table, headers, rows)
        self.tuning_table.selectRow(winner)

    def rename_selected_model(self):
        if self._busy or self._model_artifact() is None:
            return
        key = self.models.currentData()
        title = tr('Rename selected model…')
        name, accepted = QtWidgets.QInputDialog.getText(
            self, title, tr('Display name (up to 80 characters). Leave blank to reset.'),
            text=model_alias(self.current_result_path, key))
        if accepted:
            try:
                save_model_name(self.current_result_path, key, name)
            except OSError as error:
                QtWidgets.QMessageBox.warning(self, title, str(error))
                return
            self.show_comparison()

    @staticmethod
    def _fit_summary(key, result):
        params = result['parameters']
        depth = params.get('max_depth')
        lines = [tr('Depth limit — {depth}', depth=tr('No preset limit') if depth is None else depth)]
        criterion_names = {'gini': 'Gini', 'entropy': tr('Entropy')}
        criterion = params.get('criterion')
        if criterion in criterion_names:
            lines.append(tr('Split criterion — {criterion}', criterion=criterion_names[criterion]))
        if key == 'forest' and 'n_estimators' in params:
            lines.append(tr('Requested number of trees — {count}', count=params['n_estimators']))
        if result['tuning']:
            criterion_scores = {}
            for trial in result['tuning']:
                candidate = trial['parameters'].get('criterion')
                criterion_scores[candidate] = max(criterion_scores.get(candidate, 0), trial['macro_f1'])
            for candidate, name in criterion_names.items():
                if candidate in criterion_scores:
                    lines.append(tr('Best validation macro-F1 with {criterion} — {score:.6f}',
                                    criterion=name, score=criterion_scores[candidate]))
            score = max(trial['macro_f1'] for trial in result['tuning'])
            lines.append(tr('Selected by validation macro-F1 — {score:.6f}. The first candidate wins an exact tie.',
                            score=score))
        else:
            lines.append(tr('Cross-validation is off. Fixed settings were used.'))
        # Older evaluations remain readable without reconstructing estimates
        # or deserializing fitted estimators just to display this information.
        info = result.get('fit_info')
        if info is not None:
            if key == 'tree':
                lines.append(tr('Actual tree depth — {depth}', depth=info['depth']))
            else:
                lines.append(tr('Fitted trees — {count}. Actual depths — {minimum} to {maximum}.',
                                count=info['tree_count'], minimum=info['min_depth'], maximum=info['max_depth']))
            lines.append(tr('Final fit — {seconds:.3f} s', seconds=info['final_fit_seconds']))
            if info['cv_fit_count']:
                lines.append(tr('Tuning — {count} fits, {seconds:.3f} s of fitting in total',
                                count=info['cv_fit_count'], seconds=info['cv_fit_seconds']))
        return [*lines, '']

    def _model_artifact(self):
        key = self.models.currentData()
        if not self.current_result_path or key not in ('tree', 'forest'):
            return None
        result = self.current_result['report']['models'][key]
        filename = key + '.joblib'
        if result.get('artifact') != filename:
            return None
        path = self.current_result_path.with_name(filename)
        return path if path.is_file() else None

    def export_selected_model(self):
        source = self._model_artifact()
        if source is None:
            return
        alias = model_alias(self.current_result_path, self.models.currentData())
        filename = readable_name(alias) + '.joblib' if alias else source.name
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr('Save selected model…'), str(Path(self.window.project.workspace) / filename),
            tr('Fitted models (*.joblib)'))
        if not path:
            return
        target = Path(path)
        if target.suffix.casefold() != '.joblib':
            QtWidgets.QMessageBox.warning(self, tr('Save selected model…'), tr('Use the .joblib extension.'))
            return
        target = target.resolve()
        report_root = (Path(self.window.project.workspace) / 'model_evaluations').resolve()
        if report_root in target.parents:
            QtWidgets.QMessageBox.warning(self, tr('Save selected model…'),
                                          tr('Choose a destination outside saved evaluation folders.'))
            return
        try:
            with tempfile.TemporaryDirectory(prefix='.model_', dir=target.parent) as temp:
                staged = Path(temp) / target.name
                shutil.copyfile(source, staged)
                os.replace(staged, target)
            self.status.setText(tr('Model saved.'))
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, tr('Save selected model…'), str(exc))

    def reset_errors(self):
        self.filter_errors(-1, -1)

    def filter_errors(self, actual, column):
        # The confusion table has a label column before the predictions.
        # A selected cell takes precedence over the model comparison filter.
        if not self.current_result or not self.models.currentData():
            return
        key = self.models.currentData()
        other = self.error_filter.currentData()
        report = self.current_result['report']
        classes = report['classes']
        selected_cell = 0 <= actual < len(classes) and 1 <= column <= len(classes)
        self.error_rows = []
        for row in report['predictions']:
            predicted, truth = row['predicted'], row['target']
            if selected_cell:
                if truth != classes[actual] or predicted[key] != classes[column - 1]:
                    continue
            elif other in ('tree', 'forest'):
                wrong = 'tree' if other == 'forest' else 'forest'
                if predicted[other] != truth or predicted[wrong] == truth:
                    continue
            elif predicted[key] == truth:
                continue
            self.error_rows.append(row)
        _fill(self.errors, [tr('Group'), tr('Tile'), tr('Object'), tr('Actual class'), tr('tree'), tr('forest')],
              [(self.report_group_names.get(row['group'], row['group']), row['tile_name'], row['object_id'],
                _class_name(row['target']), _class_name(row['predicted']['tree']),
                _class_name(row['predicted']['forest'])) for row in self.error_rows])
        if selected_cell:
            self.details.setCurrentWidget(self.errors)
        return selected_cell

    def open_error(self, index, _column, *, parent=None):
        if not 0 <= index < len(self.error_rows):
            return
        row = self.error_rows[index]
        snapshot = self.current_result['snapshot']
        dataset = next(d for d in snapshot['datasets'] if d['dataset_id'] == row['dataset_id'])
        dlg = QtWidgets.QDialog(parent or self)
        dlg.setWindowTitle(tr('Object inspection'))
        dlg.resize(850, 620)
        layout = QtWidgets.QVBoxLayout(dlg)
        text = QtWidgets.QPlainTextEdit()
        text.setReadOnly(True)
        lines = [dataset['name'], dataset['measurement_reference'], row['tile_name'],
                 f"{tr('Actual class')} · {_class_name(row['target'])}"]
        lines.extend(f"{tr(key)} · {_class_name(label)}" for key, label in row['predicted'].items())
        lines.extend(f"{key} = {value:g}" for key, value in zip(snapshot['features'], row['values']))
        lines.extend(f"{node['node']} · {node['feature']} {'≤' if node['left'] else '>'} {node['threshold']:.6g}"
                     for node in row['tree_path'])
        text.setPlainText('\n'.join(lines))
        layout.addWidget(text)
        root = Path(self.window.project.workspace).resolve()
        # Look up the object crop under the report's measurement directory.
        # A newer result with the same tile and object IDs is a different crop.
        folder = (root / dataset['results_dir'] / 'verification_masks' / row['tile_name']).resolve() \
            if dataset.get('results_dir') else root
        masks = [path for path in folder.glob('obj_*.png') if root in path.resolve().parents
                 and path.stem.split('_', 2)[1].isdigit()
                 and int(path.stem.split('_', 2)[1]) == row['object_id']] if root in folder.parents else []
        if len(masks) == 1:
            from .evaluation_crops import EvaluationCrops
            viewer = ImageViewer()
            scale = EvaluationCrops(root).ruler_scale(dataset.get('results_dir'), row['tile_name'], row['object_id'])
            viewer.set_image(str(masks[0]), ruler_scale=scale)
            layout.addWidget(viewer, 1)
        else:
            layout.addWidget(QtWidgets.QLabel(tr('Saved object image unavailable.')))
        if dataset.get('results_dir'):
            tile = QtWidgets.QPushButton(tr('Open object tile'))
            tile.clicked.connect(lambda: self.open_tile(row, dlg))
            layout.addWidget(tile)
        dlg.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.open()

    def open_tile(self, row, dialog):
        from .result_tile import resolve_result_tile
        from .service import tile_records
        try:
            dataset = self.window.project.get_dataset(row['dataset_id'])
            path, space = resolve_result_tile(dataset, {'Tile_Name': row['tile_name']}, tile_records(dataset))
            ImageViewer.open_image_window(str(path), dialog, language=get_language(), caption=space, original=True)
        except (OSError, ValueError, KeyError) as exc:
            QtWidgets.QMessageBox.warning(dialog, tr('Open object tile'), str(exc))

    def show_data_charts(self):
        from .model_evaluation_charts import DataChartsDialog

        dialog = DataChartsDialog(self, self.payload, self.group_names, _class_name)
        show_centered_window(dialog)
        return dialog

    def show_split_gallery(self, payload):
        if payload and payload.get('plan'):
            project = self.window.project
            dialog = ModelSplitGallery(self, project.workspace, payload, _class_name,
                                       selected_model=self.models.currentData(), project_datasets=project.datasets,
                                       preferences=getattr(self.window, 'preferences', None))
            dialog.show()

    def show_performance_charts(self):
        from .model_evaluation_charts import PerformanceChartsDialog

        dialog = PerformanceChartsDialog(self, self.current_result['report'], _class_name)
        show_centered_window(dialog)
        return dialog
