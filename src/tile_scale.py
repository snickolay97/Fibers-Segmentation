"""Fixed-size model tiles and reversible coordinate/unit transforms.

Coordinates can be mapped back; lost image detail cannot. Use native images
for measurement. Pixel-centre coordinates and polygon-edge coordinates differ.
"""
import cv2
import numpy as np


def scale_metadata(height, width, target):
    side = max(int(height), int(width), int(target))
    scale = float(target) / side
    return dict(native_crop_shape=[int(height), int(width)],
                padded_native_shape=[side, side], output_shape=[target, target],
                padding_native_ltrb=[0, 0, side-width, side-height],
                output_pixels_per_source_pixel=scale,
                source_pixels_per_output_pixel=1.0/scale,
                source_area_per_output_pixel=1.0/(scale*scale),
                interpolation='INTER_AREA', coordinate_convention='pixel_edges',
                pixel_center_inverse='source=(output+0.5)/scale-0.5',
                downsampling_is_lossless=(side == target))


def fixed_canvas(image, metadata, mask=False):
    side = metadata['padded_native_shape'][0]
    h,w = image.shape[:2]
    if [h,w] != metadata['native_crop_shape']:
        raise ValueError('Native crop shape does not match scale metadata')
    padded = cv2.copyMakeBorder(image,0,side-h,0,side-w,cv2.BORDER_CONSTANT,value=0)
    target = metadata['output_shape'][0]
    if side == target:
        return padded
    # Images and coverage masks use area averages; masks are 0..255 coverage,
    # not an instance segmentation and not an exact inverse ownership map.
    return cv2.resize(padded,(target,target),interpolation=cv2.INTER_AREA)


def output_to_source(points, record, global_coordinates=False, pixel_centers=False):
    points = np.asarray(points,dtype=float)
    if points.shape[-1] != 2:
        raise ValueError('Expected x,y coordinates')
    factor = record['transform']['source_pixels_per_output_pixel']
    result = (points+0.5)*factor-0.5 if pixel_centers else points*factor
    if global_coordinates:
        result = result + [record['x1'],record['y1']]
    return result


def measurement_factors(record, source_pixel_size_um):
    if source_pixel_size_um <= 0:
        raise ValueError('Pixel calibration must be positive')
    length = record['transform']['source_pixels_per_output_pixel'] * source_pixel_size_um
    return {'um_per_output_pixel':length,'um2_per_output_pixel2':length*length}
