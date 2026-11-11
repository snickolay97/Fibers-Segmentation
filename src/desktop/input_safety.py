"""Protect editable values from accidental wheel input without disabling scrolling."""

from .qt import QtCore, QtGui, QtWidgets


class ParameterWheelGuard(QtCore.QObject):
    """Application event filter scoped to one window and its owned panels."""

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner

    def eventFilter(self, watched, event):
        if event.type() != QtCore.QEvent.Type.Wheel or not isinstance(watched, QtWidgets.QWidget):
            return False
        current = watched
        control = None
        belongs = False
        # A wheel event can arrive on an editor's child. Walk up to both the
        # value control and its owning window before intercepting anything.
        while current is not None:
            # An explicitly opened combo popup is a list that must still scroll.
            if control is None and isinstance(current, QtWidgets.QAbstractItemView):
                return False
            if isinstance(current, (QtWidgets.QAbstractSpinBox, QtWidgets.QComboBox,
                                    QtWidgets.QSlider, QtWidgets.QDial)):
                control = current
            if current is self.owner:
                belongs = True
                break
            current = current.parentWidget()
        if control is None or not belongs:
            return False
        # Forward the wheel event to the nearest enclosing scroll area.
        current = control.parentWidget()
        while current is not None:
            if isinstance(current, QtWidgets.QAbstractScrollArea):
                viewport = current.viewport()
                point = viewport.mapFromGlobal(event.globalPosition().toPoint())
                forwarded = QtGui.QWheelEvent(QtCore.QPointF(point), event.globalPosition(),
                    event.pixelDelta(), event.angleDelta(), event.buttons(), event.modifiers(),
                    event.phase(), event.inverted())
                QtWidgets.QApplication.sendEvent(viewport, forwarded)
                break
            current = current.parentWidget()
        event.accept()
        return True


def install_parameter_wheel_guard(owner):
    """Install one wheel guard per owner so rebuilding the UI keeps it active."""
    guard = getattr(owner, '_parameter_wheel_guard', None)
    if guard is None:
        guard = ParameterWheelGuard(owner)
        owner._parameter_wheel_guard = guard
        QtWidgets.QApplication.instance().installEventFilter(guard)
    return guard
