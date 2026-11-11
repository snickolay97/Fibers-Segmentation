"""Application identity shared by the launcher, windows and Windows shortcuts."""
from pathlib import Path
import sys

from .qt import QtGui


ASSET_DIRECTORY = Path(__file__).with_name('assets')
WINDOWS_APP_ID = 'SoLoData.Desktop'


def app_icon():
    # A QIcon may defer decoding. Check a rendered size before relying on the
    # ICO plugin, and fall back to the bundled PNG when it cannot load it.
    for suffix in ('ico', 'png'):
        icon = QtGui.QIcon(str(ASSET_DIRECTORY / f'solodata.{suffix}'))
        if not icon.pixmap(32, 32).isNull():
            return icon
    return QtGui.QIcon()


def set_windows_app_identity():
    """Set the taskbar group identity before constructing QApplication."""
    if sys.platform == 'win32':
        import ctypes
        setter = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        setter.argtypes = (ctypes.c_wchar_p,)
        setter.restype = ctypes.c_long
        setter(WINDOWS_APP_ID)


def configure_application_branding(application):
    """Give the main window and its dialogs the same bundled icon."""
    application.setWindowIcon(app_icon())


def configure_taskbar_window(window):
    """Give Explorer the icon and launcher for this particular native HWND."""
    if sys.platform != 'win32' or QtGui.QGuiApplication.platformName() != 'windows':
        return False
    import ctypes as c
    from ctypes import wintypes as w
    import os
    from subprocess import list2cmdline
    from uuid import UUID

    class Guid(c.Structure):
        _fields_ = [('bytes', c.c_ubyte * 16)]

    class PropertyKey(c.Structure):
        _fields_ = [('format_id', Guid), ('property_id', w.DWORD)]

    class StringValue(c.Structure):
        _fields_ = [('kind', w.WORD), ('reserved', w.WORD * 3),
                    ('text', w.LPWSTR), ('padding', c.c_void_p)]

    get_store = c.windll.shell32.SHGetPropertyStoreForWindow
    get_store.argtypes = w.HWND, c.POINTER(Guid), c.POINTER(c.c_void_p)
    get_store.restype = c.c_long
    interface = Guid.from_buffer_copy(UUID('886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99').bytes_le)
    store = c.c_void_p()
    if get_store(int(window.winId()), c.byref(interface), c.byref(store)) < 0:
        return False
    methods = c.cast(store, c.POINTER(c.POINTER(c.c_void_p))).contents
    release = c.WINFUNCTYPE(w.ULONG, c.c_void_p)(methods[2])
    set_value = c.WINFUNCTYPE(c.c_long, c.c_void_p, c.POINTER(PropertyKey),
                              c.POINTER(StringValue))(methods[6])
    commit = c.WINFUNCTYPE(c.c_long, c.c_void_p)(methods[7])
    try:
        powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        launcher = ASSET_DIRECTORY.parents[2] / 'launch_app.ps1'
        command = list2cmdline([str(powershell), '-NoProfile', '-WindowStyle', 'Hidden',
                               '-ExecutionPolicy', 'Bypass', '-File', str(launcher), '-Shortcut'])
        fmt = Guid.from_buffer_copy(UUID('9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3').bytes_le)
        # Explorer reads the relaunch properties when it receives the ID.
        for ident, text in ((2, f'{ASSET_DIRECTORY / "solodata.ico"},0'),
                            (4, 'SoLoData'), (1, command), (5, WINDOWS_APP_ID)):
            key = PropertyKey(fmt, ident)
            value = StringValue(kind=31, text=text)  # VT_LPWSTR
            if set_value(store, c.byref(key), c.byref(value)) < 0:
                return False
        return commit(store) >= 0
    finally:
        release(store)
