"""Display-only ruler measurements in image or calibrated source units."""

import json
import math
from pathlib import Path

from .i18n import register_translations, tr
from .image_controls import choose_line_color, choose_line_width, describe, tool_icon
from .qt import QtCore, QtGui, QtWidgets, Signal


_TEXT = {
    'Ruler': ('Линейка', 'סרגל'),
    'Straight ruler': ('Прямая линейка', 'סרגל ישר'),
    'Polyline ruler': ('Ломаная линейка', 'סרגל קו שבור'),
    'Segment color…': ('Цвет отрезка…', 'צבע המקטע…'),
    'Clear ruler': ('Очистить линейку', 'ניקוי הסרגל'),
    'Click vertices. Double-click or press Enter to finish. Backspace removes the last vertex.': (
        'Щёлкайте по вершинам. Двойной щелчок или Enter завершает линию. Backspace удаляет последнюю вершину.',
        'לחצו להוספת קודקודים. לחיצה כפולה או Enter מסיימים. Backspace מוחק את הקודקוד האחרון.'),
    'Right-click a segment to change its color. Esc clears the ruler.': (
        'Щёлкните правой кнопкой по отрезку, чтобы изменить его цвет. Esc очищает линейку.',
        'לחצו לחיצה ימנית על מקטע לשינוי צבעו. Esc מנקה את הסרגל.'),
    'Drag a line. Shift snaps to horizontal or vertical. Esc clears the ruler.': (
        'Проведите отрезок. Shift выравнивает его по горизонтали или вертикали. Esc очищает линейку.',
        'גררו קו. Shift מצמיד אותו לאופק או לאנך. Esc מנקה את הסרגל.'),
    '{value} image px': ('{value} пикс. изображения', '{value} פיקסלים בתמונה'),
    '{value} source px': ('{value} пикс. исходника', '{value} פיקסלים במקור'),
    '{value} µm': ('{value} мкм', '{value} מיקרומטר'),
}
register_translations({key: value[0] for key, value in _TEXT.items()},
                      hebrew={key: value[1] for key, value in _TEXT.items()})


def tile_ruler_scale(dataset, record, space):
    """Resolve scale from the tile manifest and its saved preparation settings."""
    factor = (1.0 if space == 'native' else
              record.get('transform', {}).get('source_pixels_per_output_pixel'))
    if not isinstance(factor, (int, float)) or not math.isfinite(factor) or factor <= 0:
        return None
    pixel_um = (dataset.get('settings') or {}).get('pixel_size_um')
    if not isinstance(pixel_um, (int, float)) or not math.isfinite(pixel_um) or pixel_um <= 0:
        pixel_um = None
    return factor, factor, pixel_um


def measurement_ruler_scale(directory, space=None):
    """Use only the calibration saved with these measured crops."""
    try:
        run = json.loads((Path(directory) / 'measurement_run.json').read_text(encoding='utf-8'))
        space = space or run.get('summary', {}).get('measurement_space')
        calibration = run.get('calibration')
        if isinstance(calibration, dict):
            pixel_um = calibration.get('pixel_size_um') if calibration.get('status', 'valid') == 'valid' else None
        else:
            pixel_um = (run.get('settings') or {}).get('pixel_size_um')
    except (OSError, ValueError, TypeError, AttributeError):
        pixel_um = None
    if space != 'source_pixels':
        return None
    if type(pixel_um) not in (float, int) or not math.isfinite(pixel_um) or pixel_um <= 0:
        pixel_um = None
    return 1.0, 1.0, pixel_um


class ImageRuler(QtCore.QObject):
    """Track endpoints in scene coordinates so zoom and pan preserve length."""

    changed = Signal()

    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.active = False
        self.scale = None
        self.start = self.end = self.line = self.drag_view = None
        self.mode = 'straight'
        self.color = QtGui.QColor('#ffce55')
        self.width = 2
        self.points, self.segments = [], []
        self.building = False
        self._preview = None

    def set_active(self, active):
        self.active = active
        if not active:
            self.clear()
        else:
            polygon = getattr(self.viewer, 'polygon', None)
            if polygon is not None:
                polygon.set_active(False)
            self.viewer._cancel_click()
            self.changed.emit()

    def clear(self):
        self._clear_preview()
        for segment in self.segments:
            self.viewer.scene.removeItem(segment)
        self.points, self.segments = [], []
        self.building = False
        self.line = self.start = self.end = self.drag_view = None
        self.changed.emit()

    def start_mode(self, mode):
        self.mode = mode
        self.set_active(True)
        self.clear()
        self.viewer.view.setFocus()

    def _pen(self, color):
        pen = QtGui.QPen(color, self.width)
        pen.setCosmetic(True)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        return pen

    def _add_line(self, start, end):
        line = self.viewer.scene.addLine(QtCore.QLineF(start, end), self._pen(self.color))
        line.setZValue(10)
        return line

    def change_color(self, parent, segment=None):
        previous = self.color if segment is None else segment.pen().color()
        title = 'Line color…' if segment is None else 'Segment color…'
        color = choose_line_color(parent, previous, self.viewer.language, title)
        if color.isValid():
            if segment is None:
                self.color = color
                for item in self.segments:
                    if item.pen().color() == previous:
                        item.setPen(self._pen(color))
            elif segment in self.segments:
                segment.setPen(self._pen(color))

    def change_width(self, parent):
        self.width = choose_line_width(parent, self.width, self.viewer.language)
        for item in self.segments:
            item.setPen(self._pen(item.pen().color()))
        self._clear_preview()

    def set_scale(self, x, y=None, pixel_um=None):
        # A missing transform still permits a measurement in file pixels.
        self.scale = None if x is None else (x, x if y is None else y, pixel_um)
        self.changed.emit()

    def text(self):
        language = self.viewer.language
        if not self.active:
            return ''
        if self.mode == 'polyline':
            hint = ('Click vertices. Double-click or press Enter to finish. Backspace removes the last vertex.'
                    if self.building or not self.points else 'Right-click a segment to change its color. Esc clears the ruler.')
            if not self.segments:
                return tr(hint, language=language)
        elif self.end is None:
            return tr('Drag a line. Shift snaps to horizontal or vertical. Esc clears the ruler.',
                      language=language)
        bounds = self.viewer._pixmap_item.boundingRect()
        width, height = self.viewer.original_size
        x, y, pixel_um = self.scale or (1, 1, None)
        sx, sy = width * x / bounds.width(), height * y / bounds.height()
        length = sum(math.hypot(item.line().dx() * sx, item.line().dy() * sy) for item in self.segments)
        label = tr('{value} source px' if self.scale else '{value} image px',
                   language=language, value=f'{length:.2f}')
        if pixel_um is not None and math.isfinite(pixel_um) and pixel_um > 0:
            label += ' · ' + tr('{value} µm', language=language, value=f'{length * pixel_um:.3g}')
        if self.mode == 'polyline':
            label += '\n' + tr(hint, language=language)
        return label

    def _clear_preview(self):
        if self._preview is not None:
            self.viewer.scene.removeItem(self._preview)
            self._preview = None

    def _finish(self):
        if self.segments:
            self.building = False
            self._clear_preview()
            self.changed.emit()

    def _remove_vertex(self):
        if self.building and self.points:
            self.points.pop()
            if self.segments:
                self.viewer.scene.removeItem(self.segments.pop())
            self._clear_preview()
            self.changed.emit()

    def handle_key(self, event):
        if not self.active:
            return False
        keys = QtCore.Qt.Key
        if event.key() == keys.Key_Escape:
            callback = self.clear
        elif self.mode == 'polyline' and event.key() in (keys.Key_Enter, keys.Key_Return):
            callback = self._finish
        elif self.mode == 'polyline' and event.key() == keys.Key_Backspace:
            callback = self._remove_vertex
        else:
            return False
        if event.type() == QtCore.QEvent.Type.KeyPress:
            callback()
        event.accept()
        return True

    def _endpoint(self, anchor, point, bounds, modifiers):
        point.setX(min(bounds.right(), max(bounds.left(), point.x())))
        point.setY(min(bounds.bottom(), max(bounds.top(), point.y())))
        if modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier:
            if abs(point.x() - anchor.x()) >= abs(point.y() - anchor.y()):
                point.setY(anchor.y())
            else:
                point.setX(anchor.x())
        return point

    def _polyline_event(self, view, event, point, bounds):
        mouse = QtCore.QEvent.Type
        if event.type() == mouse.MouseMove:
            if self.building and self.points and bounds.contains(point):
                anchor = self.points[-1]
                point = self._endpoint(anchor, point, bounds, event.modifiers())
                if self._preview is None:
                    self._preview = self._add_line(anchor, point)
                    self._preview.setOpacity(0.7)
                else:
                    self._preview.setLine(QtCore.QLineF(anchor, point))
            else:
                self._clear_preview()
        elif event.type() in (mouse.MouseButtonPress, mouse.MouseButtonDblClick) and bounds.contains(point):
            if not self.building:
                if event.type() == mouse.MouseButtonDblClick and self.points:
                    return
                self.clear()
                self.building = True
            self._clear_preview()
            if self.points:
                anchor = self.points[-1]
                point = self._endpoint(anchor, point, bounds, event.modifiers())
                if anchor != point:
                    self.segments.append(self._add_line(anchor, point))
                    self.points.append(point)
            else:
                self.points.append(point)
            view.setFocus()
            if event.type() == mouse.MouseButtonDblClick:
                self._finish()
            self.changed.emit()

    def _segment_menu(self, view, event):
        point = view.mapToScene(event.pos())
        hits = ((self.viewer.polygon._segment_position(view, point, item.line().p1(), item.line().p2())[0], item)
                for item in self.segments)
        distance, segment = min(hits, key=lambda hit: hit[0], default=(math.inf, None))
        if distance <= max(8, self.width):
            menu = QtWidgets.QMenu(view)
            menu.addAction(tr('Segment color…', language=self.viewer.language),
                           lambda: self.change_color(view, segment))
            menu.aboutToHide.connect(menu.deleteLater)
            menu.popup(event.globalPos())
        return True

    def handle(self, view, event):
        if not self.active or self.viewer._pixmap_item is None or self.viewer._loading:
            return False
        kind = event.type()
        events = (QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.MouseButtonDblClick,
                  QtCore.QEvent.Type.MouseMove, QtCore.QEvent.Type.MouseButtonRelease)
        if kind in (QtCore.QEvent.Type.Leave, QtCore.QEvent.Type.Hide, QtCore.QEvent.Type.UngrabMouse):
            self._clear_preview()
            if self.drag_view is view:
                self.drag_view = None
        if kind == QtCore.QEvent.Type.ContextMenu:
            return self._segment_menu(view, event)
        if kind not in events:
            return False
        if kind != QtCore.QEvent.Type.MouseMove and event.button() != QtCore.Qt.MouseButton.LeftButton:
            return False
        bounds = self.viewer._pixmap_item.boundingRect()
        point = view.mapToScene(event.position().toPoint())
        if self.mode == 'polyline':
            self._polyline_event(view, event, point, bounds)
            return True
        if kind in events[:2]:
            if bounds.contains(point):
                self.clear()
                self.start = point
                self.drag_view = view
                self.line = self._add_line(point, point)
                self.segments.append(self.line)
                view.setFocus()
        elif self.drag_view is view:
            self.end = self._endpoint(self.start, point, bounds, event.modifiers())
            self.line.setLine(QtCore.QLineF(self.start, self.end))
            self.changed.emit()
            if kind == QtCore.QEvent.Type.MouseButtonRelease:
                self.drag_view = None
        return True

    def button(self, parent):
        return _RulerButton(self, parent)

    def label(self, parent):
        return _RulerLabel(self, parent)


class _RulerButton(QtWidgets.QToolButton):
    def __init__(self, ruler, parent):
        super().__init__(parent)
        self.ruler = ruler
        self.setCheckable(True)
        self.setObjectName('imageRuler')
        self.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.setMenu(QtWidgets.QMenu(self))
        self.actions_by_key = {}
        for label, callback, icon in (
            ('Straight ruler', lambda: ruler.start_mode('straight'), 'ruler'),
            ('Polyline ruler', lambda: ruler.start_mode('polyline'), 'contour'),
            ('Line color…', lambda: ruler.change_color(self), 'edit'),
            ('Line width…', lambda: ruler.change_width(self), 'levels'),
            ('Clear ruler', ruler.clear, 'close'),
        ):
            action = self.menu().addAction(tool_icon(self, icon), label, callback)
            self.actions_by_key[label] = action
        self.toggled.connect(ruler.set_active)
        ruler.changed.connect(self._sync)
        self._sync()

    def _sync(self):
        with QtCore.QSignalBlocker(self):
            self.setChecked(self.ruler.active)
        viewer = self.ruler.viewer
        title = tr('Ruler', language=viewer.language)
        self.setText(title)
        describe(self, title)
        for key, action in self.actions_by_key.items():
            action.setText(tr(key, language=viewer.language))
        self.setEnabled(getattr(viewer, '_pixmap_item', None) is not None and not viewer._loading)


class _RulerLabel(QtWidgets.QLabel):
    def __init__(self, ruler, parent):
        super().__init__(parent)
        self.ruler = ruler
        self.setWordWrap(True)
        ruler.changed.connect(self._sync)
        self._sync()

    def _sync(self):
        self.setText(self.ruler.text())
        self.setVisible(self.ruler.active)
