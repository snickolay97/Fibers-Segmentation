"""Physical pixel sizes from explicit microscopy metadata, never magnification."""
import math
import xml.etree.ElementTree as ET


_UM = {'m': 1e6, 'cm': 1e4, 'mm': 1e3, 'um': 1, 'µm': 1, 'μm': 1,
       'micron': 1, 'microns': 1, 'micrometer': 1, 'micrometers': 1,
       'micrometre': 1, 'micrometres': 1, 'nm': .001, 'pm': .000001,
       'inch': 25400, 'in': 25400}


def _positive(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError('Invalid physical pixel size')
    return value


def _resolution(page, name):
    """Read samples per unit from a TIFF rational or scalar resolution tag."""
    value = page.tags[name].value
    return _positive(value[0] / value[1] if isinstance(value, tuple) else value)


def read_calibration(tif):
    """Return calibration diagnostics and an isotropic size in micrometers per pixel.

    OME defaults to micrometers when PhysicalSizeXUnit or PhysicalSizeYUnit
    is omitted. For ImageJ, invert X/YResolution and convert from the
    recorded unit. ImageJ spacing is along Z. Report generic inch or
    centimeter resolution separately because it may describe print density.
    """
    result = dict(status='missing', pixel_size_um=None, x_um=None, y_um=None, source=None)
    try:
        if tif.ome_metadata:
            root = ET.fromstring(tif.ome_metadata)
            namespace = root.tag.partition('}')[0].lstrip('{')
            if not namespace.startswith(('http://www.openmicroscopy.org/Schemas/OME/',
                                         'https://www.openmicroscopy.org/Schemas/OME/')):
                return dict(result, status='unsupported_metadata')
            pixels = root.findall('./{*}Image/{*}Pixels')
            if len(pixels) != 1:
                return dict(result, status='ambiguous')
            attrs = pixels[0].attrib
            series = tif.series[0]
            # Require the XML dimensions to match the actual series so stale
            # metadata from an incompatible export cannot supply a scale.
            if any(int(attrs['Size' + axis]) != series.shape[series.axes.index(axis)] for axis in ('X','Y')):
                return dict(result, status='ambiguous', source='OME')
            if not any('PhysicalSize' + axis in attrs for axis in ('X', 'Y')):
                return result
            units = [attrs.get('PhysicalSize' + axis + 'Unit', 'µm') for axis in ('X', 'Y')]
            if any(unit not in _UM for unit in units):
                return dict(result, status='unsupported_unit', source='OME')
            x, y = [_positive(attrs['PhysicalSize' + axis]) * _UM[unit]
                    for axis, unit in zip(('X', 'Y'), units)]
            origin = 'OME PhysicalSizeX/Y'
        elif tif.imagej_metadata and tif.imagej_metadata.get('unit'):
            unit = str(tif.imagej_metadata['unit']).strip().lower()
            if unit not in _UM:
                return dict(result, status='unsupported_unit', source='ImageJ')
            x, y = [_UM[unit] / _resolution(tif.pages[0], key)
                    for key in ('XResolution', 'YResolution')]
            origin = 'ImageJ unit + X/YResolution'
        else:
            page = tif.pages[0]
            unit = int(page.tags['ResolutionUnit'].value) if 'ResolutionUnit' in page.tags else 1
            if unit in (2, 3):
                multiplier = 25400 if unit == 2 else 10000
                x, y = [multiplier / _resolution(page, key) for key in ('XResolution', 'YResolution')]
                return dict(result, status='resolution_only', x_um=x, y_um=y,
                            source='TIFF inch/cm resolution (possible print DPI)')
            return result
        x, y = _positive(x), _positive(y)
        result.update(x_um=x, y_um=y, source=origin)
        # Area conversion uses one scalar squared. Preserve diagnostic X/Y
        # values for a non-square pixel but leave the scalar calibration unset.
        if not math.isclose(x, y, rel_tol=1e-6):
            return dict(result, status='anisotropic')
        return dict(result, status='valid', pixel_size_um=x)
    except (ValueError, TypeError, KeyError, ZeroDivisionError, OverflowError, ET.ParseError):
        return dict(result, status='invalid')
