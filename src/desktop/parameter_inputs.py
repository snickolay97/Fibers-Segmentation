"""Visible +/− step controls even when Qt's stylesheet hides native glyphs."""
from .qt import QtCore, QtGui, QtWidgets


class _StepSymbols:
    def paintEvent(self, event):
        # Paint over the native button rectangles so the original hit areas,
        # keyboard behavior and step constraints stay in charge.
        super().paintEvent(event)
        option = QtWidgets.QStyleOptionSpinBox()
        self.initStyleOption(option)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        enabled = self.stepEnabled()
        for control, direction in ((QtWidgets.QStyle.SubControl.SC_SpinBoxUp, 1),
                                   (QtWidgets.QStyle.SubControl.SC_SpinBoxDown, -1)):
            rect = self.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_SpinBox,
                                              option, control, self)
            if rect.isEmpty():
                continue
            flag = (QtWidgets.QAbstractSpinBox.StepEnabledFlag.StepUpEnabled if direction > 0
                    else QtWidgets.QAbstractSpinBox.StepEnabledFlag.StepDownEnabled)
            active = self.isEnabled() and not self.isReadOnly() and bool(enabled & flag)
            group = QtGui.QPalette.ColorGroup.Active if active else QtGui.QPalette.ColorGroup.Disabled
            painter.setPen(QtGui.QPen(self.palette().color(group, QtGui.QPalette.ColorRole.Text), 1.7))
            center = QtCore.QPointF(rect.center())
            painter.drawLine(center + QtCore.QPointF(-4, 0), center + QtCore.QPointF(4, 0))
            if direction > 0:
                painter.drawLine(center + QtCore.QPointF(0, -4), center + QtCore.QPointF(0, 4))
        painter.end()


class ParameterSpinBox(_StepSymbols, QtWidgets.QSpinBox):
    pass


class ParameterDoubleSpinBox(_StepSymbols, QtWidgets.QDoubleSpinBox):
    pass
