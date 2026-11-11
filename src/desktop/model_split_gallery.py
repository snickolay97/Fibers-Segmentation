"""Read-only inspection of the objects in a frozen training plan or report."""

from .evaluation_crops import EvaluationCrops
from .i18n import register_translations, tr
from .input_safety import install_parameter_wheel_guard
from .object_review import ObjectReviewGallery
from .qt import QtCore, QtGui, QtWidgets
from .widgets import ImageViewer


_TEXT = {
    'Split gallery…': ('Галерея разбиения…', 'גלריית חלוקה…'),
    'Training objects': ('Обучающие объекты', 'עצמי אימון'),
    'Held-out test objects': ('Отложенные тестовые объекты', 'עצמים ממבחן ההחזקה'),
    'Validation fold {fold}': ('Валидация · фолд {fold}', 'תיקוף · קפל {fold}'),
    'Show reviewed class': ('Показать ручной класс', 'הצגת המחלקה הידנית'),
    'Reviewed class — {name}': ('Ручной класс — {name}', 'מחלקה ידנית — {name}'),
    'Prediction — {name}': ('Прогноз — {name}', 'תחזית — {name}'),
    'Training cards show the reviewed class used to fit the model.': (
        'На обучающих карточках указан ручной класс, который используется для обучения.',
        'כרטיסי האימון מציגים את המחלקה הידנית ששימשה לאימון המודל.'),
    'Test cards show the selected model’s prediction. The reviewed class is used for scoring.': (
        'На тестовых карточках указан прогноз выбранной модели. Ручной класс используется для подсчёта метрик.',
        'כרטיסי המבחן מציגים את תחזית המודל שנבחר. המחלקה הידנית משמשת לחישוב הציונים.'),
    'This preview contains test membership. Predictions are available after fitting.': (
        'Здесь видно, какие объекты попадут в тест. Прогнозы появятся после обучения.',
        'בתצוגה זו אפשר לראות אילו עצמים ייכללו במבחן. התחזיות זמינות לאחר האימון.'),
    'A validation fold is taken from the training partition for model selection. Individual fold predictions are not saved.': (
        'Фолд валидации берётся из обучающей выборки для подбора модели. Отдельные прогнозы по фолдам не сохраняются.',
        'קפל התיקוף נלקח מחלק האימון לבחירת המודל. התחזיות לכל עצם בקפלי התיקוף אינן נשמרות.'),
    'This CSV or Excel snapshot contains features and labels without images.': (
        'Для строк Excel или CSV без совпавшей версии измерений доступны только данные.',
        'לשורות Excel או CSV ללא גרסת מדידה תואמת מוצגים רק נתונים.'),
    'Images are loaded from the measurement version verified against this table.': (
        'Изображения открываются из версии измерений, сверенной с этой таблицей.',
        'התמונות נטענות מגרסת המדידה שאומתה מול הטבלה הזאת.'),
    'No verified project measurement for this row.': (
        'Для этой строки нет подтверждённой версии измерений проекта.',
        'לא נמצאה גרסת מדידה מאומתת בפרויקט לשורה זו.'),
    'No objects in this partition.': ('В этой части нет объектов.', 'אין עצמים בחלק זה.'),
    'Exact saved mask': ('Точная сохранённая маска', 'מסכה מדויקת שמורה'),
    'Saved review crop': ('Сохранённый контрольный фрагмент', 'חיתוך ביקורת שמור'),
    'Inspect a split without changing classes': (
        'Просмотр разбиения без изменения классов', 'בדיקת חלוקה ללא שינוי מחלקות'),
}
register_translations({key: values[0] for key, values in _TEXT.items()},
                      hebrew={key: values[1] for key, values in _TEXT.items()})

def _identity(row):
    return row['dataset_id'], row['tile_name'], row['object_id']


class _SplitCards(ObjectReviewGallery):
    def __init__(self, resolve, table_only):
        self._resolve = resolve
        self.table_only = table_only
        super().__init__(thumbnail_size=124)
        self.hint.hide()
        self.summary.hide()
        self.unclassified_only.hide()
        for _, badge, _ in self._help_badges:
            badge.hide()
        if table_only:
            self.view.setViewMode(QtWidgets.QListView.ViewMode.ListMode)
            self.view.setFlow(QtWidgets.QListView.Flow.TopToBottom)
            self.view.setWrapping(False)
            self.view.setGridSize(QtCore.QSize())
            self.view.setItemDelegate(QtWidgets.QStyledItemDelegate(self.view))

    def _manual_class(self, row):
        # The badge is view-only. Its content follows the partition's caption.
        return row['Card_Class']

    def _class_name(self, key):
        return key or '—'

    def _thumbnail(self, key):
        return None if self.table_only else super()._thumbnail(key)

    def _thumbnail_path(self, key):
        path, _ = self._resolve(self._rows_by_key[key])
        return path


class ModelSplitGallery(QtWidgets.QDialog):
    """Browse captured memberships and classes without reopening live labels."""

    def __init__(self, parent, workspace, payload, class_name, selected_model=None,
                 *, project_datasets=(), preferences=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Split gallery…'))
        self.resize(1020, 700)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.WindowMinMaxButtonsHint)
        self.setSizeGripEnabled(True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self._preferences = preferences
        self._help_center = None
        snapshot, plan = payload['snapshot'], payload['plan']
        self._rows = snapshot['rows']
        self._features = snapshot['features']
        self._datasets = {entry['dataset_id']: entry for entry in snapshot['datasets']}
        self._parts = {'train': plan['train'], 'test': plan['test']}
        self._parts.update({number: fold['test'] for number, fold in enumerate(plan['folds'], 1)})
        report = payload.get('report', {})
        # Saved predictions follow the test-index order. The index also
        # distinguishes imported table rows without unique object identifiers.
        self._predictions = {index: row['predicted']
                             for index, row in zip(plan['test'], report.get('predictions', ()))
                             if _identity(self._rows[index]) == _identity(row)}
        self._class_name = class_name
        self._crops = EvaluationCrops(workspace)
        self._from_table = not any(entry.get('results_dir') for entry in self._datasets.values())
        self._table_paths = {}
        if self._from_table:
            references = [entry.get('measurement_reference') for entry in self._datasets.values()]
            measurements = self._crops.table_measurements(references, project_datasets)
            self._table_paths = self._crops.table_object_paths(snapshot, measurements)
        self.table_only = self._from_table and not self._table_paths
        self._synthetic_offset = max((row['object_id'] for row in self._rows), default=0) if self._table_paths else 0
        self._selected = None

        layout = QtWidgets.QVBoxLayout(self)
        controls = QtWidgets.QHBoxLayout()
        self.part = QtWidgets.QComboBox()
        for key, indices in self._parts.items():
            title = (tr('Training objects') if key == 'train' else tr('Held-out test objects') if key == 'test'
                     else tr('Validation fold {fold}', fold=key))
            self.part.addItem(f'{title} ({len(indices)})', key)
        self.dataset = QtWidgets.QComboBox()
        self.model = QtWidgets.QComboBox()
        for key in report.get('models', {}):
            self.model.addItem(tr(key), key)
        self.model.setCurrentIndex(max(0, self.model.findData(selected_model)))
        self.reveal = QtWidgets.QCheckBox(tr('Show reviewed class'))
        help_button = QtWidgets.QPushButton('?')
        help_button.setAccessibleName(tr('Inspect a split without changing classes'))
        help_button.clicked.connect(self.show_help)
        controls.addWidget(self.part)
        controls.addWidget(self.dataset, 1)
        controls.addWidget(self.model)
        controls.addWidget(help_button)
        layout.addLayout(controls)
        self.info = QtWidgets.QLabel()
        self.info.setWordWrap(True)
        layout.addWidget(self.info)

        self.cards = _SplitCards(self._resolve, self.table_only)
        navigation = QtWidgets.QHBoxLayout()
        self.previous_button = QtWidgets.QPushButton('←')
        self.next_button = QtWidgets.QPushButton('→')
        self._arrow_shortcuts = []
        for button, direction, label, key in (
            (self.previous_button, 'previous', 'Previous', 'Left'),
            (self.next_button, 'next', 'Next', 'Right'),
        ):
            button.setToolTip(tr(label))
            button.setAccessibleName(tr(label))
            button.setAutoDefault(False)
            button.clicked.connect(lambda _checked=False, step=direction: self.cards.navigate(step))
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(key), self)
            shortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(button.click)
            self._arrow_shortcuts.append(shortcut)
            navigation.addWidget(button)
        self.position = QtWidgets.QLabel()
        self.position.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        navigation.addWidget(self.position)
        navigation.addStretch()
        navigation.addWidget(self.reveal)
        layout.addLayout(navigation)
        self.detail = QtWidgets.QLabel()
        self.detail.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.detail.setWordWrap(True)
        self.image = ImageViewer()
        self.image.view.setBackgroundBrush(QtGui.QColor('#34454d'))
        scroll = QtWidgets.QScrollArea()
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        self.detail.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.detail)
        self.detail_split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.detail_split.addWidget(scroll)
        self.detail_split.addWidget(self.image)
        self.detail_split.setChildrenCollapsible(False)
        self.detail_split.setStretchFactor(1, 1)
        self.detail_split.setSizes([190, 420])
        self.gallery_split = QtWidgets.QSplitter()
        self.gallery_split.addWidget(self.cards)
        self.gallery_split.addWidget(self.detail_split)
        self.gallery_split.setChildrenCollapsible(False)
        self.gallery_split.setSizes([440, 555])
        layout.addWidget(self.gallery_split, 1)
        if preferences is not None:
            geometry = preferences.value('split_gallery/geometry')
            if isinstance(geometry, QtCore.QByteArray):
                self.restoreGeometry(geometry)
            for key, splitter in (('widths', self.gallery_split), ('heights', self.detail_split)):
                state = preferences.value('split_gallery/' + key)
                if isinstance(state, QtCore.QByteArray):
                    splitter.restoreState(state)

        self.part.currentIndexChanged.connect(self._change_partition)
        self.dataset.currentIndexChanged.connect(self._show_rows)
        self.model.currentIndexChanged.connect(self._show_rows)
        self.reveal.toggled.connect(self._show_detail)
        self.cards.row_selected.connect(self._select)
        self.cards.selection_cleared.connect(lambda: self._select(None))
        self.cards.search.textChanged.connect(self._update_navigation)
        self.cards.tile_filter.currentIndexChanged.connect(self._update_navigation)
        QtWidgets.QApplication.instance().focusChanged.connect(self._focus_changed)
        shortcut = QtGui.QShortcut(QtGui.QKeySequence('F1'), self)
        shortcut.activated.connect(self.show_help)
        install_parameter_wheel_guard(self)
        self._change_partition()
        self.cards.view.setFocus()

    def _focus_changed(self, _old, focus):
        # Leave arrow keys with search and selectors while those controls have focus.
        editing = isinstance(focus, (QtWidgets.QLineEdit, QtWidgets.QComboBox, QtWidgets.QAbstractSpinBox))
        for shortcut in self._arrow_shortcuts:
            shortcut.setEnabled(not editing)

    def _update_navigation(self, *_):
        count = len(self.cards.visible_rows)
        index = self.cards.view.currentIndex().row() if self._selected is not None else -1
        self.position.setText(f'{index + 1} / {count}')
        self.previous_button.setEnabled(index > 0)
        self.next_button.setEnabled(index + 1 < count)

    def show_help(self):
        from .help_center import HelpCenter
        if self._help_center is None:
            self._help_center = HelpCenter(parent=self)
        self._help_center.open_topic('evaluation_gallery')
        self._help_center.raise_()

    def _measurement_dir(self, card):
        row = card['Snapshot_Row']
        return (self._table_paths.get(card['Snapshot_Index']) if self._from_table
                else self._datasets[row['dataset_id']].get('results_dir'))

    def _resolve(self, card):
        row = card['Snapshot_Row']
        return self._crops.resolve(self._measurement_dir(card), row['tile_name'], row['object_id'])

    def _change_partition(self, *_):
        part = self.part.currentData()
        previous = self.dataset.currentData()
        ids = dict.fromkeys(self._rows[index]['dataset_id'] for index in self._parts[part])
        with QtCore.QSignalBlocker(self.dataset), QtCore.QSignalBlocker(self.reveal):
            self.dataset.clear()
            for ident in ids:
                self.dataset.addItem(self._datasets[ident]['name'], ident)
            self.dataset.setCurrentIndex(max(0, self.dataset.findData(previous)))
            self.reveal.setChecked(False)
        self.model.setVisible(part == 'test' and bool(self._predictions))
        self.reveal.setVisible(part != 'train')
        self._show_rows()

    def _prediction(self, index):
        return self._predictions.get(index, {}).get(self.model.currentData())

    def _show_rows(self, *_):
        part, ident = self.part.currentData(), self.dataset.currentData()
        previous = self._selected
        rows = []
        for index in self._parts[part]:
            row = self._rows[index]
            if row['dataset_id'] != ident:
                continue
            label = row['target'] if part == 'train' else self._prediction(index) if part == 'test' else None
            # Imported tables can omit tile names or contain non-project IDs.
            # Use a unique display index while retaining their raw identifiers.
            tile, object_id = row['tile_name'], row['object_id']
            if self._from_table and index not in self._table_paths:
                tile = tile.translate(str.maketrans('/\\:', '___')) or '—'
                tile = '—' if tile in ('.', '..') else tile
                object_id = self._synthetic_offset + index + 1
            rows.append(dict(Tile_Name=tile, Object_ID=object_id, Snapshot_Index=index, Snapshot_Row=row,
                             Card_Class=self._class_name(label) if label is not None else None))
        if part == 'train':
            caption = tr('Training cards show the reviewed class used to fit the model.')
        elif part == 'test':
            caption = (tr('Test cards show the selected model’s prediction. The reviewed class is used for scoring.')
                       if self._predictions else tr('This preview contains test membership. Predictions are available after fitting.'))
        else:
            caption = tr('A validation fold is taken from the training partition for model selection. Individual fold predictions are not saved.')
        if self.table_only:
            caption += ' ' + tr('This CSV or Excel snapshot contains features and labels without images.')
        elif self._from_table:
            caption += ' ' + tr('Images are loaded from the measurement version verified against this table.')
        if not rows:
            caption += ' ' + tr('No objects in this partition.')
        self.info.setText(caption)
        self._select(None)
        self.cards.set_rows(rows, None)
        previous_card = next((card for card in rows if previous is not None
                              and card['Snapshot_Index'] == previous['Snapshot_Index']), None)
        if previous_card is not None and self.cards.select_object(previous_card['Tile_Name'], previous_card['Object_ID']):
            return
        self.cards.navigate('next')
        self._update_navigation()

    def _select(self, card):
        self._selected = card
        self._update_navigation()
        self._show_detail()

    def _show_detail(self, *_):
        if self._selected is None:
            self.detail.clear()
            self.image.clear()
            return
        row = self._selected['Snapshot_Row']
        labels = [f"{row['tile_name']} · #{row['object_id']}"]
        part = self.part.currentData()
        if part == 'train' or self.reveal.isChecked():
            labels.append(tr('Reviewed class — {name}', name=self._class_name(row['target'])))
        if part == 'test':
            prediction = self._prediction(self._selected['Snapshot_Index'])
            if prediction is not None:
                labels.append(tr('Prediction — {name}', name=self._class_name(prediction)))
        labels.extend(f'{feature} = {value:g}' for feature, value in zip(self._features, row['values']))
        self.detail.setText('\n'.join(labels))
        path, kind = self._resolve(self._selected)
        if path is None:
            self.image.clear(tr('No verified project measurement for this row.')
                             if self._from_table and self._selected['Snapshot_Index'] not in self._table_paths
                             else 'Saved object image unavailable.')
        elif str(path) != self.image.filename:
            scale = self._crops.ruler_scale(self._measurement_dir(self._selected), row['tile_name'], row['object_id'])
            self.image.set_image(str(path), tr('Exact saved mask' if kind == 'exact' else 'Saved review crop'),
                                 ruler_scale=scale)

    def closeEvent(self, event):
        if self._preferences is not None:
            self._preferences.setValue('split_gallery/geometry', self.saveGeometry())
            self._preferences.setValue('split_gallery/widths', self.gallery_split.saveState())
            self._preferences.setValue('split_gallery/heights', self.detail_split.saveState())
        self.cards.dispose()
        self.image.clear()
        super().closeEvent(event)
