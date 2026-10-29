"""Bounded, read-only contact sheet of saved object verification crops.

Current CSVs do not contain object bounding boxes in their native tile. This
widget therefore displays the actual saved local crops, without guessing a
segmentation overlay or a source-image hit map.
"""
from collections import OrderedDict
from pathlib import Path
import re

from .qt import QtCore, QtGui, QtWidgets, Signal
from .i18n import tr, get_language, register_translations
from .object_labels import CANONICAL_MANUAL_CLASSES, object_key
from .widgets import image_pool


register_translations({
    'Object gallery': 'Галерея объектов',
    'All tiles': 'Все тайлы',
    'Search objects or classes': 'Поиск объектов или классов',
    'Unclassified only': 'Только без класса',
    'Saved object crops — select a card to inspect and classify':
        'Сохранённые фрагменты объектов — выберите карточку для проверки и разметки',
    'No objects match these filters': 'По заданным фильтрам объектов нет',
    'No measured objects': 'Нет измеренных объектов',
    'Object image is unavailable': 'Изображение объекта недоступно',
    'Large object: select it to open the detailed preview':
        'Крупный объект: выберите его для подробного просмотра',
    'Object {object} · {class_name}': 'Объект {object} · {class_name}',
    'Show crops from one tile, or review all tiles together.':
        'Показывать фрагменты одного тайла или проверять все тайлы вместе.',
    'Search by tile name, object ID, or assigned class. This does not change saved data.':
        'Поиск по имени тайла, ID объекта или присвоенному классу. Сохранённые данные не меняются.',
    'Hide objects with an assigned class. After assignment, the next visible object is selected.':
        'Скрыть объекты с присвоенным классом. После назначения выбирается следующий видимый объект.',
    '{visible} / {total} objects · {assigned} classified':
        '{visible} / {total} объектов · с классом: {assigned}',
})


class _ThumbnailSignals(QtCore.QObject):
    done = Signal(int, str, object, str)


class _ThumbnailTask(QtCore.QRunnable):
    """Decode one crop off the GUI thread, with explicit native-size bounds."""
    def __init__(self, token, key, path, maximum, max_source_pixels):
        super().__init__()
        self.token, self.key, self.path = token, key, str(path)
        self.maximum, self.max_source_pixels = maximum, max_source_pixels
        self.cancelled = False
        self.signals = _ThumbnailSignals()

    def run(self):
        image, error = None, ''
        try:
            if self.cancelled:
                error = 'cancelled'
            else:
                reader = QtGui.QImageReader(self.path)
                size = reader.size()
                if not size.isValid() or size.width() <= 0 or size.height() <= 0:
                    error = 'missing'
                elif size.width()*size.height() > self.max_source_pixels:
                    # PNG decoders may allocate native pixels even when scaled
                    # reading is requested. The gallery never decodes huge
                    # crops; the selected-object viewer remains available.
                    error = 'large'
                else:
                    reader.setAutoTransform(True)
                    reader.setScaledSize(size.scaled(self.maximum, QtCore.Qt.AspectRatioMode.KeepAspectRatio))
                    result = reader.read()
                    if result.isNull():
                        error = 'missing'
                    elif not self.cancelled:
                        image = result.scaled(self.maximum, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                              QtCore.Qt.TransformationMode.SmoothTransformation)
                    else:
                        error = 'cancelled'
        except Exception:
            error = 'missing'
        self.signals.done.emit(self.token, self.key, image, error)


class _GalleryModel(QtCore.QAbstractListModel):
    def __init__(self, gallery):
        super().__init__(gallery)
        self.gallery = gallery

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.gallery.visible_rows)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.gallery.visible_rows):
            return None
        gallery = self.gallery
        row = gallery.visible_rows[index.row()]
        key = gallery._key(row)
        if role == QtCore.Qt.ItemDataRole.UserRole:
            return gallery._display_row(row)
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return gallery._text('Object {object} · {class_name}', object=row.get('Object_ID', ''),
                                 class_name=gallery._class_name(gallery._manual_class(row))) + '\n' + str(row.get('Tile_Name', ''))
        if role == QtCore.Qt.ItemDataRole.DecorationRole:
            return gallery._thumbnail(key)
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            caption = str(row.get('Tile_Name', '')) + '\n' + gallery._text('Object {object} · {class_name}',
                object=row.get('Object_ID', ''), class_name=gallery._class_name(gallery._manual_class(row)))
            entry = gallery._cache.get(key)
            if entry and entry[1]:
                caption += '\n' + gallery._text('Large object: select it to open the detailed preview' if entry[1] == 'large' else 'Object image is unavailable')
            return caption
        if role == QtCore.Qt.ItemDataRole.ForegroundRole and gallery._manual_class(row):
            return QtGui.QBrush(QtGui.QColor('#20a585'))
        return None


class _ObjectCardDelegate(QtWidgets.QStyledItemDelegate):
    """Place bounded thumbnails and captions independently of global QSS."""
    def __init__(self, gallery):
        super().__init__(gallery.view)
        self.gallery = gallery

    def sizeHint(self, _option, _index):
        return QtCore.QSize(self.gallery._maximum.width()+42, self.gallery._maximum.height()+66)

    def paint(self, painter, option, index):
        gallery = self.gallery
        row = gallery.visible_rows[index.row()]
        card = option.rect.adjusted(4,4,-4,-4)
        selected = bool(option.state & QtWidgets.QStyle.StateFlag.State_Selected)
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        base = option.palette.color(QtGui.QPalette.ColorRole.Base)
        accent = option.palette.color(QtGui.QPalette.ColorRole.Highlight)
        edge = accent if selected else option.palette.color(QtGui.QPalette.ColorRole.Mid)
        painter.setPen(QtGui.QPen(edge, 3 if selected else 1))
        painter.setBrush(base)
        painter.drawRoundedRect(QtCore.QRectF(card),7,7)
        image_rect = QtCore.QRect(card.left()+10, card.top()+8, card.width()-20, gallery._maximum.height())
        icon = index.data(QtCore.Qt.ItemDataRole.DecorationRole)
        if isinstance(icon, QtGui.QIcon):
            icon.paint(painter, image_rect, QtCore.Qt.AlignmentFlag.AlignCenter, QtGui.QIcon.Mode.Normal)
        caption = QtCore.QRect(card.left()+9, card.bottom()-43, card.width()-18,22)
        text = option.palette.color(QtGui.QPalette.ColorRole.Text)
        painter.setPen(text)
        font = QtGui.QFont(option.font)
        font.setBold(True)
        painter.setFont(font)
        metrics = QtGui.QFontMetrics(font)
        ident = '#' + str(row.get('Object_ID',''))
        id_width = min(caption.width()//2, metrics.horizontalAdvance(ident)+8)
        painter.drawText(QtCore.QRect(caption.left(),caption.top(),id_width,caption.height()),
                         QtCore.Qt.AlignmentFlag.AlignLeft|QtCore.Qt.AlignmentFlag.AlignVCenter,ident)
        badge = QtCore.QRect(caption.left()+id_width,caption.top(),max(1,caption.width()-id_width),caption.height())
        assigned = bool(gallery._manual_class(row))
        badge_color = QtGui.QColor(accent if assigned else option.palette.color(QtGui.QPalette.ColorRole.AlternateBase))
        if assigned:
            badge_color.setAlpha(35)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(badge_color)
        painter.drawRoundedRect(QtCore.QRectF(badge),4,4)
        painter.setFont(option.font)
        painter.setPen(text)
        metrics = QtGui.QFontMetrics(option.font)
        name = metrics.elidedText(gallery._class_name(gallery._manual_class(row)),
                                   QtCore.Qt.TextElideMode.ElideRight,max(1,badge.width()-8))
        painter.drawText(badge.adjusted(4,0,-4,0),
                         QtCore.Qt.AlignmentFlag.AlignLeft|QtCore.Qt.AlignmentFlag.AlignVCenter,name)
        tile_rect = QtCore.QRect(card.left()+9,card.bottom()-20,card.width()-18,18)
        tile = metrics.elidedText(str(row.get('Tile_Name','')),QtCore.Qt.TextElideMode.ElideMiddle,tile_rect.width())
        painter.drawText(tile_rect,QtCore.Qt.AlignmentFlag.AlignLeft|QtCore.Qt.AlignmentFlag.AlignVCenter,tile)
        painter.restore()


class ObjectReviewGallery(QtWidgets.QWidget):
    row_selected = Signal(object)
    selection_cleared = Signal()
    thumbnail_loaded = Signal(str, bool)

    def __init__(self, parent=None, thumbnail_size=144, cache_limit=192, max_source_pixels=4_000_000):
        super().__init__(parent)
        self.language = get_language()
        self.rows, self.visible_rows = [], []
        self.dataset = None
        self._rows_by_key, self._visible_indexes = {}, {}
        self._labels, self._labels_supplied = {}, False
        self._cache = OrderedDict()
        self._cache_limit = max(1, int(cache_limit))
        self._maximum = QtCore.QSize(max(32, int(thumbnail_size)), max(32, int(thumbnail_size)))
        self._max_source_pixels = max(1, int(max_source_pixels))
        self._max_pending = 8
        self._tasks, self._tile_paths = {}, {}
        self._token, self._disposed = 0, False
        self._selected_key = None
        self._selection_guard = False
        self._ensure_selection_pending = False
        self.tile_filter = QtWidgets.QComboBox()
        self.tile_filter.setMinimumContentsLength(12)
        self.tile_filter.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.search = QtWidgets.QLineEdit()
        self.unclassified_only = QtWidgets.QCheckBox()
        self.summary = QtWidgets.QLabel()
        self.summary.setWordWrap(True)
        self.summary.setObjectName('muted')
        self.hint = QtWidgets.QLabel()
        self.hint.setWordWrap(True)
        self.hint.setObjectName('muted')
        self.view = QtWidgets.QListView()
        self.view.setObjectName('objectReviewGallery')
        self.view.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self.view.setFlow(QtWidgets.QListView.Flow.LeftToRight)
        self.view.setWrapping(True)
        self.view.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.view.setMovement(QtWidgets.QListView.Movement.Static)
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setUniformItemSizes(True)
        self.view.setIconSize(self._maximum)
        self.view.setGridSize(QtCore.QSize(self._maximum.width()+42, self._maximum.height()+66))
        self.view.setSpacing(5)
        self.view.setWordWrap(True)
        self.view.setTextElideMode(QtCore.Qt.TextElideMode.ElideMiddle)
        self.view.setLayoutMode(QtWidgets.QListView.LayoutMode.Batched)
        self.view.setBatchSize(120)
        self.view.viewport().installEventFilter(self)
        self.view.installEventFilter(self)
        self._model = _GalleryModel(self)
        self.view.setModel(self._model)
        self.view.setItemDelegate(_ObjectCardDelegate(self))
        self.view.selectionModel().currentChanged.connect(self._current_changed)
        self.tile_filter.currentIndexChanged.connect(self.apply_filter)
        self.search.textChanged.connect(self.apply_filter)
        self.unclassified_only.toggled.connect(self.apply_filter)
        self._help_badges = []
        line = QtWidgets.QHBoxLayout()
        line.addWidget(self.tile_filter,1)
        line.addWidget(self._help(self.tile_filter, 'Show crops from one tile, or review all tiles together.'))
        line.addWidget(self.unclassified_only)
        line.addWidget(self._help(self.unclassified_only, 'Hide objects with an assigned class. After assignment, the next visible object is selected.'))
        search_line = QtWidgets.QHBoxLayout()
        search_line.addWidget(self.search,1)
        search_line.addWidget(self._help(self.search, 'Search by tile name, object ID, or assigned class. This does not change saved data.'))
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(line)
        layout.addLayout(search_line)
        layout.addWidget(self.summary)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.hint)
        self._placeholder = self._placeholder_icon()
        self.retranslate(self.language)

    def _text(self, text, **values):
        return tr(text, language=self.language, **values)

    def _help(self, widget, text):
        badge = QtWidgets.QLabel('?')
        badge.setObjectName('helpBadge')
        badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(20,20)
        badge.setCursor(QtCore.Qt.CursorShape.WhatsThisCursor)
        self._help_badges.append((widget, badge, text))
        return badge

    @staticmethod
    def _key(row):
        return object_key(row.get('Tile_Name'), row.get('Object_ID'))

    def _class_name(self, key):
        entry = next((item for item in CANONICAL_MANUAL_CLASSES if item['key'] == key), None)
        return self._text(entry['label_en']) if entry else self._text('Unclassified')

    def _manual_class(self, row):
        if self._labels_supplied:
            return self._labels.get(self._key(row), {}).get('Manual_Class') or None
        return row.get('Manual_Class') or None

    def _display_row(self, row):
        result = dict(row)
        if self._labels_supplied:
            result.update(Manual_Class_ID='', Manual_Class='', Reviewed=False)
            label = self._labels.get(self._key(row), {})
            result.update({name:label[name] for name in ('Manual_Class_ID', 'Manual_Class', 'Reviewed') if name in label})
        return result

    def retranslate(self, language=None):
        self.language = language or get_language()
        chosen = self.tile_filter.currentData()
        self.tile_filter.blockSignals(True)
        self.tile_filter.clear()
        self.tile_filter.addItem(self._text('All tiles'), None)
        counts = {}
        for row in self.rows:
            name = str(row.get('Tile_Name', ''))
            counts[name] = counts.get(name, 0)+1
        for name, count in sorted(counts.items()):
            self.tile_filter.addItem(name + ' (' + str(count) + ')', name)
        self.tile_filter.setCurrentIndex(max(0, self.tile_filter.findData(chosen)))
        self.tile_filter.blockSignals(False)
        self.search.setPlaceholderText(self._text('Search objects or classes'))
        self.unclassified_only.setText(self._text('Unclassified only'))
        for widget, badge, text in self._help_badges:
            widget.setToolTip(self._text(text))
            badge.setToolTip(self._text(text))
            badge.setWhatsThis(self._text(text))
        self.hint.setText(self._text('Saved object crops — select a card to inspect and classify'))
        self.apply_filter()

    def set_rows(self, rows, dataset):
        copied = [dict(row) for row in rows]
        indexed = {}
        for row in copied:
            key = self._key(row)
            if key in indexed:
                raise ValueError('Duplicate object identity in gallery: ' + key)
            indexed[key] = row
        self.dispose()
        self._disposed = False
        self._token += 1
        self._cache.clear()
        self._tile_paths.clear()
        self._selected_key = None
        self._labels, self._labels_supplied = {}, False
        self.dataset = dict(dataset) if dataset is not None else None
        self.rows, self._rows_by_key = copied, indexed
        self.retranslate()

    def set_manual_labels(self, report_or_labels):
        report = report_or_labels or {}
        values = report.get('labels', report)
        self._labels = {key:dict(value) for key, value in values.items() if isinstance(value, dict)}
        self._labels_supplied = True
        self.apply_filter()

    def filter_state(self):
        return dict(tile=self.tile_filter.currentData(), search=self.search.text(),
                    unclassified=self.unclassified_only.isChecked())

    def set_filter_state(self, state):
        state = state or {}
        for widget in (self.tile_filter, self.search, self.unclassified_only):
            widget.blockSignals(True)
        self.tile_filter.setCurrentIndex(max(0, self.tile_filter.findData(state.get('tile'))))
        self.search.setText(str(state.get('search') or ''))
        self.unclassified_only.setChecked(bool(state.get('unclassified')))
        for widget in (self.tile_filter, self.search, self.unclassified_only):
            widget.blockSignals(False)
        self.apply_filter()

    def apply_filter(self, *_args):
        prior_key = self._selected_key
        had_visible = bool(self.visible_rows)
        prior_position = self._visible_indexes.get(prior_key, 0)
        tile, query = self.tile_filter.currentData(), self.search.text().strip().casefold()
        def matches(row):
            manual = self._manual_class(row)
            if tile is not None and row.get('Tile_Name') != tile:
                return False
            if self.unclassified_only.isChecked() and manual:
                return False
            words = str(row.get('Tile_Name', '')) + ' ' + str(row.get('Object_ID', ''))
            words += ' ' + str(manual or '') + ' ' + self._class_name(manual)
            return not query or query in words.casefold()
        visible = [row for row in self.rows if matches(row)]
        self._selection_guard = True
        self._model.beginResetModel()
        self.visible_rows = visible
        self._visible_indexes = {self._key(row):index for index, row in enumerate(visible)}
        self._model.endResetModel()
        self._selected_key = None
        self._selection_guard = False
        assigned = sum(bool(self._manual_class(row)) for row in self.rows)
        self.summary.setText(self._text('{visible} / {total} objects · {assigned} classified',
                                        visible=len(visible), total=len(self.rows), assigned=assigned))
        if not visible:
            self.hint.setText(self._text('No objects match these filters' if self.rows else 'No measured objects'))
        else:
            self.hint.setText(self._text('Saved object crops — select a card to inspect and classify'))
        if prior_key in self._visible_indexes:
            row = visible[self._visible_indexes[prior_key]]
            self.select_object(row['Tile_Name'], row['Object_ID'])
        elif prior_key is not None and visible:
            row = visible[min(prior_position, len(visible)-1)]
            self.select_object(row['Tile_Name'], row['Object_ID'])
        elif not visible and (prior_key is not None or had_visible):
            self.selection_cleared.emit()
        self.view.viewport().update()

    def selected_row(self):
        row = self._rows_by_key.get(self._selected_key)
        return self._display_row(row) if row is not None else None

    def select_object(self, tile_name, object_id):
        key = object_key(tile_name, object_id)
        position = self._visible_indexes.get(key)
        if position is None:
            return False
        index = self._model.index(position, 0)
        self.view.setCurrentIndex(index)
        self.view.scrollTo(index, QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible)
        if self._selected_key != key:
            self._current_changed(index, QtCore.QModelIndex())
        self._schedule_selection_visibility()
        return True

    def _schedule_selection_visibility(self):
        if self._disposed or self._selected_key is None or self._ensure_selection_pending:
            return
        self._ensure_selection_pending = True
        QtCore.QTimer.singleShot(0, self.ensure_selection_visible)

    def ensure_selection_visible(self):
        """Resolve card geometry after deferred dock/viewport column changes."""
        self._ensure_selection_pending = False
        if self._disposed or self._selected_key is None:
            return
        position = self._visible_indexes.get(self._selected_key)
        if position is None:
            return
        try:
            self.view.doItemsLayout()
            self.view.scrollTo(self._model.index(position,0),QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible)
        except RuntimeError:
            # A pending timer may outlive an old workspace during language
            # reconstruction. Never access that workspace's deleted Qt view.
            return

    def _current_changed(self, index, _previous):
        if self._selection_guard:
            return
        if index.isValid() and 0 <= index.row() < len(self.visible_rows):
            row = self.visible_rows[index.row()]
            self._selected_key = self._key(row)
            self.row_selected.emit(self._display_row(row))
        else:
            self._selected_key = None

    def navigate(self, direction):
        if direction not in ('previous', 'next', 'unlabeled'):
            raise ValueError('Unknown gallery navigation direction')
        if not self.visible_rows:
            return None
        position = self._visible_indexes.get(self._selected_key, -1)
        if direction == 'unlabeled':
            order = list(range(position+1, len(self.visible_rows))) + list(range(0, position+1))
            chosen = next((i for i in order if not self._manual_class(self.visible_rows[i])), None)
            if chosen is None:
                return None
        else:
            chosen = 0 if position < 0 else max(0, min(len(self.visible_rows)-1,
                                                       position+(-1 if direction == 'previous' else 1)))
        row = self.visible_rows[chosen]
        self.select_object(row['Tile_Name'], row['Object_ID'])
        return self._display_row(row)

    def eventFilter(self, watched, event):
        view = getattr(self, 'view', None)
        if view is not None and (watched is view or watched is view.viewport()) and event.type() in (QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show):
            self._schedule_selection_visibility()
        if watched is view and event.type() == QtCore.QEvent.Type.KeyPress:
            directions = {QtCore.Qt.Key.Key_Left:'previous', QtCore.Qt.Key.Key_Right:'next', QtCore.Qt.Key.Key_U:'unlabeled'}
            if event.key() in directions and not event.modifiers():
                self.navigate(directions[event.key()])
                return True
        return super().eventFilter(watched, event)

    def _placeholder_icon(self):
        pixmap = QtGui.QPixmap(self._maximum)
        pixmap.fill(QtGui.QColor('#58626c'))
        painter = QtGui.QPainter(pixmap)
        painter.setPen(QtGui.QColor('#e0e4e8'))
        painter.drawText(pixmap.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, '…')
        painter.end()
        return QtGui.QIcon(pixmap)

    def _thumbnail_path(self, key):
        row = self._rows_by_key[key]
        if not self.dataset or not self.dataset.get('results_dir'):
            return None
        base = (Path(self.dataset['results_dir'])/'verification_masks').resolve()
        tile = str(row['Tile_Name'])
        folder = (base/tile).resolve()
        if base not in folder.parents:
            return None
        if tile not in self._tile_paths:
            found = {}
            if folder.is_dir():
                for file in sorted(folder.glob('obj_*.png')):
                    match = re.fullmatch(r'obj_(\d+)_.+\.png', file.name)
                    if match:
                        path = file.resolve()
                        if base in path.parents:
                            found.setdefault(int(match.group(1)), path)
            self._tile_paths[tile] = found
        return self._tile_paths[tile].get(int(row['Object_ID']))

    def _thumbnail(self, key):
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key][0]
        if self._disposed or key in self._tasks or len(self._tasks) >= self._max_pending:
            return self._placeholder
        path = self._thumbnail_path(key)
        if path is None:
            self._cache_entry(key, self._placeholder, 'missing')
            return self._placeholder
        task = _ThumbnailTask(self._token, key, path, self._maximum, self._max_source_pixels)
        task.signals.done.connect(self._thumbnail_ready)
        self._tasks[key] = task
        image_pool().start(task, -1)
        return self._placeholder

    def _cache_entry(self, key, icon, error):
        self._cache[key] = (icon, error)
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_limit:
            self._cache.popitem(last=False)

    def _thumbnail_ready(self, token, key, image, error):
        task = self._tasks.get(key)
        if task is not None and task.token == token:
            self._tasks.pop(key, None)
        if token != self._token or self._disposed or error == 'cancelled':
            return
        icon = QtGui.QIcon(QtGui.QPixmap.fromImage(image)) if image is not None else self._placeholder
        self._cache_entry(key, icon, error)
        position = self._visible_indexes.get(key)
        if position is not None:
            index = self._model.index(position, 0)
            self._model.dataChanged.emit(index, index, [QtCore.Qt.ItemDataRole.DecorationRole, QtCore.Qt.ItemDataRole.ToolTipRole])
        self.thumbnail_loaded.emit(key, image is not None)
        self.view.viewport().update()

    def dispose(self):
        self._disposed = True
        self._token += 1
        for task in self._tasks.values():
            task.cancelled = True
        self._tasks.clear()

    def closeEvent(self, event):
        self.dispose()
        super().closeEvent(event)
