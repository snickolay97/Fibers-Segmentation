"""Shared icon buttons and screen-space drawing controls for image windows."""

from .i18n import register_translations, tr
from .qt import QtCore, QtGui, QtWidgets


_LABELS = {
    'Zoom out': ('Уменьшить', 'הקטנת תצוגה'),
    'Zoom in': ('Увеличить', 'הגדלת תצוגה'),
    'Line color…': ('Цвет линии…', 'צבע הקו…'),
    'Line width…': ('Толщина линии…', 'עובי הקו…'),
    'Width (screen px)': ('Толщина (экранные px)', 'עובי (פיקסלי מסך)'),
    'Drawing cursor': ('Курсор рисования', 'סמן ציור'),
    'Crosshair': ('Крест', 'צלב'),
    'Dot': ('Точка', 'נקודה'),
    'Arrow': ('Стрелка', 'חץ'),
    'Precision target': ('Прицел', 'כוונת'),
}
register_translations({key: value[0] for key, value in _LABELS.items()},
                      hebrew={key: value[1] for key, value in _LABELS.items()})


def tool_icon(widget, name):
    """Paint monochrome glyphs using the active theme's button text color."""
    pixmap = QtGui.QPixmap(48, 48)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.scale(2, 2)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    color = (QtGui.QColor('white') if widget.property('primary')
             else widget.palette().color(QtGui.QPalette.ColorGroup.Active, QtGui.QPalette.ColorRole.ButtonText))
    painter.setPen(QtGui.QPen(color, 1.65,
                             cap=QtCore.Qt.PenCapStyle.RoundCap,
                             join=QtCore.Qt.PenJoinStyle.RoundJoin))

    def line(*points):
        painter.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in points]))

    if name in ('zoom_in', 'zoom_out'):
        painter.drawEllipse(3, 3, 13, 13)
        line((14, 14), (21, 21))
        line((6, 9.5), (13, 9.5))
        if name == 'zoom_in':
            line((9.5, 6), (9.5, 13))
    elif name in ('fit', 'enlarge'):
        for x, y, dx, dy in ((3, 3, 1, 1), (21, 3, -1, 1), (3, 21, 1, -1), (21, 21, -1, -1)):
            line((x, y + 5 * dy), (x, y), (x + 5 * dx, y))
        if name == 'fit':
            painter.drawRect(7, 8, 10, 8)
    elif name == 'ruler':
        painter.translate(12, 12)
        painter.rotate(-37)
        painter.drawRect(-10, -4, 20, 8)
        for x, length in ((-6, 3), (-2, 5), (2, 3), (6, 5)):
            line((x, -4), (x, -4 + length))
    elif name == 'contour':
        line((4, 16), (7, 4), (19, 7), (20, 18), (11, 21), (4, 16))
        for x, y in ((4, 16), (7, 4), (19, 7), (20, 18), (11, 21)):
            painter.drawEllipse(x - 1, y - 1, 2, 2)
    elif name == 'levels':
        for x, y in ((5, 8), (12, 15), (19, 10)):
            line((x, 3), (x, y - 2))
            painter.drawEllipse(x - 2, y - 2, 4, 4)
            line((x, y + 2), (x, 21))
    elif name == 'save':
        line((4, 3), (17, 3), (20, 6), (20, 21), (4, 21), (4, 3))
        line((8, 3), (8, 9), (16, 9), (16, 3))
        line((8, 21), (8, 14), (16, 14), (16, 21))
    elif name == 'compare':
        painter.drawRect(3, 4, 13, 12)
        line((19, 8), (21, 8), (21, 20), (8, 20), (8, 19))
        line((5, 13), (9, 9), (13, 13))
    elif name == 'undo':
        line((9, 4), (4, 9), (9, 14))
        painter.drawPath(_undo_curve())
    elif name == 'edit':
        line((4, 20), (5, 14), (16, 3), (21, 8), (10, 19), (4, 20))
        line((14, 5), (19, 10))
    elif name == 'pick':
        line((5, 19), (6, 15), (15, 6), (18, 9), (9, 18), (5, 19))
        line((13, 5), (19, 11))
        line((15, 6), (19, 2), (22, 5), (18, 9))
    elif name == 'apply':
        line((4, 12), (9, 17), (20, 6))
    elif name == 'close':
        line((6, 6), (18, 18))
        line((18, 6), (6, 18))
    elif name == 'open':
        line((3, 18), (3, 5), (10, 5), (12, 8), (21, 8), (21, 10))
        line((3, 18), (7, 10), (22, 10), (19, 19), (3, 19), (3, 18))
    elif name == 'new':
        line((5, 3), (14, 3), (19, 8), (19, 21), (5, 21), (5, 3))
        line((14, 3), (14, 8), (19, 8))
        line((9, 14), (15, 14))
        line((12, 11), (12, 17))
    elif name == 'run':
        line((7, 4), (20, 12), (7, 20), (7, 4))
    elif name == 'delete':
        line((4, 6), (20, 6))
        line((9, 6), (9, 3), (15, 3), (15, 6))
        line((6, 6), (7, 21), (17, 21), (18, 6))
        line((10, 10), (10, 17))
        line((14, 10), (14, 17))
    elif name == 'merge':
        line((4, 5), (9, 5), (15, 12), (21, 12))
        line((4, 19), (9, 19), (15, 12))
        line((18, 9), (21, 12), (18, 15))
    painter.end()
    return QtGui.QIcon(pixmap)


def _undo_curve():
    path = QtGui.QPainterPath(QtCore.QPointF(4, 9))
    path.lineTo(14, 9)
    path.cubicTo(23, 9, 23, 20, 14, 20)
    return path


def describe(button, text):
    button.setAccessibleName(text)
    button.setToolTip(text)


def size_action(button, width):
    # A wider window gives the actions larger hit targets and glyphs, up to
    # a cap that leaves the image most of the vertical space.
    growth = min(12, max(0, (width - 440) // 70))
    button.setMinimumHeight(30 + growth)
    button.setIconSize(QtCore.QSize(17 + growth // 2, 17 + growth // 2))
    return growth


class ImageActionStrip(QtWidgets.QWidget):
    """Reflow one set of actions for narrow panes and large windows."""

    def __init__(self, buttons, parent=None):
        super().__init__(parent)
        self.setObjectName('imageActions')
        self.buttons = buttons
        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(4)
        self._columns = 0
        self._visible_buttons = ()
        for button in self.buttons:
            button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self._arrange()

    def _arrange(self):
        growth = size_action(self.buttons[0], self.width())
        cell = 40 + growth
        visible = tuple(button for button in self.buttons if not button.isHidden())
        columns = max(1, min(len(visible), (self.width() + 4) // (cell + 4)))
        if columns != self._columns or visible != self._visible_buttons:
            for index in range(max(columns, self._columns)):
                self.grid.setColumnStretch(index, int(index < columns))
            for index, button in enumerate(visible):
                self.grid.addWidget(button, index // columns, index % columns)
            self._columns = columns
            self._visible_buttons = visible
        for button in visible:
            size_action(button, self.width())
            has_label = bool(button.property('showActionText')) and self.width() >= 1050
            button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon if has_label
                                      else QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setMinimumWidth(max(cell, button.sizeHint().width()) if has_label else cell)
            button.setMaximumWidth(180 if has_label else 96 + growth * 3)

    def minimumSizeHint(self):
        return QtCore.QSize(0, self.grid.minimumSize().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange()


def choose_line_color(parent, color, language, title='Line color…'):
    return QtWidgets.QColorDialog.getColor(color, parent, tr(title, language=language))


def choose_line_width(parent, width, language):
    value, ok = QtWidgets.QInputDialog.getInt(
        parent, tr('Line width…', language=language), tr('Width (screen px)', language=language), width, 1, 12)
    return value if ok else width


class DrawingCursor(QtWidgets.QComboBox):
    """Select the drawing pointer without changing pan or brush geometry."""

    def __init__(self, language, parent=None):
        super().__init__(parent)
        self.setAccessibleName(tr('Drawing cursor', language=language))
        self.setIconSize(QtCore.QSize(25, 25))
        for label in ('Crosshair', 'Dot', 'Arrow', 'Precision target'):
            self.addItem(QtGui.QIcon(self.preview_pixmap(label)), tr(label, language=language), label)

    def set_preference(self, value):
        self.setCurrentIndex(max(0, self.findData(value)))

    def drawing_cursor(self):
        shape = self.currentData()
        if shape == 'Crosshair':
            return QtGui.QCursor(QtCore.Qt.CursorShape.CrossCursor)
        if shape == 'Arrow':
            return QtGui.QCursor(QtCore.Qt.CursorShape.ArrowCursor)
        return QtGui.QCursor(self.preview_pixmap(shape), 11, 11)

    @staticmethod
    def preview_pixmap(shape):
        """Draw a legible sample with the same dot and target as the live cursor."""
        pixmap = QtGui.QPixmap(23, 23)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        center = QtCore.QPointF(11.5, 11.5)
        if shape == 'Arrow':
            painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.black, 1.4))
            painter.setBrush(QtCore.Qt.GlobalColor.white)
            painter.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in
                ((5, 2), (5, 19), (9, 15), (12, 21), (15, 19), (12, 13), (18, 13))]))
        else:
            for color, width in ((QtCore.Qt.GlobalColor.black, 3), (QtCore.Qt.GlobalColor.white, 1.5)):
                painter.setPen(QtGui.QPen(color, width))
                if shape == 'Crosshair':
                    painter.drawLine(3, 11, 19, 11)
                    painter.drawLine(11, 3, 11, 19)
                else:
                    radius = 2 if shape == 'Dot' else 7
                    painter.drawEllipse(center, radius, radius)
            painter.drawPoint(center)
        painter.end()
        return pixmap


def editor_cursor_preference(widget):
    while widget is not None:
        preferences = getattr(widget, 'preferences', None)
        if preferences is not None:
            return preferences.value('appearance/drawing_cursor', 'Crosshair')
        widget = widget.parentWidget()
    return 'Crosshair'
