"""TIFF inspection and explicit selection of spatial, channel and plane axes."""
from pathlib import Path
import numpy as np
import tifffile


def _layout(shape, axes):
    axes = str(axes).upper()
    if len(shape) != len(axes) or axes.count('Y') != 1 or axes.count('X') != 1:
        raise ValueError('TIFF must identify exactly one X and Y spatial axis')
    channel_axes = [i for i, axis in enumerate(axes) if axis in 'SC']
    plane_axes = [i for i, axis in enumerate(axes) if axis in 'ZIT']
    if len(channel_axes) > 1 or len(plane_axes) > 1:
        raise ValueError('Ambiguous TIFF: select a file with one channel axis and at most one Z/I/T plane axis')
    unknown = [axis for axis, size in zip(axes, shape) if axis not in 'XYSCZIT' and size > 1]
    if unknown:
        raise ValueError('Ambiguous TIFF axes: ' + axes + '. Export with explicit spatial/channel/plane axes.')
    if any(axes.count(axis) > 1 for axis in axes):
        raise ValueError('Duplicate TIFF axes are not supported: ' + axes)
    return channel_axes, plane_axes


def inspect_tiff(path):
    source = Path(path).resolve()
    with tifffile.TiffFile(source) as tif:
        if len(tif.series) != 1:
            raise ValueError('TIFF contains multiple image series; export the intended series separately')
        series = tif.series[0]
        shape, axes, dtype = tuple(series.shape), series.axes, np.dtype(series.dtype)
    channels, planes = _layout(shape, axes)
    if dtype not in (np.dtype('uint8'), np.dtype('uint16')):
        raise ValueError('Supported TIFF data types are uint8 and uint16; found ' + str(dtype))
    return dict(name=source.name, path=str(source), shape=list(shape), axes=axes,
                dtype=str(dtype), width=int(shape[axes.index('X')]),
                height=int(shape[axes.index('Y')]),
                channels=int(shape[channels[0]]) if channels else 1,
                plane_count=int(shape[planes[0]]) if planes else 1)


def _select(path, channel=0, plane=0):
    info = inspect_tiff(path)
    if isinstance(channel, bool) or not isinstance(channel, (int, np.integer)) or not 0 <= channel < info['channels']:
        raise ValueError('Channel index is outside this TIFF')
    if isinstance(plane, bool) or not isinstance(plane, (int, np.integer)) or not 0 <= plane < info['plane_count']:
        raise ValueError('Plane index is outside this TIFF')
    try:
        image = tifffile.memmap(info['path'], series=0, mode='r')
    except (ValueError, OSError):
        with tifffile.TiffFile(info['path']) as tif:
            image = tif.series[0].asarray()
    selection = []
    remaining = []
    for axis in info['axes']:
        if axis in 'XY':
            selection.append(slice(None)); remaining.append(axis)
        elif axis in 'SC':
            selection.append(channel)
        elif axis in 'ZIT':
            selection.append(plane)
        else:
            selection.append(0)
    raw = image[tuple(selection)]
    if remaining == ['X', 'Y']:
        raw = raw.T
    return raw, image


def _close_mapping(image):
    if isinstance(image, np.memmap):
        image._mmap.close()


def _processing_uint8(raw):
    return raw if raw.dtype == np.uint8 else (raw >> 8).astype(np.uint8)


def load_tiff_channel(path, channel=0, plane=0):
    """Return native 2D uint8/uint16 pixels and a separate uint8 processing view."""
    view, owner = _select(path, channel, plane)
    try:
        # Public callers receive ordinary arrays with no live TIFF file handle.
        # Only the selected plane/channel is copied from a mapped stack.
        native_dtype = np.uint8 if view.dtype.itemsize == 1 else np.uint16
        raw = np.array(view, dtype=native_dtype, copy=True, order='C')
        return raw, _processing_uint8(raw)
    finally:
        _close_mapping(owner)


def preview_tiff(path, channel=0, plane=0, max_size=1200, crop=False):
    if not isinstance(max_size, int) or max_size <= 0:
        raise ValueError('max_size must be a positive integer')
    raw, owner = _select(path, channel, plane)
    try:
        h, w = raw.shape
        if crop:
            y, x = max(0, (h-max_size)//2), max(0, (w-max_size)//2)
            selected = raw[y:y+max_size, x:x+max_size]
        else:
            # Sample before conversion to avoid a full native uint8 allocation.
            step = max(1, int(np.ceil(max(h, w)/max_size)))
            selected = raw[::step, ::step]
        return np.array(_processing_uint8(selected), copy=True, order='C')
    finally:
        _close_mapping(owner)
