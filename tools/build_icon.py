"""Rebuild Windows ICO and PNG from the editable SoLoData SVG."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.desktop.qt import QtCore, QtGui, QtWidgets


def build():
    # Keep a reference to the Qt application while painting the SVG.
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    try:
        from PyQt6.QtSvg import QSvgRenderer
    except ImportError:
        from PySide6.QtSvg import QSvgRenderer
    assets = ROOT / 'src' / 'desktop' / 'assets'
    renderer = QSvgRenderer(str(assets / 'solodata.svg'))
    if not renderer.isValid():
        raise ValueError('Invalid icon SVG')
    image = QtGui.QImage(256, 256, QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(image)
    renderer.render(painter)
    painter.end()
    if not image.save(str(assets / 'solodata.png')):
        raise OSError('Could not write icon PNG')
    from PIL import Image
    # Embed multiple sizes in the ICO for Explorer, shortcuts and taskbar use.
    with Image.open(assets / 'solodata.png') as rendered:
        rendered.save(assets / 'solodata.ico', sizes=[(s, s) for s in (16, 20, 24, 32, 48, 64, 128, 256)])
    print(assets / 'solodata.ico')


if __name__ == '__main__':
    build()
