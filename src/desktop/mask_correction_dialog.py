"""Preview endpoint connections and native-grid mask brush edits before saving."""
from copy import deepcopy
import math

import numpy as np

from . import mask_correction_text
from .editor_tools import install_tool_shortcuts, tool_label
from .help import attach_help, help_label, install_image_help
from .i18n import tr, get_language
from .image_controls import DrawingCursor, editor_cursor_preference, size_action, tool_icon
from .mask_connection import endpoint_pairs, component_count, footprint
from .object_corrections import correction_context
from .parameter_inputs import ParameterSpinBox
from .qt import QtCore, QtGui, QtWidgets, Signal
from .widgets import ImageViewer, image_pool
from src.default_settings import MASK_EDITOR_DEFAULTS as DEFAULTS


class _Task(QtCore.QRunnable):
    class Signals(QtCore.QObject):
        ready = Signal(object, str)

    def __init__(self, function):
        super().__init__(); self.function = function; self.signals = self.Signals()

    def run(self):
        try: self.signals.ready.emit(self.function(), '')
        except Exception as error: self.signals.ready.emit(None, str(error))


class MaskCorrectionDialog(QtWidgets.QDialog):
    def __init__(self, dataset, tile_name, identifiers, rows, parent=None, *, keep_separate=False, defaults=None):
        super().__init__(parent)
        self.setLayoutDirection(QtCore.Qt.LayoutDirection.RightToLeft if get_language() == 'he' else QtCore.Qt.LayoutDirection.LeftToRight)
        self.keep_separate = keep_separate
        defaults = defaults or DEFAULTS
        self.setWindowTitle(tr('Edit masks separately' if keep_separate else 'Connect ends and edit mask'))
        self.resize(1250, 880)
        self.model = None; self._task = None; self._callback = None
        self._ends, self._items, self._points = [], [], []
        self._pending = None; self._pick_first = True; self.operations = []
        self._guide = None
        self._mask_stats = None
        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(tr('Gold: brush targets. Teal: other selected masks. The eraser acts on every selected mask.'
                                    if keep_separate else
                                    'Gold: selected mask. Pink: manually added pixels. Tile intensities stay unchanged.'))
        intro.setWordWrap(True)
        intro_row=QtWidgets.QHBoxLayout(); intro_row.addWidget(intro,1)
        self.focus_button=QtWidgets.QPushButton(tr('Zoom to selection')); intro_row.addWidget(self.focus_button)
        self.focus_button.clicked.connect(self._focus_selection); attach_help(self.focus_button,'mask_correction')
        layout.addLayout(intro_row)
        self.viewer = ImageViewer(self,maximum=None); layout.addWidget(self.viewer, 1)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.WindowMinMaxButtonsHint)
        self.setSizeGripEnabled(True)
        self.viewer._host_window = self
        install_image_help(self, 'mask_correction', get_language())
        self.viewer.view.viewport().installEventFilter(self)
        self.viewer.loaded.connect(self._draw)
        self.viewer.loaded.connect(self._focus_selection)
        self.controls = QtWidgets.QWidget(); form = QtWidgets.QVBoxLayout(self.controls)
        form.setContentsMargins(0, 0, 0, 0)
        ends_row = QtWidgets.QHBoxLayout()
        self.pairs = QtWidgets.QComboBox(); self.pairs.setMinimumContentsLength(18)
        self.first = QtWidgets.QComboBox(); self.last = QtWidgets.QComboBox()
        for combo in (self.pairs,self.first,self.last):
            combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(14); combo.setMinimumWidth(140)
        for title, widget in [('Suggested pair', self.pairs), ('End A', self.first), ('End B', self.last)]:
            ends_row.addWidget(QtWidgets.QLabel(tr(title))); ends_row.addWidget(widget, 1)
        end_controls = QtWidgets.QWidget()
        end_layout = QtWidgets.QVBoxLayout(end_controls)
        end_layout.setContentsMargins(0, 0, 0, 0)
        end_layout.addLayout(ends_row)
        form.addWidget(end_controls)
        route_row = QtWidgets.QHBoxLayout()
        self.method = QtWidgets.QComboBox()
        self.method.addItem(tr('Follow image signal'), 'image'); self.method.addItem(tr('Straight connection'), 'straight')
        self.connection_width = self._spin(1, 101, defaults['connection_width'], 2)
        self.margin = self._spin(4, 256, defaults['search_margin'])
        self.find = QtWidgets.QPushButton(tr('Find connection')); self.find.setProperty('primary', True)
        self.add = QtWidgets.QPushButton(tr('Add previewed connection'))
        for title, widget in [('Path',self.method), ('Connection width (native px)',self.connection_width), ('Search margin (native px)',self.margin)]:
            route_row.addWidget(QtWidgets.QLabel(tr(title))); route_row.addWidget(widget)
        end_layout.addLayout(route_row)
        end_controls.setVisible(not keep_separate)
        tools = QtWidgets.QHBoxLayout()
        self.tool = QtWidgets.QComboBox()
        self.tool.addItem(tool_label(tr('Pan'), 'pan'), 'pan')
        if not keep_separate:
            self.tool.addItem(tr('Pick ends A / B'), 'ends')
        for title, key in [('Brush','paint'), ('Eraser','erase')]:
            self.tool.addItem(tool_label(tr(title), key), key)
        self.brush = self._spin(1,101,defaults['brush_width'],2)
        self.undo = QtWidgets.QPushButton(tr('Undo mask stroke'))
        self.compare = QtWidgets.QCheckBox(tr('Show original mask'))
        self.save = QtWidgets.QPushButton(tr('Save mask edits' if keep_separate else 'Save connected mask'))
        self.save.setProperty('primary', True)
        self.cancel = QtWidgets.QPushButton(tr('Cancel'))
        tools.addWidget(QtWidgets.QLabel(tr('Tool'))); tools.addWidget(self.tool)
        tools.addWidget(QtWidgets.QLabel(tr('Brush width (native px)'))); tools.addWidget(self.brush)
        for w in (self.undo,self.compare): tools.addWidget(w)
        self.paint_target = QtWidgets.QComboBox()
        if keep_separate:
            tools.addWidget(QtWidgets.QLabel(tr('Brush target')))
            tools.addWidget(attach_help(self.paint_target, 'mask_correction'))
            self.paint_target.currentIndexChanged.connect(self._draw)
        tools.addStretch(); tools.addWidget(help_label('mask_correction')); form.addLayout(tools)
        self.cursor_choice = attach_help(DrawingCursor(get_language()), 'editor_cursor')
        self.cursor_choice.set_preference(editor_cursor_preference(self))
        self.cursor_choice.currentIndexChanged.connect(self._sync)
        cursor_row = QtWidgets.QHBoxLayout()
        cursor_row.addWidget(QtWidgets.QLabel(tr('Drawing cursor')))
        cursor_row.addWidget(self.cursor_choice)
        cursor_row.addStretch()
        form.addLayout(cursor_row)
        actions=QtWidgets.QHBoxLayout(); actions.addWidget(self.find); actions.addWidget(self.add); actions.addStretch()
        self.find.setVisible(not keep_separate); self.add.setVisible(not keep_separate)
        actions.addWidget(self.save); actions.addWidget(self.cancel); form.addLayout(actions); layout.addWidget(self.controls)
        self.status = QtWidgets.QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.caution = QtWidgets.QLabel(tr('A path is a manual reconstruction, not observed biological evidence. Confirm its shape before saving.'))
        self.caution.setWordWrap(True); self.caution.setObjectName('muted'); layout.addWidget(self.caution)
        self.find.clicked.connect(self._find); self.add.clicked.connect(self._add_connection)
        self.undo.clicked.connect(self._undo); self.save.clicked.connect(self._save); self.cancel.clicked.connect(self.reject)
        self._action_buttons = (self.focus_button, self.find, self.add, self.undo, self.save, self.cancel)
        for button, icon in zip(self._action_buttons, ('fit', 'ruler', 'apply', 'undo', 'save', 'close')):
            button.setIcon(tool_icon(button, icon))
            button.setAutoDefault(False)
        self.compare.toggled.connect(self._comparison_changed)
        self.tool.currentIndexChanged.connect(self._tool_changed)
        self.viewer.ruler_button.toggled.connect(self._sync)
        self._tool_shortcuts = install_tool_shortcuts(self, self.tool, self.viewer)
        self.pairs.currentIndexChanged.connect(self._pair_changed)
        for combo in (self.first,self.last,self.method): combo.currentIndexChanged.connect(self._clear_preview)
        self.connection_width.valueChanged.connect(self._route_width_changed)
        self.margin.valueChanged.connect(self._clear_preview)
        self.brush.valueChanged.connect(lambda:self._odd(self.brush))
        self.shortcut = QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Undo, self)
        self.shortcut.activated.connect(self._undo)
        from .input_safety import install_parameter_wheel_guard
        install_parameter_wheel_guard(self)
        for widget in (self.connection_width,self.brush,self.margin,self.first,self.last,self.pairs,self.viewer.view):
            widget.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        for widget in (self.first,self.last,self.pairs,self.connection_width,self.margin,self.method,self.find,self.add,self.tool,self.brush,self.save):
            attach_help(widget,'mask_correction')
        self.dataset, self.tile_name, self.identifiers = deepcopy(dataset),tile_name,list(identifiers)
        self.signature = dataset['measurement_signature']
        self._run(lambda:correction_context(self.dataset,tile_name,self.identifiers,rows,
                                           keep_separate=keep_separate),self._loaded)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for button in getattr(self, '_action_buttons', ()):
            size_action(button, self.width())

    @staticmethod
    def _spin(low, high, value, step=1):
        spin = ParameterSpinBox(); spin.setRange(low,high); spin.setValue(value); spin.setSingleStep(step)
        spin.setMaximumWidth(95); return spin

    @staticmethod
    def _odd(spin):
        if spin.value()%2 == 0:
            with QtCore.QSignalBlocker(spin): spin.setValue(min(101,spin.value()+1))

    def _run(self, function, callback):
        self._callback = callback; self._task = _Task(function)
        self._task.signals.ready.connect(self._done); self.status.setText(tr('Working on mask…'))
        self._sync(); image_pool().start(self._task)

    def _done(self, result, error):
        callback = self._callback; self._task = self._callback = None
        if error: self.status.setText(error)
        else: callback(result)
        self._sync()

    def _loaded(self, context):
        self.model = context['model']
        self.viewer.set_image(context['path'], tr('Native mask correction'),
                              ruler_scale=(1, 1, context['pixel_um']))
        if self.keep_separate:
            for ident in self.model.selected_ids:
                self.paint_target.addItem(f'#{ident}', ident)
            self.paint_target.addItem(tr('Across touched masks'), 'touched')
            self._batch_changed()
        else:
            self._refresh_ends()

    def _tool_changed(self, *_):
        self.viewer.ruler_button.setChecked(False)
        self.viewer.polygon.set_active(False)
        self._points = []
        self._stroke_guide()
        self._sync()

    def _comparison_changed(self, *_):
        self._draw()
        self._sync()

    def _batch_changed(self, *_):
        self._draw()
        self.status.setText(tr('Selected: {selected} · Changed: {changed}. Each edited mask must stay connected.',
                               selected=len(self.model.selected_ids), changed=len(self.model.changed_ids())))

    def _stroke_done(self, changed):
        if self.keep_separate:
            self._batch_changed()
        elif changed:
            self._refresh_ends()
        else:
            self._status()

    def _refresh_ends(self):
        self._pending = None
        self._ends = []
        model = self.model

        def analyse():
            mask, original = model.mask, model.original
            stats = dict(count=component_count(mask), added=int(np.count_nonzero(mask & ~original)),
                         removed=int(np.count_nonzero(original & ~mask)))
            return endpoint_pairs(mask), stats

        self._run(analyse, self._set_ends)

    def _set_ends(self, result):
        (self._ends, pairs), self._mask_stats = result
        for combo in (self.first,self.last,self.pairs): combo.blockSignals(True); combo.clear()
        for i, end in enumerate(self._ends):
            label = tr('End {n} · part {part} · ({x}, {y})',n=i+1,part=end['component'],x=end['x'],y=end['y'])
            coordinates=f"({end['x']}, {end['y']})"
            label=label.replace(coordinates,'\u2066'+coordinates+'\u2069')
            self.first.addItem(label,i); self.last.addItem(label,i)
        for pair in pairs:
            self.pairs.addItem(tr('{a} → {b} · {distance} px',a=pair['first']+1,b=pair['last']+1,distance=f"{pair['distance']:.1f}"),pair)
        for combo in (self.first,self.last,self.pairs): combo.blockSignals(False)
        if pairs: self._pair_changed()
        self._draw(); self._status()

    def _pair_changed(self, *_):
        pair = self.pairs.currentData()
        if pair:
            self.first.setCurrentIndex(pair['first']); self.last.setCurrentIndex(pair['last'])
        self._clear_preview()

    def _route_width_changed(self, *_):
        self._odd(self.connection_width); self._clear_preview()

    def _clear_preview(self, *_):
        self._pending = None; self._draw(); self._sync()

    def _find(self):
        if self._task or not self._ends: return
        self._pending = None
        a,b = self._ends[self.first.currentIndex()],self._ends[self.last.currentIndex()]
        first,last = [a['x'],a['y']],[b['x'],b['y']]
        width,margin,method = self.connection_width.value(),self.margin.value(),self.method.currentData()
        self._run(lambda:self.model.route(first,last,width,margin,method),self._route_ready)

    def _route_ready(self, operation):
        self._pending = operation; self._draw()
        self.status.setText(tr('Review the pink connection, then add it to the mask. Changing width requires a new preview.'))

    def _add_connection(self):
        if self._pending and not self._task:
            operation = self._pending
            self._run(lambda: self.model.apply(operation), self._stroke_done)

    def _undo(self):
        if self._task or not self.model or self.compare.isChecked(): return
        if self._pending: self._clear_preview(); self._status()
        elif self.model.operations:
            self._run(self.model.undo, lambda _: self._stroke_done(True))

    def _save(self):
        if self._task or not self.model or self._pending: return
        self._run(self.model.validate, self._validated)

    def _validated(self, _):
        self.operations = deepcopy(self.model.operations); self.accept()

    def _status(self):
        if self._mask_stats is not None:
            self.status.setText(tr('Components: {count} · Added: {added} px · Removed: {removed} px. Save requires one connected mask.',
                                   **self._mask_stats))

    def _sync(self, *_):
        active = self.model is not None and self._task is None
        self.controls.setEnabled(active)
        different = (len(self._ends) >= 2 and self.first.currentIndex() >= 0 and self.last.currentIndex() >= 0 and
                     self._ends[self.first.currentIndex()]['component'] != self._ends[self.last.currentIndex()]['component'])
        self.find.setEnabled(active and different and not self.compare.isChecked())
        self.add.setEnabled(active and self._pending is not None and not self.compare.isChecked())
        self.undo.setEnabled(active and not self.compare.isChecked() and bool(self._pending or self.model.operations) if self.model else False)
        self.save.setEnabled(active and bool(self.model.operations) and self._pending is None and not self.compare.isChecked() if self.model else False)
        self.paint_target.setEnabled(active and self.tool.currentData() == 'paint' and not self.compare.isChecked())
        if self.viewer.measurement_active:
            return
        drawing = active and not self.compare.isChecked() and self.tool.currentData() != 'pan'
        self.viewer.view.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag if drawing else QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        self.viewer.view.viewport().setCursor(self.cursor_choice.drawing_cursor() if drawing
                                              else QtCore.Qt.CursorShape.OpenHandCursor)

    def _draw(self, *_):
        for item in self._items:
            try:
                if item.scene() is self.viewer.scene: self.viewer.scene.removeItem(item)
            except RuntimeError: pass
        self._items = []
        if not self.model or self.viewer._pixmap_item is None: return
        bounds = self.viewer._pixmap_item.boundingRect(); h,w = self.model.mask.shape
        sx,sy = bounds.width()/w,bounds.height()/h
        mask = self.model.original if self.compare.isChecked() else self.model.mask
        import cv2
        rgba = np.zeros((round(bounds.height()),round(bounds.width()),4),np.uint8)
        selected = cv2.resize(mask.astype(np.uint8),(rgba.shape[1],rgba.shape[0]),interpolation=cv2.INTER_NEAREST)>0
        target = self.paint_target.currentData()
        separate_target = self.keep_separate and type(target) is int
        rgba[selected] = (64,208,185,125) if separate_target else (255,196,48,130)
        if separate_target:
            ident = self.paint_target.currentData()
            crop = self.model.original_crop(ident) if self.compare.isChecked() else self.model.crops[ident]
            active = crop.raster((0, 0, w, h))
            active = cv2.resize(active.astype(np.uint8), (rgba.shape[1],rgba.shape[0]), interpolation=cv2.INTER_NEAREST)>0
            rgba[active] = (255,196,48,160)
        if not self.compare.isChecked():
            changes = self.model.added_mask() if self.keep_separate else mask & ~self.model.original
            added = cv2.resize(changes.astype(np.uint8),(rgba.shape[1],rgba.shape[0]),interpolation=cv2.INTER_NEAREST)>0
            rgba[added] = (245,65,170,205)
            if self._pending:
                (x0,y0,x1,y1),stroke = footprint(mask.shape,self._pending['points'],self._pending['width'])
                pending = np.zeros_like(mask); pending[y0:y1,x0:x1] = stroke
                small = cv2.resize(pending.astype(np.uint8),(rgba.shape[1],rgba.shape[0]),interpolation=cv2.INTER_NEAREST)>0
                rgba[small] = (245,65,170,220)
                x0,y0,x1,y1 = self._pending['search_bounds']
                pen = QtGui.QPen(QtGui.QColor('#4ec7df'),1); pen.setCosmetic(True)
                self._items.append(self.viewer.scene.addRect(x0*sx,y0*sy,(x1-x0)*sx,(y1-y0)*sy,pen))
        qimage=QtGui.QImage(rgba.tobytes(),rgba.shape[1],rgba.shape[0],rgba.shape[1]*4,QtGui.QImage.Format.Format_RGBA8888).copy()
        overlay = self.viewer.scene.addPixmap(QtGui.QPixmap.fromImage(qimage)); overlay.setZValue(1); self._items.append(overlay)
        if not self.compare.isChecked():
            for i, end in enumerate(self._ends):
                color = '#48c9eb'
                label = ''
                if i == self.first.currentIndex(): color,label = '#57d86c','A'
                if i == self.last.currentIndex(): color,label = '#e783ff','B'
                mark = self.viewer.scene.addEllipse(-4,-4,8,8,QtGui.QPen(QtGui.QColor(color)),QtGui.QBrush(QtGui.QColor(color)))
                mark.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
                mark.setPos((end['x']+.5)*sx,(end['y']+.5)*sy); mark.setZValue(3); self._items.append(mark)
                if label:
                    text=self.viewer.scene.addSimpleText(label); text.setBrush(QtGui.QColor(color))
                    # A child of the cosmetic marker uses screen-pixel offsets
                    # even when a small native tile is magnified many times.
                    text.setParentItem(mark); text.setPos(7,-14); text.setZValue(3); self._items.append(text)

    def _point(self, event):
        p=self.viewer.view.mapToScene(event.position().toPoint()); b=self.viewer._pixmap_item.boundingRect()
        h,w=self.model.mask.shape
        return [int(math.floor(p.x()*w/b.width())),int(math.floor(p.y()*h/b.height()))]

    def _focus_selection(self, *_):
        if not self.model or self.viewer._pixmap_item is None: return
        ys = np.flatnonzero(self.model.original.any(axis=1))
        xs = np.flatnonzero(self.model.original.any(axis=0))
        h,w=self.model.mask.shape; b=self.viewer._pixmap_item.boundingRect()
        left,top=max(0,int(xs.min())-24),max(0,int(ys.min())-24)
        right,bottom=min(w,int(xs.max())+25),min(h,int(ys.max())+25)
        region=QtCore.QRectF(left*b.width()/w,top*b.height()/h,(right-left)*b.width()/w,(bottom-top)*b.height()/h)
        self.viewer._keep_manual_transform()
        self.viewer.view.fitInView(region,QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        self.viewer._update_pan_bounds(self.viewer.view); self.viewer.view.centerOn(region.center())

    def _stroke_guide(self):
        if self._guide is not None:
            self.viewer.scene.removeItem(self._guide); self._guide = None
        if not self._points: return
        bounds=self.viewer._pixmap_item.boundingRect(); h,w=self.model.mask.shape
        sx,sy=bounds.width()/w,bounds.height()/h
        path=QtGui.QPainterPath(QtCore.QPointF((self._points[0][0]+.5)*sx,(self._points[0][1]+.5)*sy))
        for x,y in self._points[1:]: path.lineTo((x+.5)*sx,(y+.5)*sy)
        if len(self._points) == 1: path.lineTo((self._points[0][0]+.51)*sx,(self._points[0][1]+.5)*sy)
        pen=QtGui.QPen(QtGui.QColor('#ef576a' if self.tool.currentData() == 'erase' else '#f541aa'),self.brush.value()*sx)
        if self.keep_separate and self.tool.currentData() == 'paint' and self.paint_target.currentData() == 'touched':
            # The guide shows the path. Only centers on selected masks stamp a brush.
            pen.setWidth(1)
            pen.setCosmetic(True)
            pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap); pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        self._guide=self.viewer.scene.addPath(path,pen); self._guide.setZValue(4)

    def eventFilter(self, watched, event):
        if self.viewer.measurement_active: return False
        kind = QtCore.QEvent.Type
        left = QtCore.Qt.MouseButton.LeftButton
        if event.type() == kind.MouseButtonDblClick and event.button() == left: return True
        if (not self.model or self._task or self.compare.isChecked() or
                self.viewer._pixmap_item is None or self.tool.currentData() == 'pan'): return False
        if event.type() in (kind.Hide,kind.UngrabMouse): self._points=[]; self._stroke_guide()
        if event.type() == kind.MouseButtonPress and event.button() == left:
            point=self._point(event); h,w=self.model.mask.shape
            if 0 <= point[0] < w and 0 <= point[1] < h:
                if self.tool.currentData() == 'ends' and self._ends:
                    index=min(range(len(self._ends)),key=lambda i:math.dist(point,[self._ends[i]['x'],self._ends[i]['y']]))
                    if math.dist(point,[self._ends[index]['x'],self._ends[index]['y']]) <= 30:
                        (self.first if self._pick_first else self.last).setCurrentIndex(index); self._pick_first=not self._pick_first
                    else: self.status.setText(tr('Click a marked endpoint.'))
                elif self.tool.currentData() in ('paint','erase'):
                    self._pending=None; self._points=[point]; self._stroke_guide()
            return True
        if self._points and event.type() == kind.MouseMove:
            p=self._point(event); h,w=self.model.mask.shape
            if 0 <= p[0] < w and 0 <= p[1] < h and p != self._points[-1]: self._points.append(p)
            self._stroke_guide()
            return True
        if self._points and event.type() == kind.MouseButtonRelease and event.button() == left:
            p=self._point(event); h,w=self.model.mask.shape
            if 0 <= p[0] < w and 0 <= p[1] < h and p != self._points[-1]: self._points.append(p)
            points,self._points=self._points,[]; self._stroke_guide()
            operation = dict(tool=self.tool.currentData(), points=points, width=self.brush.value())
            if self.keep_separate and operation['tool'] == 'paint':
                target = self.paint_target.currentData()
                if target == 'touched':
                    operation['tool'] = 'paint_touched'
                else:
                    operation['object_id'] = target
            self._run(lambda: self.model.apply(operation), self._stroke_done)
            return True
        return False
