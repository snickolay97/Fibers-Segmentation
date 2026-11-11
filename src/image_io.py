"""TIFF inspection and explicit selection of spatial, channel and plane axes."""
from pathlib import Path
import numpy as np
import tifffile


def _layout(shape, axes):
    """Identify explicit TIFF axes and reject ambiguous non-singleton dimensions."""
    axes = str(axes).upper()
    if len(shape) != len(axes) or axes.count('Y') != 1 or axes.count('X') != 1:
        raise ValueError('TIFF must identify exactly one X and Y spatial axis')
    # S is a pixel-sample axis (such as RGB); C is an explicit channel axis.
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
    """Read layout and calibration metadata without decoding the source pixels."""
    source = Path(path).resolve()
    with tifffile.TiffFile(source) as tif:
        if len(tif.series) != 1:
            raise ValueError('TIFF contains multiple image series; export the intended series separately')
        series = tif.series[0]
        shape, axes, dtype = tuple(series.shape), series.axes, np.dtype(series.dtype)
        from src.tiff_calibration import read_calibration
        calibration = read_calibration(tif)
    channels, planes = _layout(shape, axes)
    if dtype not in (np.dtype('uint8'), np.dtype('uint16')):
        raise ValueError('Supported TIFF data types are uint8 and uint16; found ' + str(dtype))
    return dict(name=source.name, path=str(source), shape=list(shape), axes=axes,
                dtype=str(dtype), width=int(shape[axes.index('X')]),
                height=int(shape[axes.index('Y')]),
                channels=int(shape[channels[0]]) if channels else 1,
                plane_count=int(shape[planes[0]]) if planes else 1,
                plane_axis=axes[planes[0]] if planes else None,
                calibration=calibration)


def _select(path, channel=0, plane=0, *, max_decode_bytes=None):
    """Return a Y/X view and the backing array that owns its storage."""
    info = inspect_tiff(path)
    _validate_selection(info, channel, plane)
    image = open_tiff_array(info, max_decode_bytes=max_decode_bytes)
    return tiff_plane(image, info, channel, plane), image


def _validate_selection(info, channel, plane):
    for name, value, limit in (('Channel', channel, info['channels']), ('Plane', plane, info['plane_count'])):
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or not 0 <= value < limit:
            raise ValueError(f'{name} index is outside this TIFF')


def open_tiff_array(info, *, max_decode_bytes=None):
    # Uncompressed layouts can expose a memory map. Compressed or otherwise
    # unmappable layouts require decoding the series before slicing the axes.
    try:
        return tifffile.memmap(info['path'], series=0, mode='r')
    except (ValueError, OSError):
        if max_decode_bytes is not None:
            from math import prod
            if prod(info['shape']) * np.dtype(info['dtype']).itemsize > max_decode_bytes:
                raise BufferError('TIFF cannot be mapped without decoding the entire series')
        with tifffile.TiffFile(info['path']) as tif:
            return tif.series[0].asarray()


def tiff_plane(image, info, channel, plane):
    """Select a YX channel/plane from an already opened backing array."""
    _validate_selection(info, channel, plane)
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
    # Downstream image operations always index rows before columns.
    if remaining == ['X', 'Y']:
        raw = raw.T
    return raw


def _close_mapping(image):
    if isinstance(image, np.memmap):
        image._mmap.close()


def _processing_uint8(raw):
    """Keep uint8 values and take the high byte of each uint16 pixel."""
    return raw if raw.dtype == np.uint8 else (raw >> 8).astype(np.uint8)


def load_tiff_channel(path, channel=0, plane=0):
    """Return native 2D pixels and their uint8 processing representation.

    Both outputs share storage for uint8 sources. The uint16 source copy retains
    every original bit, and its processing representation is a separate array.
    """
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
    """Read a bounded display preview, either a central crop or a strided view."""
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


def read_tiff_view(path, channel, plane, size, center=None, *, preserve_uint16=False):
    """Read a bounded overview or a native-pixel crop for interactive viewing."""
    raw, owner = _select(path, channel, plane, max_decode_bytes=64 * 1024**2)
    try:
        h, w = raw.shape
        if center is None:
            step = (max(h, w) + size - 1) // size
            pixels, location = raw[::step, ::step], (w, h)
        else:
            step = 1
            x = max(0, min(center[0] - size // 2, w - size))
            y = max(0, min(center[1] - size // 2, h - size))
            pixels, location = raw[y:y + size, x:x + size], (x, y)
        if preserve_uint16 and raw.dtype.kind == 'u' and raw.dtype.itemsize == 2:
            return np.array(pixels, dtype=np.uint16, order='C', copy=True), location, step
        return np.array(_processing_uint8(pixels), order='C', copy=True), location, step
    finally:
        _close_mapping(owner)


def read_tiff_region(path, channel, plane, bounds):
    """Read the requested source rectangle at full bit depth and pixel spacing."""
    raw, owner = _select(path, channel, plane, max_decode_bytes=64 * 1024**2)
    try:
        height, width = raw.shape
        x0, y0, x1, y1 = bounds
        if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            raise ValueError('TIFF region is outside the source image')
        dtype = np.uint8 if raw.dtype.itemsize == 1 else np.uint16
        return np.array(raw[y0:y1, x0:x1], dtype=dtype, order='C', copy=True)
    finally:
        _close_mapping(owner)
