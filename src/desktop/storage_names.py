"""Readable Windows-safe names; internal identities remain in project JSON."""
from pathlib import Path
import re


def readable_name(value):
    """Sanitize a display name for Windows, including reserved device stems."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value)).strip(' .')[:100] or 'Image'
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
        name = '_' + name
    return name


def unused_file(parent, name, occupied=()):
    """Choose a filename, accounting for paths reserved by a pending migration."""
    parent, name = Path(parent), Path(name)
    for index in range(1, 100000):
        candidate = parent / (name.name if index == 1 else f'{name.stem}_{index:03d}{name.suffix}')
        if not candidate.exists() and str(candidate).casefold() not in occupied:
            return candidate
    raise OSError('No unused project filename is available')


def version_path(parent, prefix):
    """Plan a version name for a caller that publishes a staged directory."""
    parent = Path(parent)
    for index in range(1, 100000):
        path = parent / f'{readable_name(prefix)}_{index:03d}'
        if not path.exists():
            return path
    raise OSError('No unused project version is available')


def version_file(parent, prefix, suffix='.json'):
    """Plan a readable versioned file under the caller's project writer lock."""
    parent = Path(parent)
    for index in range(1, 100000):
        path = parent / f'{readable_name(prefix)}_{index:03d}{suffix}'
        if not path.exists():
            return path
    raise OSError('No unused project filename is available')


def new_version(parent, prefix):
    """Reserve a version atomically when the caller writes directly into it."""
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    for index in range(1, 100000):
        path = parent / f'{readable_name(prefix)}_{index:03d}'
        try:
            path.mkdir()
            return path
        except FileExistsError:
            continue
    raise OSError('No unused project version is available')
