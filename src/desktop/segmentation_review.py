"""Browse tile images and select exact measured masks for a versioned union."""
from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path

import numpy as np

from . import mask_correction_text, segmentation_text
from .help import attach_help
from .i18n import tr
from .image_comparison import add_comparison
from .image_controls import size_action, tool_icon
from .image_ruler import tile_ruler_scale
from .object_merging import exact_objects
from .qt import QtCore, QtGui, QtWidgets, Signal
from .result_tile import resolve_tile_image
from .widgets import ImageViewer, image_pool
from .yolo_preview import add_yolo_status, show_yolo_polygons
from src.partition_geometry import dataset_path
from src.tile_edits import tile_artifact_path


class _MasksTask(QtCore.QRunnable):
    class Signals(QtCore.QObject):
        ready = Signal(int, object, str)

    def __init__(self, token, dataset, tile, rows):
        super().__init__()
        self.token, self.dataset, self.tile, self.rows = token, dataset, tile, rows
        self.signals = self.Signals()

    def run(self):
        try:
            self.signals.ready.emit(self.token, exact_objects(self.dataset, self.tile, self.rows), '')
        except Exception as error:
            self.signals.ready.emit(self.token, [], str(error))


class SegmentationReview(QtWidgets.QWidget):
    merge_requested = Signal(str, object, str)
    correct_requested = Signal(str, object, str, object)
    batch_edit_requested = Signal(str, object, str, object)
    delete_requested = Signal(str, object, str)
    undo_requested = Signal(str)
    labeling_requested = Signal()
    PALETTE = ('#41d6b0', '#ef8a62', '#9cbeff', '#d4a5ff', '#e0d951', '#fc86b5', '#7be0ec')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dataset, self.record, self.rows = None, None, []
        self._rows_by_tile, self._objects, self._tasks = {}, [], {}
        self._token, self._busy, self._native = 0, False, False
        self._items, self._pending_ids = [], []
        self._current, self._can_undo = False, False
        self.editor_defaults = None
        self._preview_dataset_id, self._measurement_pixel_um = None, None
        layout = QtWidgets.QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        controls = QtWidgets.QHBoxLayout()
        self.tiles = QtWidgets.QComboBox(); self.tiles.setMinimumWidth(150)
        self.tiles.setEditable(True)
        self.tiles.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self.tiles.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.tiles.completer().setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
        self.tiles.completer().setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        attach_help(self.tiles, 'segmentation_review')
        controls.addWidget(self.tiles, 1)
        for offset, text in [(-1,'‹'), (1,'›')]:
            button = QtWidgets.QPushButton(text); button.setMaximumWidth(36)
            button.clicked.connect(lambda checked=False, step=offset:self._step(step))
            controls.addWidget(button)
        layout.addLayout(controls)
        splitter = QtWidgets.QSplitter()
        self.tabs = QtWidgets.QTabWidget()
        self.native_view = ImageViewer(); self.model_view = ImageViewer()
        self.objects_view = ImageViewer(); self.polygons_view = ImageViewer()
        self.polygons_status = add_yolo_status(self.polygons_view)
        for viewer, title in [(self.native_view,'Native'), (self.model_view,'Model'),
                              (self.objects_view,'Objects'), (self.polygons_view,'YOLO polygons')]:
            self.tabs.addTab(viewer, tr(title))
        self.tabs.setCurrentIndex(2)
        self.comparison = add_comparison(self.tabs, 0, 2, 'segmentation_review')
        splitter.addWidget(self.tabs)
        parts = QtWidgets.QWidget(); parts.setMinimumWidth(225)
        part_layout = QtWidgets.QVBoxLayout(parts); part_layout.setContentsMargins(4,0,0,0)
        hint = QtWidgets.QLabel(tr('Select parts on the image or check them in the list.')); hint.setWordWrap(True)
        part_layout.addWidget(hint)
        self.ids = QtWidgets.QCheckBox(tr('Show object IDs')); self.ids.setChecked(True)
        self.ids.toggled.connect(self._draw); part_layout.addWidget(self.ids)
        self.list = QtWidgets.QListWidget()
        self.list.setMaximumSize(260, 145)
        attach_help(self.list, 'segmentation_review'); part_layout.addWidget(self.list, 1)
        self.count = QtWidgets.QLabel(); part_layout.addWidget(self.count)
        self.select_all_button = QtWidgets.QPushButton(tr('Select all masks'))
        self.select_all_button.clicked.connect(self.select_all_masks)
        attach_help(self.select_all_button, 'mask_correction'); part_layout.addWidget(self.select_all_button)
        self.select_all_shortcut = QtGui.QShortcut(QtGui.QKeySequence.StandardKey.SelectAll, self)
        self.select_all_shortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.select_all_shortcut.activated.connect(self.select_all_masks)
        self.clear_button = QtWidgets.QPushButton(tr('Clear selection'))
        self.clear_button.clicked.connect(lambda:self.select_ids([])); part_layout.addWidget(self.clear_button)
        self.merge_button = QtWidgets.QPushButton(tr('Merge selected parts')); self.merge_button.setProperty('primary', True)
        self.merge_button.clicked.connect(self._merge)
        attach_help(self.merge_button, 'merge_objects'); part_layout.addWidget(self.merge_button)
        self.correct_button = QtWidgets.QPushButton(tr('Connect ends / Edit mask'))
        self.correct_button.clicked.connect(self._correct)
        attach_help(self.correct_button,'mask_correction'); part_layout.addWidget(self.correct_button)
        self.batch_edit_button = QtWidgets.QPushButton(tr('Edit masks separately'))
        self.batch_edit_button.clicked.connect(lambda: self._correct(keep_separate=True))
        attach_help(self.batch_edit_button, 'mask_correction'); part_layout.addWidget(self.batch_edit_button)
        self.delete_button = QtWidgets.QPushButton(tr('Delete selected masks'))
        self.delete_button.clicked.connect(self._delete)
        attach_help(self.delete_button,'delete_masks'); part_layout.addWidget(self.delete_button)
        self.undo_button = QtWidgets.QPushButton(tr('Undo last mask change'))
        self.undo_button.clicked.connect(lambda:self.undo_requested.emit(self.dataset['measurement_signature']))
        attach_help(self.undo_button, 'merge_objects'); part_layout.addWidget(self.undo_button)
        self.label_button = QtWidgets.QPushButton(tr('Open object labeling'))
        self.label_button.clicked.connect(self.labeling_requested); part_layout.addWidget(self.label_button)
        self._action_buttons = (self.select_all_button, self.clear_button, self.merge_button, self.correct_button,
                                self.batch_edit_button, self.delete_button, self.undo_button, self.label_button)
        icons = ('apply', 'close', 'merge', 'edit', 'edit', 'delete', 'undo', 'open')
        for button, icon in zip(self._action_buttons, icons):
            button.setIcon(tool_icon(button, icon))
            # Long translations wrap at spaces instead of clipping the action.
            lines, line = [], ''
            for word in button.text().split():
                candidate = (line+' '+word).strip()
                if line and button.fontMetrics().horizontalAdvance(candidate) > 150:
                    lines.append(line); line = word
                else:
                    line = candidate
            lines.append(line); button.setText('\n'.join(lines))
        actions = QtWidgets.QScrollArea()
        actions.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        actions.setWidgetResizable(True)
        actions.setWidget(parts)
        actions.setMinimumWidth(240)
        splitter.addWidget(actions)
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([750, 240])
        layout.addWidget(splitter,1)
        self.status = QtWidgets.QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.tiles.currentIndexChanged.connect(self._tile_changed)
        self.list.itemChanged.connect(self._selection_changed)
        self.objects_view.loaded.connect(self._draw)
        self.objects_view.clicked.connect(self._clicked)
        self.set_context(None, [], [], False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for button in self._action_buttons:
            size_action(button, self.width())

    def set_busy(self, busy):
        self._busy = bool(busy)
        self._update_actions()

    def set_context(self, dataset, records, rows, current, preferred_tile=None):
        previous = self.tiles.currentData()
        previous_name = previous.get('filename') if previous else None
        self.dataset, self.rows, self._current = deepcopy(dataset), list(rows), bool(current)
        grouped = defaultdict(list)
        for row in rows: grouped[row['Tile_Name']].append(row)
        self._rows_by_tile = grouped
        self._can_undo, self._measurement_pixel_um = False, None
        if dataset and current:
            try:
                run = json.loads((Path(dataset['results_dir'])/'measurement_run.json').read_text(encoding='utf8'))
                self._can_undo = run.get('operation') in ('merge_objects','correct_objects','delete_objects')
                self._measurement_pixel_um = run.get('settings', {}).get('pixel_size_um')
            except (OSError, ValueError): pass
        self.tiles.blockSignals(True); self.tiles.clear()
        for record in records:
            if not record.get('excluded'):
                stem = Path(record['filename']).stem
                self.tiles.addItem(f"{record['id']:04d} · {stem} · {len(grouped[stem])}", record)
        wanted = previous_name if preferred_tile is None else preferred_tile
        for i in range(self.tiles.count()):
            record = self.tiles.itemData(i)
            if wanted in (record['id'], record['filename'], Path(record['filename']).stem):
                self.tiles.setCurrentIndex(i)
                break
        self.tiles.blockSignals(False); self._tile_changed()

    def _step(self, step):
        self.tiles.setCurrentIndex(max(0,min(self.tiles.count()-1,self.tiles.currentIndex()+step)))

    def select_tile(self, tile):
        for i in range(self.tiles.count()):
            record = self.tiles.itemData(i)
            if tile in (record['id'], Path(record['filename']).stem):
                self.tiles.setCurrentIndex(i); return

    def select_ids(self, identifiers):
        self._pending_ids = list(identifiers)
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setCheckState(QtCore.Qt.CheckState.Checked if item.data(QtCore.Qt.ItemDataRole.UserRole) in identifiers
                               else QtCore.Qt.CheckState.Unchecked)
        self.list.blockSignals(False); self._selection_changed()

    def selected_ids(self):
        return [self.list.item(i).data(QtCore.Qt.ItemDataRole.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == QtCore.Qt.CheckState.Checked]

    def select_all_masks(self):
        if self.select_all_button.isEnabled():
            self.select_ids([self.list.item(i).data(QtCore.Qt.ItemDataRole.UserRole)
                             for i in range(self.list.count())])

    def _tile_changed(self, *_):
        old_record, self.record = self.record, self.tiles.currentData()
        dataset_id = self.dataset.get('id') if self.dataset else None
        same_tile = bool(self.record and old_record and dataset_id == self._preview_dataset_id
                         and self.record['id'] == old_record['id'])
        self._preview_dataset_id = dataset_id
        self._token += 1
        self._pending_ids = self.selected_ids() if same_tile else []
        self._objects = []
        with QtCore.QSignalBlocker(self.list):
            self.list.clear()
        self._selection_changed()
        if not self.dataset or not self.record:
            for viewer in (self.native_view, self.model_view, self.objects_view, self.polygons_view):
                viewer.clear()
            self.polygons_status.hide()
            self.status.setText(tr('Select a tile')); return
        try:
            path, space = resolve_tile_image(self.dataset, self.record); self._native = space == 'native'
            model = tile_artifact_path(self.dataset['path'], self.record, 'filename')
            native_scale = tile_ruler_scale(self.dataset, self.record, space)
            model_scale = tile_ruler_scale(self.dataset, self.record, 'model')
            measurement_scale = (*native_scale[:2], self._measurement_pixel_um) if native_scale else None
            for viewer, filename, caption, scale in (
                (self.native_view, path, tr('Native') if self._native else tr('Model'), native_scale),
                (self.model_view, model, None, model_scale),
                (self.objects_view, path, None, measurement_scale),
                (self.polygons_view, model, None, model_scale),
            ):
                if str(filename) != viewer.filename or viewer._error:
                    viewer.set_image(filename, caption, ruler_scale=scale, preserve_view=same_tile)
                else:
                    viewer.set_ruler_scale(*(scale or (None,)))
            show_yolo_polygons(self.polygons_view, self.polygons_status, self.dataset, self.record)
            if not self._current:
                self.status.setText(tr('Recalculate measurements to view exact masks and merge parts.')); return
            tile = Path(self.record['filename']).stem
            if not self._rows_by_tile.get(tile):
                self.status.setText(tr('No measured objects on this tile.')); return
            self.status.setText(tr('Loading object masks…'))
            task = _MasksTask(self._token, self.dataset, tile, self._rows_by_tile[tile])
            task.signals.ready.connect(self._ready); self._tasks[self._token] = task
            image_pool().start(task)
        except (OSError, ValueError) as error:
            for viewer in (self.native_view, self.model_view, self.objects_view, self.polygons_view):
                viewer.clear()
            self.polygons_status.hide()
            self.status.setText(str(error))

    def _ready(self, token, objects, error):
        self._tasks.pop(token, None)
        if token != self._token: return
        self._objects = objects
        self.list.blockSignals(True)
        for obj in objects:
            ident, area = int(obj['row']['Object_ID']), float(obj['row']['Area'])
            item = QtWidgets.QListWidgetItem(f'#{ident} · {area:g} px²')
            item.setData(QtCore.Qt.ItemDataRole.UserRole, ident)
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Unchecked)
            swatch = QtGui.QPixmap(10,10); swatch.fill(QtGui.QColor(self.PALETTE[ident % len(self.PALETTE)]))
            item.setIcon(QtGui.QIcon(swatch))
            self.list.addItem(item)
        self.list.blockSignals(False)
        self.status.setText(error or tr('The selected parts become one object using their mask union. Gaps remain unchanged.'))
        self.select_ids(self._pending_ids)

    def _selection_changed(self, *_):
        self._update_actions()
        self._draw()

    def _update_actions(self):
        count = len(self.selected_ids())
        self.count.setText(tr('Selected parts: {count}', count=count))
        self.merge_button.setEnabled(self._current and self._native and count >= 2 and not self._busy)
        self.correct_button.setEnabled(self._current and self._native and count > 0 and not self._busy)
        self.batch_edit_button.setEnabled(self.correct_button.isEnabled())
        self.select_all_button.setEnabled(self._current and bool(self.list.count()) and not self._busy)
        self.select_all_shortcut.setEnabled(self.select_all_button.isEnabled())
        self.delete_button.setEnabled(self._current and count > 0 and not self._busy)
        self.undo_button.setEnabled(self._current and self._can_undo and not self._busy)

    def _coordinates(self):
        if self._native:
            return tuple(self._objects[0]['entry']['tile_shape'][::-1])
        return tuple(self.record['transform']['padded_native_shape'][::-1])

    def _draw(self, *_):
        viewer = self.objects_view
        for item in self._items:
            try:
                if item.scene() is viewer.scene: viewer.scene.removeItem(item)
            except RuntimeError: pass
        self._items = []
        if viewer._pixmap_item is None or viewer._loading or not self._objects: return
        bounds = viewer._pixmap_item.boundingRect(); cw,ch = self._coordinates()
        sx,sy = bounds.width()/cw,bounds.height()/ch
        selected = set(self.selected_ids())
        for obj in self._objects:
            ident = int(obj['row']['Object_ID']); mask = obj['mask']
            color = QtGui.QColor('#ffc430' if ident in selected else self.PALETTE[ident % len(self.PALETTE)])
            h,w = mask.shape
            # Raster overlays are bounded by the existing preview resolution.
            import cv2
            dw,dh = max(1,round(w*sx)),max(1,round(h*sy))
            small = cv2.resize(mask.astype(np.uint8),(dw,dh),interpolation=cv2.INTER_NEAREST)
            rgba = np.zeros((dh,dw,4),np.uint8)
            rgba[small > 0] = (color.red(),color.green(),color.blue(),180 if ident in selected else 95)
            if obj.get('manual_added') is not None and obj['manual_added'].any():
                manual = cv2.resize(obj['manual_added'].astype(np.uint8),(dw,dh),interpolation=cv2.INTER_NEAREST)
                rgba[manual > 0] = (245,65,170,210)
            qimage = QtGui.QImage(rgba.tobytes(),dw,dh,dw*4,QtGui.QImage.Format.Format_RGBA8888).copy()
            item = viewer.scene.addPixmap(QtGui.QPixmap.fromImage(qimage))
            x,y = obj['origin']; item.setPos(x*sx,y*sy); item.setZValue(1)
            self._items.append(item)
            ys,xs = np.nonzero(mask)
            if self.ids.isChecked():
                label = viewer.scene.addSimpleText(str(ident)); label.setBrush(color)
                label.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
                label.setPos((x+int(xs.min()))*sx,(y+int(ys.min()))*sy-12); label.setZValue(3)
                self._items.append(label)
            if ident in selected:
                pen = QtGui.QPen(color,2); pen.setCosmetic(True)
                frame = viewer.scene.addRect((x+int(xs.min())-3)*sx,(y+int(ys.min())-3)*sy,
                    (int(xs.max()-xs.min())+7)*sx,(int(ys.max()-ys.min())+7)*sy,pen)
                frame.setZValue(2); self._items.append(frame)

    def _clicked(self, x, y):
        if not self._objects: return
        cw,ch = self._coordinates(); iw,ih = self.objects_view.original_size
        x,y = int(x*cw/iw),int(y*ch/ih)
        hits = []
        for obj in self._objects:
            ox,oy = obj['origin']; mx,my = x-ox,y-oy
            if 0 <= my < obj['mask'].shape[0] and 0 <= mx < obj['mask'].shape[1] and obj['mask'][my,mx]:
                hits.append(int(obj['row']['Object_ID']))
        if len(hits) == 1:
            selected = set(self.selected_ids())
            selected.symmetric_difference_update(hits); self.select_ids(selected)

    def _merge(self):
        if self.merge_button.isEnabled():
            self.merge_requested.emit(Path(self.record['filename']).stem,self.selected_ids(),self.dataset['measurement_signature'])

    def _correct(self, *, keep_separate=False):
        if not (self.batch_edit_button if keep_separate else self.correct_button).isEnabled():
            return
        from .mask_correction_dialog import MaskCorrectionDialog
        tile = Path(self.record['filename']).stem
        dialog = MaskCorrectionDialog(self.dataset, tile, self.selected_ids(), self._rows_by_tile[tile], self,
                                      keep_separate=keep_separate, defaults=self.editor_defaults)
        try:
            if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                signal = self.batch_edit_requested if keep_separate else self.correct_requested
                signal.emit(tile, dialog.identifiers, dialog.signature, dialog.operations)
        finally:
            dialog.deleteLater()

    def _delete(self):
        if self.delete_button.isEnabled():
            self.delete_requested.emit(Path(self.record['filename']).stem,self.selected_ids(),self.dataset['measurement_signature'])
