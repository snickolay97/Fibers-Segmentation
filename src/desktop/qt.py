"""Use either supported Qt binding without mixing objects from both."""

import os
from pathlib import Path

# Initialize OpenCV's native DLLs before Qt and background image decoders.
# On Windows, a fresh GUI process can otherwise fail its first late cv2 import.
if os.name == 'nt':
    import cv2

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    Signal = QtCore.Signal
    Slot = QtCore.Slot
    BINDING = "PySide6"
except ImportError:
    try:
        from PyQt6 import QtCore, QtGui, QtWidgets
        Signal = QtCore.pyqtSignal
        Slot = QtCore.pyqtSlot
        BINDING = "PyQt6"
    except ImportError as exc:
        raise ImportError(
            "SoLoData requires PySide6 or PyQt6 in its Python environment."
        ) from exc


def configure_font():
    """The Windows offscreen plugin needs fonts explicitly registered."""
    QtWidgets.QApplication.setStyle("Fusion")
    available = QtGui.QFontDatabase.families()
    if "Segoe UI" not in available and os.name == "nt":
        directory = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"):
            path = directory / name
            if path.is_file():
                QtGui.QFontDatabase.addApplicationFont(str(path))
        available = QtGui.QFontDatabase.families()
    family = "Segoe UI" if "Segoe UI" in available else QtWidgets.QApplication.font().family()
    QtWidgets.QApplication.setFont(QtGui.QFont(family, 10))
    return family
