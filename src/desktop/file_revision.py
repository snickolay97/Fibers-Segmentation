"""Cheap revision tokens for immutable measurement snapshots, including Windows."""
import ctypes
import os
from pathlib import Path


if os.name == 'nt':
    from ctypes import wintypes

    class _BasicInfo(ctypes.Structure):
        _fields_ = [(name, ctypes.c_longlong) for name in
                    ('creation', 'access', 'write', 'change')] + [('attributes', wintypes.DWORD)]

    _kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    _kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    _kernel.CreateFileW.restype = wintypes.HANDLE
    _kernel.GetFileInformationByHandleEx.argtypes = (wintypes.HANDLE, ctypes.c_int,
                                                    ctypes.c_void_p, wintypes.DWORD)
    _kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
    _kernel.CloseHandle.argtypes = (wintypes.HANDLE,)


def file_revision(path):
    """Include change time so restoring size/mtime cannot reuse an old CSV cache.

    On a filesystem without Windows change-time support, a None token disables
    reuse. Correctness takes precedence over the optimization in that case.
    """
    path = Path(path)
    stat = path.stat()
    token = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    if os.name != 'nt':
        return token
    handle = _kernel.CreateFileW(str(path), 0x80, 7, None, 3, 0x02000000, None)
    if handle == ctypes.c_void_p(-1).value:
        return token + (None,)
    try:
        info = _BasicInfo()
        if not _kernel.GetFileInformationByHandleEx(handle, 0, ctypes.byref(info), ctypes.sizeof(info)):
            return token + (None,)
        if info.change <= 0:
            return token + (None,)
        return token + (info.change,)
    finally:
        _kernel.CloseHandle(handle)
