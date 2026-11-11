"""Common tool names and keyboard shortcuts for native-grid editors."""

from .i18n import register_translations
from .qt import QtGui


_KEYS = {'pan': 'H', 'paint': 'B', 'erase': 'E'}

register_translations({'Brush': 'Кисть', 'Eraser': 'Ластик'})


def tool_label(label, tool):
    return f'{label} ({_KEYS[tool]})' if tool in _KEYS else label


def install_tool_shortcuts(owner, selector, viewer, *, erase='erase'):
    def select(tool):
        if not selector.isVisible() or not selector.isEnabled():
            return
        viewer.ruler_button.setChecked(False)
        selector.setCurrentIndex(selector.findData(tool))

    shortcuts = []
    for mode, key in _KEYS.items():
        shortcut = QtGui.QShortcut(QtGui.QKeySequence(key), owner)
        shortcut.activated.connect(lambda tool=erase if mode == 'erase' else mode: select(tool))
        shortcuts.append(shortcut)
    return shortcuts
