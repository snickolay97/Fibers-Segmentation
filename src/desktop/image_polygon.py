"""Editable image measurements. The source polygons and image files stay read-only."""

import math
from collections import deque

from .i18n import register_translations, tr
from .image_controls import choose_line_color, choose_line_width, describe, tool_icon
from .qt import QtCore, QtGui, QtWidgets, Signal


_TEXT = {
    'Contour': ('Контур', 'מתאר'),
    'Draw a path': ('Нарисовать ломаную', 'ציור קו שבור'),
    'Draw a rectangle': ('Нарисовать прямоугольник', 'ציור מלבן'),
    'Draw an ellipse': ('Нарисовать эллипс', 'ציור אליפסה'),
    'Copy a displayed outline': ('Скопировать показанный контур', 'העתקת מתאר מוצג'),
    'Close contour': ('Замкнуть контур', 'סגירת המתאר'),
    'Undo contour edit': ('Отменить правку контура', 'ביטול עריכת מתאר'),
    'Clear contour': ('Очистить контур', 'ניקוי המתאר'),
    'YOLO outline color…': ('Цвет контуров YOLO…', 'צבע מתארי YOLO…'),
    'YOLO outline width…': ('Толщина контуров YOLO…', 'עובי מתארי YOLO…'),
    'Use YOLO class colors': ('Использовать цвета классов YOLO', 'שימוש בצבעי מחלקות YOLO'),
    'Click to add vertices. Hold Shift for a horizontal or vertical segment. Enter closes the contour.': (
        'Щёлкайте, чтобы добавить вершины. Удерживайте Shift для горизонтального или вертикального отрезка. Enter замыкает контур.',
        'לחצו להוספת קודקודים. החזיקו Shift לקבלת מקטע אופקי או אנכי. Enter סוגר את המתאר.'),
    'Drag to draw a rectangle. Hold Shift for a square.': (
        'Перетащите указатель, чтобы нарисовать прямоугольник. Удерживайте Shift для квадрата.',
        'גררו לציור מלבן. החזיקו Shift לציור ריבוע.'),
    'Drag to draw an ellipse. Hold Shift for a circle.': (
        'Перетащите указатель, чтобы нарисовать эллипс. Удерживайте Shift для круга.',
        'גררו לציור אליפסה. החזיקו Shift לציור מעגל.'),
    'Click a displayed outline to measure and edit a copy.': (
        'Щёлкните по показанному контуру, чтобы измерить и отредактировать его копию.',
        'לחצו על מתאר מוצג כדי למדוד ולערוך עותק שלו.'),
    'Drag a vertex to move it. Click an edge to add a vertex. Esc clears the contour.': (
        'Перетаскивайте вершины. Щёлкните по ребру, чтобы добавить вершину. Esc очищает контур.',
        'גררו קודקוד כדי להזיזו. לחצו על צלע כדי להוסיף קודקוד. Esc מנקה את המתאר.'),
    'Path length': ('Длина ломаной', 'אורך הקו'),
    'Enclosed area': ('Площадь внутри контура', 'שטח תחום'),
    'Perimeter': ('Периметр', 'היקף'),
    'Equivalent diameter': ('Эквивалентный диаметр', 'קוטר שקול'),
    'Area and diameter require a simple closed contour with positive area.': (
        'Площадь и диаметр доступны для замкнутого контура без самопересечений с ненулевой площадью.',
        'חישוב שטח וקוטר דורש מתאר סגור ללא חציות עצמיות עם שטח חיובי.'),
    '{value} image px²': ('{value} пикс. изображения²', '{value} פיקסלים בתמונה בריבוע'),
    '{value} source px²': ('{value} пикс. исходника²', '{value} פיקסלים במקור בריבוע'),
    '{value} µm²': ('{value} мкм²', '{value} מיקרומטר רבוע'),
}
register_translations({key: pair[0] for key, pair in _TEXT.items()},
                      hebrew={key: pair[1] for key, pair in _TEXT.items()})

_KEYS = QtCore.Qt.Key


def _is_undo(event):
    return event.matches(QtGui.QKeySequence.StandardKey.Undo)


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _is_simple(points):
    if len(set(points)) != len(points):
        return False
    count = len(points)
    segments = []
    for i, a in enumerate(points):
        b = points[(i + 1) % count]
        segments.append((min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1]), i, a, b))
    # Test only edges whose X and Y ranges overlap. Adjacent edges may touch
    # at their shared vertex but must not double back over each other.
    active = []
    for left, right, bottom, top, i, a, b in sorted(segments):
        active = [edge for edge in active if edge[0] >= left]
        for _, low, high, j, c, d in active:
            if high < bottom or low > top:
                continue
            if (i - j) % count in (1, count - 1):
                joint, first, last = (a, c, b) if (i - j) % count == 1 else (b, a, d)
                if (_cross(joint, first, last) == 0 and
                        (first[0] - joint[0]) * (last[0] - joint[0]) +
                        (first[1] - joint[1]) * (last[1] - joint[1]) > 0):
                    return False
            elif (_cross(a, b, c) * _cross(a, b, d) <= 0 and
                  _cross(c, d, a) * _cross(c, d, b) <= 0):
                return False
        active.append((right, bottom, top, i, a, b))
    return True


def contour_geometry(points, closed=False):
    """Return length, enclosed area and area-equivalent diameter in the same units."""
    if len(points) < 2:
        return 0.0, None, None
    edges = list(zip(points, points[1:]))
    if closed and len(points) >= 3:
        edges.append((points[-1], points[0]))
    length = math.fsum(math.dist(a, b) for a, b in edges)
    if not closed or len(points) < 3 or not _is_simple(points):
        return length, None, None
    origin = points[0]
    area = abs(math.fsum(_cross(origin, a, b) for a, b in edges)) / 2
    return (length, area, 2 * math.sqrt(area / math.pi)) if area > 0 else (length, None, None)


def _contour_icons(color):
    """Draw menu glyphs in the current text color for either theme."""
    def icon(draw):
        pixmap = QtGui.QPixmap(18, 18)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QPen(color, 1.5))
        draw(painter)
        painter.end()
        return QtGui.QIcon(pixmap)

    def line(painter, *points):
        painter.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in points]))

    def copy(painter):
        painter.drawRect(7, 7, 8, 8)
        line(painter, (4, 11), (4, 4), (11, 4))

    def undo(painter):
        line(painter, (7, 3), (3, 7), (7, 11))
        line(painter, (3, 7), (12, 7), (15, 10), (15, 14))

    def clear(painter):
        line(painter, (4, 4), (14, 14))
        line(painter, (14, 4), (4, 14))

    return {
        'Draw a path': icon(lambda p: line(p, (2, 13), (6, 5), (11, 11), (16, 4))),
        'Draw a rectangle': icon(lambda p: p.drawRect(3, 3, 12, 12)),
        'Draw an ellipse': icon(lambda p: p.drawEllipse(2, 4, 14, 10)),
        'Copy a displayed outline': icon(copy),
        'Close contour': icon(lambda p: line(p, (3, 14), (9, 4), (15, 14), (3, 14))),
        'Undo contour edit': icon(undo),
        'Clear contour': icon(clear),
    }


class ImagePolygon(QtCore.QObject):
    """Keep editable vertices in scene coordinates across pan, zoom and expanded views."""

    changed = Signal()

    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.active = False
        self.mode = 'path'
        self.points = []
        self.closed = False
        self._outline = None
        self._hover_line = None
        self._vertices = []
        self.color = QtGui.QColor('#ffcf60')
        self.width = 2
        self.displayed_color = None
        self.displayed_width = 2
        self._history = deque(maxlen=128)
        self._reset_drag()
        self.viewer.ruler.changed.connect(self.changed)

    def ready(self):
        return getattr(self.viewer, '_pixmap_item', None) is not None and not self.viewer._loading

    def set_active(self, active):
        if active == self.active:
            return
        self.active = active
        if active:
            self.viewer.ruler.set_active(False)
            self.viewer._cancel_click()
            self.changed.emit()
        else:
            self._history.clear()
            self._restore(((), False))

    def start(self, mode):
        self.set_active(True)
        self.cancel_drag()
        self._clear_hover()
        self.mode = 'new_path' if mode == 'path' else mode
        self.changed.emit()

    def _snapshot(self):
        return tuple(self.points), self.closed

    def _restore(self, state):
        self._clear_hover()
        points, self.closed = state
        self.points = list(points)
        self.mode = 'path'
        self._reset_drag()
        self._redraw()

    def _record(self, before):
        if before != self._snapshot():
            self._history.append(before)

    @property
    def can_undo(self):
        return bool(self._history)

    def cancel_drag(self):
        if self._before_drag is not None:
            self._restore(self._before_drag)

    def undo(self):
        if self._before_drag is not None:
            self.cancel_drag()
        elif self._history:
            self._restore(self._history.pop())

    def clear(self):
        self.cancel_drag()
        if self.points:
            self._history.append(self._snapshot())
        self._restore(((), False))

    def _reset_drag(self):
        self._drag_view = self._drag_index = self._anchor = self._drag_start = None
        self._before_drag = None
        self._drag_moved = False

    def close_contour(self):
        self.cancel_drag()
        self._clear_hover()
        if len(self.points) >= 3 and not self.closed:
            self._history.append(self._snapshot())
            self.closed = True
            self.mode = 'path'
            self._redraw()

    def _redraw(self):
        if not self.points:
            for item in [self._outline, *self._vertices]:
                if item is not None:
                    self.viewer.scene.removeItem(item)
            self._outline, self._vertices = None, []
            self.changed.emit()
            return
        path = QtGui.QPainterPath()
        if self.points:
            path.moveTo(self.points[0])
            for point in self.points[1:]:
                path.lineTo(point)
            if self.closed:
                path.closeSubpath()
        if self._outline is None:
            self._outline = self.viewer.scene.addPath(path, self._pen())
            self._outline.setZValue(11)
        else:
            self._outline.setPath(path)
            self._outline.setPen(self._pen())
        while len(self._vertices) > len(self.points):
            self.viewer.scene.removeItem(self._vertices.pop())
        while len(self._vertices) < len(self.points):
            marker = self.viewer.scene.addEllipse(-3.5, -3.5, 7, 7, QtGui.QPen(QtGui.QColor('#593700')),
                                                   QtGui.QBrush(self.color))
            marker.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            marker.setZValue(12)
            self._vertices.append(marker)
        for marker, point in zip(self._vertices, self.points):
            marker.setPos(point)
            marker.setBrush(self.color)
        self.changed.emit()

    def _pen(self):
        pen = QtGui.QPen(self.color, self.width)
        pen.setCosmetic(True)
        return pen

    def change_color(self, parent, *, displayed=False):
        old = (self.displayed_color or self.color) if displayed else self.color
        title = 'YOLO outline color…' if displayed else 'Line color…'
        color = choose_line_color(parent, old, self.viewer.language, title)
        if color.isValid():
            if displayed:
                self.displayed_color = color
                self.viewer._draw_polygons()
                self.changed.emit()
            else:
                self.color = color
                self._clear_hover()
                self._redraw()

    def change_width(self, parent, *, displayed=False):
        if displayed:
            self.displayed_width = choose_line_width(parent, self.displayed_width, self.viewer.language)
            self.viewer._draw_polygons()
        else:
            self.width = choose_line_width(parent, self.width, self.viewer.language)
            self._clear_hover()
            self._redraw()

    def restore_class_colors(self):
        self.displayed_color = None
        self.viewer._draw_polygons()
        self.changed.emit()

    def _clear_hover(self):
        if self._hover_line is not None:
            self.viewer.scene.removeItem(self._hover_line)
            self._hover_line = None

    def _follow_pointer(self, point, bounds, constrained):
        if self.closed or not self.points or self.mode != 'path' or not bounds.contains(point):
            self._clear_hover()
            return
        anchor = self.points[-1]
        if constrained:
            point = self._snap_to_axis(anchor, point)
        if self._hover_line is None:
            pen = self._pen()
            pen.setStyle(QtCore.Qt.PenStyle.DashLine)
            self._hover_line = self.viewer.scene.addLine(QtCore.QLineF(anchor, point), pen)
            self._hover_line.setZValue(11)
        else:
            self._hover_line.setLine(QtCore.QLineF(anchor, point))

    def _snap_to_axis(self, anchor, point):
        sx, sy = self._scene_scale()
        if abs(point.x() - anchor.x()) * sx >= abs(point.y() - anchor.y()) * sy:
            point.setY(anchor.y())
        else:
            point.setX(anchor.x())
        return point

    def _scene_scale(self):
        rect = self.viewer._pixmap_item.boundingRect()
        width, height = self.viewer.original_size
        sx, sy = self.viewer.ruler.scale[:2] if self.viewer.ruler.scale is not None else (1.0, 1.0)
        return width / rect.width() * sx, height / rect.height() * sy

    def _scaled_points(self):
        sx, sy = self._scene_scale()
        return [(point.x() * sx, point.y() * sy) for point in self.points]

    def text(self):
        if not self.active or not self.ready():
            return ''
        language = self.viewer.language
        hint = {
            'rectangle': 'Drag to draw a rectangle. Hold Shift for a square.',
            'ellipse': 'Drag to draw an ellipse. Hold Shift for a circle.',
            'copy': 'Click a displayed outline to measure and edit a copy.',
        }.get(self.mode)
        if hint is None:
            hint = ('Drag a vertex to move it. Click an edge to add a vertex. Esc clears the contour.' if self.closed else
                    'Click to add vertices. Hold Shift for a horizontal or vertical segment. Enter closes the contour.')
        if len(self.points) < 2:
            return tr(hint, language=language)
        length, area, diameter = contour_geometry(self._scaled_points(), self.closed)
        scale = self.viewer.ruler.scale
        unit = 'source' if scale is not None else 'image'
        pixel_um = scale[2] if scale is not None else None

        def format_value(label, value, squared=False):
            px = '{value} ' + unit + (' px²' if squared else ' px')
            text = tr(label, language=language) + ' ' + tr(px, language=language, value=f'{value:.2f}')
            if pixel_um is not None and math.isfinite(pixel_um) and pixel_um > 0:
                physical = value * (pixel_um ** (2 if squared else 1))
                text += ' · ' + tr('{value} µm²' if squared else '{value} µm', language=language, value=f'{physical:.3g}')
            return text

        values = [format_value('Perimeter' if self.closed else 'Path length', length)]
        if area is not None:
            values += [format_value('Enclosed area', area, squared=True), format_value('Equivalent diameter', diameter)]
        elif self.closed:
            values.append(tr('Area and diameter require a simple closed contour with positive area.', language=language))
        return '  |  '.join(values) + '\n' + tr(hint, language=language)

    @staticmethod
    def _segment_position(view, point, a, b):
        # Hit-testing in viewport pixels keeps the insertion radius stable while zooming.
        p = view.mapFromScene(point)
        x, y = view.mapFromScene(a), view.mapFromScene(b)
        dx, dy = y.x() - x.x(), y.y() - x.y()
        length_sq = dx * dx + dy * dy
        fraction = ((p.x() - x.x()) * dx + (p.y() - x.y()) * dy) / length_sq if length_sq else 0
        fraction = max(0.0, min(1.0, fraction))
        return math.hypot(p.x() - x.x() - dx * fraction, p.y() - x.y() - dy * fraction), a + (b - a) * fraction

    def _nearest_edge(self, view, point, points):
        hits = ((*self._segment_position(view, point, a, points[(i + 1) % len(points)]), i + 1)
                for i, a in enumerate(points))
        distance, projected, index = min(hits, key=lambda hit: hit[0])
        if distance <= 8:
            return projected, index
        return None

    def _copy_outline(self, view, point, bounds):
        # The last displayed outline is on top when multiple outlines overlap.
        for outline in reversed(self.viewer._polygons):
            points = [QtCore.QPointF(x * bounds.width(), y * bounds.height()) for x, y in outline.get('points', ())
                      if math.isfinite(x) and math.isfinite(y)]
            if len(points) > 1 and points[0] == points[-1]:
                points.pop()
            if len(points) < 3:
                continue
            if (QtGui.QPolygonF(points).containsPoint(point, QtCore.Qt.FillRule.OddEvenFill)
                    or self._nearest_edge(view, point, points)):
                before = self._snapshot()
                self.points, self.closed, self.mode = points, True, 'path'
                self._record(before)
                self._redraw()
                return

    def _set_shape(self, point, constrained):
        if constrained:
            # Use the measurement grid so a square stays square even in a
            # resampled preview with a different X and Y scale.
            sx, sy = self._scene_scale()
            dx, dy = point.x() - self._anchor.x(), point.y() - self._anchor.y()
            side = min(abs(dx) * sx, abs(dy) * sy)
            point = self._anchor + QtCore.QPointF(math.copysign(side / sx, dx), math.copysign(side / sy, dy))
        box = QtCore.QRectF(self._anchor, point).normalized()
        if box.isEmpty():
            points, self.closed = self._before_drag
            self.points = list(points)
            self._redraw()
            return
        if self.mode == 'rectangle':
            self.points = [box.topLeft(), box.topRight(), box.bottomRight(), box.bottomLeft()]
        else:
            # Ellipses become an editable polygon with uniformly spaced angles.
            center = box.center()
            self.points = [QtCore.QPointF(center.x() + box.width() / 2 * math.cos(angle),
                                          center.y() + box.height() / 2 * math.sin(angle))
                           for angle in (math.tau * i / 32 for i in range(32))]
        self.closed = True
        self._redraw()

    def _press(self, view, point, bounds, constrained):
        if not bounds.contains(point):
            return
        self.cancel_drag()
        view.setFocus()
        if self.mode == 'copy':
            self._copy_outline(view, point, bounds)
            return
        if self.mode in ('rectangle', 'ellipse'):
            self._before_drag = self._snapshot()
            self._anchor, self._drag_view = point, view
            return
        if self.mode == 'new_path':
            before = self._snapshot()
            self.points, self.closed, self.mode = [point], False, 'path'
            self._record(before)
            self._redraw()
            return
        position = view.mapFromScene(point)
        offsets = (position - view.mapFromScene(vertex) for vertex in self.points)
        distances = ((offset.x() ** 2 + offset.y() ** 2, i) for i, offset in enumerate(offsets))
        distance_squared, hit = min(distances, default=(math.inf, None))
        if distance_squared <= 8 ** 2:
            self._before_drag = self._snapshot()
            self._begin_vertex_drag(view, hit, point)
        elif not self.closed:
            if constrained and self.points:
                point = self._snap_to_axis(self.points[-1], point)
            self._history.append(self._snapshot())
            self.points.append(point)
            self._redraw()
        elif edge := self._nearest_edge(view, point, self.points):
            projected, index = edge
            self._before_drag = self._snapshot()
            self.points.insert(index, projected)
            self._begin_vertex_drag(view, index, point)
            self._redraw()

    def _begin_vertex_drag(self, view, index, point):
        self._drag_view, self._drag_index = view, index
        self._drag_start = point, self.points[index]
        self._drag_moved = False

    @staticmethod
    def _clamp(point, bounds):
        return QtCore.QPointF(max(bounds.left(), min(bounds.right(), point.x())),
                              max(bounds.top(), min(bounds.bottom(), point.y())))

    def _move_vertex(self, view, point, bounds, released):
        start, original = self._drag_start
        self._drag_moved |= (view.mapFromScene(start) - view.mapFromScene(point)).manhattanLength() >= 3
        if self._drag_moved:
            self.points[self._drag_index] = self._clamp(original + point - start, bounds)
            self._redraw()
        elif released and self._drag_index == 0 and not self.closed and len(self.points) >= 3:
            self.closed = True
            self._redraw()

    def handle_key(self, event):
        if not self.active or not self.ready():
            return False
        key = event.key()
        if _is_undo(event):
            action = self.undo
        elif key == _KEYS.Key_Escape:
            action = self.clear
        elif key in (_KEYS.Key_Return, _KEYS.Key_Enter):
            action = self.close_contour
        elif key == _KEYS.Key_Backspace:
            action = self._remove_last_point
        else:
            return False
        if event.type() == QtCore.QEvent.Type.KeyPress:
            action()
        event.accept()
        return True

    def _remove_last_point(self):
        self.cancel_drag()
        self._clear_hover()
        if self.points:
            self._history.append(self._snapshot())
            self.points.pop()
            self.closed = self.closed and len(self.points) >= 3
            self.mode = 'path'
            self._redraw()

    def handle(self, view, event):
        if not self.active or not self.ready():
            return False
        kind = event.type()
        mouse = QtCore.QEvent.Type
        if kind in (mouse.Hide, mouse.UngrabMouse) and self._drag_view is view:
            self.cancel_drag()
        if kind in (mouse.Hide, mouse.Leave, mouse.UngrabMouse):
            self._clear_hover()
        if kind not in (mouse.MouseButtonPress, mouse.MouseButtonDblClick, mouse.MouseMove, mouse.MouseButtonRelease):
            return False
        if kind != mouse.MouseMove and event.button() != QtCore.Qt.MouseButton.LeftButton:
            return False
        bounds = self.viewer._pixmap_item.boundingRect()
        point = view.mapToScene(event.position().toPoint())
        constrained = bool(event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier)
        if kind in (mouse.MouseButtonPress, mouse.MouseButtonDblClick):
            self._clear_hover()
            if kind != mouse.MouseButtonDblClick or not self.closed:
                self._press(view, point, bounds, constrained)
            if kind == mouse.MouseButtonDblClick and self.mode == 'path' and bounds.contains(point):
                self.close_contour()
        elif self._drag_view is view:
            released = kind == mouse.MouseButtonRelease
            if self._anchor is not None:
                self._set_shape(self._clamp(point, bounds), constrained)
            else:
                self._move_vertex(view, point, bounds, released)
            if released:
                # A drag, including an inserted vertex, is one undo step.
                if self._before_drag != self._snapshot():
                    self._record(self._before_drag)
                    self.mode = 'path'
                self._reset_drag()
                self.changed.emit()
        elif kind == mouse.MouseMove:
            self._follow_pointer(point, bounds, constrained)
        return True

    def button(self, parent):
        return _PolygonButton(self, parent)

    def label(self, parent):
        return _PolygonLabel(self, parent)


class _PolygonButton(QtWidgets.QToolButton):
    def __init__(self, polygon, parent):
        super().__init__(parent)
        self.polygon = polygon
        self.setObjectName('imageContour')
        self.setCheckable(True)
        self.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        menu = QtWidgets.QMenu(self)
        self.actions_by_key = {}
        for key, callback in (
            ('Draw a path', lambda: polygon.start('path')),
            ('Draw a rectangle', lambda: polygon.start('rectangle')),
            ('Draw an ellipse', lambda: polygon.start('ellipse')),
            ('Copy a displayed outline', lambda: polygon.start('copy')),
            ('Close contour', polygon.close_contour),
            ('Undo contour edit', polygon.undo),
            ('Clear contour', polygon.clear),
            ('Line color…', lambda: polygon.change_color(self)),
            ('Line width…', lambda: polygon.change_width(self)),
            ('YOLO outline color…', lambda: polygon.change_color(self, displayed=True)),
            ('YOLO outline width…', lambda: polygon.change_width(self, displayed=True)),
            ('Use YOLO class colors', polygon.restore_class_colors),
        ):
            action = menu.addAction(key, callback)
            action.setIconVisibleInMenu(True)
            self.actions_by_key[key] = action
        self.setMenu(menu)
        self.toggled.connect(polygon.set_active)
        polygon.changed.connect(self._sync)
        self._sync_icons()
        self._sync()

    def _sync_icons(self):
        for key, icon in _contour_icons(self.palette().color(QtGui.QPalette.ColorRole.ButtonText)).items():
            self.actions_by_key[key].setIcon(icon)
        for key, icon in (('Line color…', 'edit'), ('Line width…', 'levels'), ('YOLO outline color…', 'edit'),
                          ('YOLO outline width…', 'levels'), ('Use YOLO class colors', 'undo')):
            self.actions_by_key[key].setIcon(tool_icon(self, icon))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.Type.PaletteChange, QtCore.QEvent.Type.StyleChange):
            self._sync_icons()

    def event(self, event):
        if (event.type() in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress)
                and _is_undo(event) and self.polygon.handle_key(event)):
            return True
        return super().event(event)

    def _sync(self):
        polygon = self.polygon
        language = polygon.viewer.language
        with QtCore.QSignalBlocker(self):
            self.setChecked(polygon.active)
        title = tr('Contour', language=language)
        self.setText(title)
        describe(self, title)
        self.setEnabled(polygon.ready())
        for key, action in self.actions_by_key.items():
            shortcut = '\tCtrl+Z' if key == 'Undo contour edit' else ''
            action.setText(tr(key, language=language) + shortcut)
        self.actions_by_key['Copy a displayed outline'].setEnabled(bool(polygon.viewer._polygons))
        self.actions_by_key['Close contour'].setEnabled(len(polygon.points) >= 3 and not polygon.closed)
        self.actions_by_key['Undo contour edit'].setEnabled(polygon.can_undo)
        self.actions_by_key['Clear contour'].setEnabled(bool(polygon.points))
        for key in ('YOLO outline color…', 'YOLO outline width…', 'Use YOLO class colors'):
            self.actions_by_key[key].setEnabled(bool(polygon.viewer._polygons))


class _PolygonLabel(QtWidgets.QLabel):
    def __init__(self, polygon, parent):
        super().__init__(parent)
        self.polygon = polygon
        self.setWordWrap(True)
        polygon.changed.connect(self._sync)
        self._sync()

    def _sync(self):
        self.setText(self.polygon.text())
        self.setVisible(self.polygon.active)
