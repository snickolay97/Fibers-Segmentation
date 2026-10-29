"""Record the actual local implementation and runtime of a completed run."""
import hashlib
import importlib.metadata
from pathlib import Path
import platform
import sys


def runtime_provenance():
    root = Path(__file__).resolve().parents[2]
    digest = hashlib.sha256()
    files = sorted((root / 'src').rglob('*.py'))
    files += [root / name for name in ('app.py', 'requirements.txt')]
    for path in files:
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode('utf-8'))
            digest.update(path.read_bytes())
    dependencies = {}
    for name in ('numpy', 'scipy', 'opencv-python', 'scikit-image', 'pandas',
                 'tifffile', 'Pillow', 'PyQt6', 'PySide6'):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    return dict(code_sha256=digest.hexdigest(), python=sys.version,
                platform=platform.platform(), dependencies=dependencies)
