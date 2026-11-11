"""Use either supported Qt binding without mixing objects from both."""

import os
from pathlib import Path

# Initialize OpenCV's native DLLs before Qt and background image decoders.
# On Windows, a fresh GUI process can otherwise fail its first late cv2 import.
if os.name == 'nt':
    import cv2

try:
    # Keep all widgets and signal declarations on one binding. Downstream
    # modules import Signal and Slot from this adapter.
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
    """Configure the application style and choose an available UI font."""
    QtWidgets.QApplication.setStyle("Fusion")
    available = QtGui.QFontDatabase.families()
    if "Segoe UI" not in available and os.name == "nt":
        # The Windows offscreen plugin may require explicit font registration.
        directory = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"):
            path = directory / name
            if path.is_file():
                QtGui.QFontDatabase.addApplicationFont(str(path))
        available = QtGui.QFontDatabase.families()
    family = "Segoe UI" if "Segoe UI" in available else QtWidgets.QApplication.font().family()
    QtWidgets.QApplication.setFont(QtGui.QFont(family, 10))
    return family


def show_centered_window(dialog):
    """Open a modeless, resizable dialog on its owner's screen with a native title bar."""
    types = QtCore.Qt.WindowType
    dialog.setWindowFlags(types.Window | types.WindowTitleHint | types.WindowSystemMenuHint
                          | types.WindowMinMaxButtonsHint | types.WindowCloseButtonHint)
    dialog.setSizeGripEnabled(True)
    parent = dialog.parentWidget()
    screen = parent.screen() if parent is not None else dialog.screen()
    if screen is None:
        dialog.show()
        return
    available = screen.availableGeometry()
    # Reserve room for the native frame, including the title bar on small displays.
    maximum = QtCore.QSize(max(1, available.width() - 32), max(1, available.height() - 64))
    dialog.resize(dialog.size().boundedTo(maximum))
    dialog.move(available.center() - dialog.rect().center())
    dialog.show()
    frame = dialog.frameGeometry()
    dialog.move(available.left() + max(0, (available.width() - frame.width()) // 2),
                available.top() + max(0, (available.height() - frame.height()) // 2))
