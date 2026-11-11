"""Render an additive RGB visualization from registered samples of one TIFF."""

import os
from pathlib import Path
import tempfile

import numpy as np
from PIL import Image
import tifffile

from .image_io import _close_mapping, inspect_tiff, open_tiff_array, tiff_plane


MAX_COMPRESSED_BYTES = 512 * 1024**2
MAX_SMALL_EXPORT_PIXELS = 32_000_000


def _render(views, height, width, rows, cols):
    accumulator = np.zeros((height, width, 3), dtype=np.float32)
    for pixels, lut in views:
        samples = pixels[rows, cols]
        for index in range(3):
            accumulator[..., index] += lut[:, index][samples]
    return np.rint(np.minimum(accumulator, 255)).astype(np.uint8)


def composite(path, plane, layers, *, destination=None, cancelled=lambda: False):
    """Preview up to 1600 px per side or export RGB8 on the original pixel grid."""
    info = inspect_tiff(path)
    width, height = info['width'], info['height']
    target = Path(destination) if destination else None
    if target and target.resolve() == Path(path).resolve():
        raise ValueError('Choose a different file from the source TIFF.')
    suffix = target.suffix.lower() if target else ''
    if target and suffix not in ('.tif', '.tiff', '.png', '.jpg', '.jpeg'):
        raise ValueError('Choose TIFF, PNG or JPEG.')
    is_tiff = suffix in ('.tif', '.tiff')
    if target and not is_tiff and width * height > MAX_SMALL_EXPORT_PIXELS:
        raise ValueError('Choose TIFF for images over 32 megapixels.')
    if cancelled():
        return None
    step = max(1, (max(height, width) + 1599) // 1600)
    preview_height, preview_width = (height + step - 1) // step, (width + step - 1) // step
    if not layers:
        if target:
            raise ValueError('Select at least one channel.')
        return np.zeros((preview_height, preview_width, 3), dtype=np.uint8), step
    image = open_tiff_array(info, max_decode_bytes=MAX_COMPRESSED_BYTES)
    try:
        maximum = np.iinfo(info['dtype']).max
        samples = np.arange(maximum + 1, dtype=np.float32) / maximum
        views = [(tiff_plane(image, info, channel, plane),
                  np.minimum(samples * gain, 1)[:, None] * (np.asarray(color, np.float32) * opacity))
                 for channel, color, gain, opacity in layers]
        if not target:
            return _render(views, preview_height, preview_width,
                           slice(None, None, step), slice(None, None, step)), step
        with tempfile.TemporaryDirectory(prefix='.composite_', dir=target.parent) as temporary:
            stage = Path(temporary) / 'composite.tif'
            calibration = info['calibration']
            physical = {}
            if calibration.get('status') == 'valid':
                scale = calibration['pixel_size_um']
                physical = dict(PhysicalSizeX=scale, PhysicalSizeY=scale,
                                PhysicalSizeXUnit='µm', PhysicalSizeYUnit='µm')
            output = tifffile.memmap(stage, shape=(height, width, 3), dtype=np.uint8,
                                     bigtiff=width * height * 3 >= 2**32 - 2**25,
                                     photometric='rgb', ome=True, metadata={'axes': 'YXS', **physical})
            staged_output = stage
            try:
                band = max(1, min(128, 500_000 // width))
                for y in range(0, height, band):
                    if cancelled():
                        return None
                    stop = min(y + band, height)
                    output[y:stop] = _render(views, stop - y, width, slice(y, stop), slice(None))
                output.flush()
                if not is_tiff and not cancelled():
                    staged_output = stage.with_suffix(suffix)
                    Image.fromarray(output).save(staged_output, **({'quality': 95} if suffix in ('.jpg', '.jpeg') else {}))
            finally:
                _close_mapping(output)
            if not cancelled():
                os.replace(staged_output, target)
                return target
            return None
    finally:
        _close_mapping(image)
