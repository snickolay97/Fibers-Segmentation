"""Train and apply a local pixel classifier on reviewed native-grid masks."""

from collections import defaultdict
from errno import EEXIST, ENOTEMPTY
import json
from pathlib import Path
import re
import tempfile

import cv2
import numpy as np

from src.default_settings import (MODEL_DEFAULTS, PIXEL_SEGMENTATION_DEFAULTS as DEFAULTS,
                                  PIXEL_SEGMENTATION_DEFAULTS_VERSION as FEATURE_VERSION)
from src.image_io import _processing_uint8
from src.object_classes import CLASS_CATALOG_VERSION, OBJECT_CLASS_CATALOG
from src.partition_geometry import dataset_path, png_shape
from src.tile_edits import file_sha256, tile_artifact_path
from . import model_evaluation_text, service
from .i18n import register_translations, tr
from .model_evaluation import CLASS_IDS, FOREST_TREE_COUNT_RANGE
from .object_labels import _load_document, _measurement, object_key
from .object_merging import exact_objects
from .project import atomic_json, timestamp
from .storage_names import version_path
from .tile_edit import _read_png, _write_png


_TEXT = {
    'Select active native tiles with valid grayscale pixels and ownership masks (up to 32 MP).': (
        'Выберите активные native-тайлы до 32 Мп с серыми пикселями и масками принадлежности.',
        'בחרו אריחי מקור פעילים עד 32 מגה־פיקסל עם פיקסלים אפורים ומסכות שיוך תקינות.'),
    'Pixel segmentation needs current measurements and reviewed exact masks.': (
        'Для сегментации по пикселям нужны актуальные измерения и проверенные точные маски.',
        'לפילוח פיקסלים נדרשות מדידות עדכניות ומסכות מדויקות שנבדקו.'),
    'Select a dataset and at least one supported class for pixel segmentation.': (
        'Выберите набор и хотя бы один поддерживаемый класс для сегментации по пикселям.',
        'בחרו מערך ומחלקה נתמכת אחת לפחות לפילוח פיקסלים.'),
    'Too few usable pixels for these segmentation labels ({codes}). Review masks and background or change the selection.': (
        'Слишком мало пригодных пикселей для кодов сегментации ({codes}). Проверьте маски и фон или измените выбор.',
        'אין מספיק פיקסלים מתאימים לקודי הפילוח ({codes}). בדקו מסכות ורקע או שנו את הבחירה.'),
    'Use a trusted pixel model saved in this project.': (
        'Используйте доверенную модель сегментации, сохранённую в этом проекте.',
        'השתמשו במודל פילוח מהימן שנשמר בפרויקט זה.'),
    'The pixel model or its metadata changed or is incompatible. Train it again.': (
        'Модель сегментации или её метаданные изменились либо несовместимы. Обучите модель заново.',
        'מודל הפילוח או המטא־נתונים שלו השתנו או אינם תואמים. אמנו אותו שוב.'),
    'Sampling reviewed masks and candidate background': (
        'Выборка пикселей проверенных масок и предполагаемого фона', 'דגימת מסכות שנבדקו ורקע משוער'),
    'Fitting the pixel model': ('Обучение пиксельной модели', 'אימון מודל הפיקסלים'),
    'Predicting native pixels': ('Прогноз на native-пикселях', 'חיזוי פיקסלים באריח המקור'),
    'Use a seed from 0 to 2147483647.': ('Укажите зерно от 0 до 2147483647.', 'הזינו זרע בין 0 ל־2147483647.'),
}
register_translations({key: item[0] for key, item in _TEXT.items()},
                      hebrew={key: item[1] for key, item in _TEXT.items()})

BACKGROUND, IGNORE = 0, 255
_CHUNK = 512
_FEATURES = ('intensity', *(f'{moment}_{2 * radius + 1}' for radius in DEFAULTS['local_radii']
                           for moment in ('mean', 'std')))
_COLORS = ((230, 114, 0), (0, 158, 115), (220, 110, 205),
           (0, 159, 230), (233, 180, 86), (0, 94, 213))


def _pixel_root(project):
    workspace = Path(project.workspace).resolve()
    root = workspace / 'pixel_segmentation'
    if root.resolve() != root:
        raise ValueError(tr('Use a trusted pixel model saved in this project.'))
    return root


def _publish(staged, root, prefix, cancelled):
    while True:
        service._check_cancel(cancelled)
        destination = version_path(root, prefix)
        try:
            staged.rename(destination)
        except OSError as error:
            if error.errno not in (EEXIST, ENOTEMPTY):
                raise
        else:
            return destination


def _native_tile(dataset, record):
    message = tr('Select active native tiles with valid grayscale pixels and ownership masks (up to 32 MP).')
    shape = record.get('transform', {}).get('native_crop_shape')
    if (record.get('excluded') or not record.get('native_filename') or not record.get('valid_mask')
            or not shape or shape[0] * shape[1] > DEFAULTS['max_tile_pixels']):
        raise ValueError(message)
    native_path = tile_artifact_path(dataset['path'], record, 'native_filename')
    valid_path = tile_artifact_path(dataset['path'], record, 'valid_mask')
    if png_shape(native_path) != tuple(shape) or png_shape(valid_path) != tuple(shape):
        raise ValueError(message)
    pixels, native_hash = _read_png(native_path)
    valid, valid_hash = _read_png(valid_path)
    if (pixels is None or pixels.shape != tuple(shape) or pixels.dtype not in (np.uint8, np.uint16)
            or valid is None or valid.shape != pixels.shape or valid.dtype != np.uint8
            or not valid.any() or not np.isin(valid, (0, 255)).all()):
        raise ValueError(message)
    revision = record.get('edit_reference')
    synthetic = False
    if revision:
        metadata = dataset_path(dataset['path'], revision + '/edit.json')
        synthetic = json.loads(metadata.read_text(encoding='utf-8')).get('contains_synthetic_signal', False)
    provenance = dict(tile_id=record['id'], tile_name=Path(record['filename']).stem,
                      native_sha256=native_hash, valid_sha256=valid_hash,
                      edit_reference=revision, native_bit_depth=pixels.dtype.itemsize * 8,
                      contains_synthetic_signal=synthetic)
    return _processing_uint8(pixels), valid > 0, provenance


def _patches(shape):
    height, width = shape
    for y in range(0, height, _CHUNK):
        for x in range(0, width, _CHUNK):
            yield y, min(y + _CHUNK, height), x, min(x + _CHUNK, width)


def _features(gray, valid, box):
    y0, y1, x0, x1 = box
    radii = DEFAULTS['local_radii']
    halo = max(radii)
    top, left = max(0, y0 - halo), max(0, x0 - halo)
    region = np.s_[top:y1 + halo, left:x1 + halo]
    core = np.s_[y0 - top:y1 - top, x0 - left:x1 - left]
    pixels = gray[region].astype(np.float32)
    owned = valid[region].astype(np.float32)
    signal = pixels * owned
    square = signal * pixels
    values = [pixels[core]]
    # A halo makes the computed values identical across chunk boundaries.
    # Normalize moments by valid neighbors so padding is never background data.
    for radius in radii:
        kernel = (2 * radius + 1,) * 2
        weight = cv2.boxFilter(owned, -1, kernel, normalize=False, borderType=cv2.BORDER_CONSTANT)
        np.maximum(weight, 1, out=weight)
        mean = cv2.boxFilter(signal, -1, kernel, normalize=False, borderType=cv2.BORDER_CONSTANT) / weight
        moment2 = cv2.boxFilter(square, -1, kernel, normalize=False, borderType=cv2.BORDER_CONSTANT) / weight
        values.extend((mean[core], np.sqrt(np.maximum(moment2[core] - mean[core] ** 2, 0))))
    return np.stack(values, axis=-1)


def _label_pixels(valid, objects, labels, selected):
    codes = np.full(valid.shape, IGNORE, np.uint8)
    occupied = np.zeros(valid.shape, bool)
    for obj in objects:
        entry = obj['entry']
        if entry['measurement_space'] != 'source_pixels' or tuple(entry['tile_shape']) != valid.shape:
            raise ValueError(tr('Pixel segmentation needs current measurements and reviewed exact masks.'))
        local_y, local_x = np.nonzero(obj['mask'])
        x, y = obj['origin']
        rows, columns = local_y + y, local_x + x
        if not valid[rows, columns].all():
            raise ValueError(tr('Pixel segmentation needs current measurements and reviewed exact masks.'))
        collision = occupied[rows, columns]
        codes[rows[collision], columns[collision]] = IGNORE
        occupied[rows, columns] = True
        label = labels.get(object_key(entry['tile_name'], entry['object_id']))
        if label and label['Manual_Class_ID'] in selected:
            observed = ~collision & ~obj['manual_added'][local_y, local_x]
            codes[rows[observed], columns[observed]] = label['Manual_Class_ID'] + 1
    # Pixels near any measured object, including unreviewed and excluded
    # classes, are ambiguous. The distant region is only candidate background.
    size = 2 * DEFAULTS['background_margin'] + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    near_object = cv2.dilate(occupied.astype(np.uint8), kernel)
    codes[valid & (near_object == 0)] = BACKGROUND
    return codes


def _collect_samples(gray, valid, codes, reservoirs, seen, rng, cancelled):
    limit = DEFAULTS['samples_per_label']
    for box in _patches(gray.shape):
        service._check_cancel(cancelled)
        y0, y1, x0, x1 = box
        labels = codes[y0:y1, x0:x1].ravel()
        features = None
        for code in reservoirs:
            indices = np.flatnonzero(labels == code)
            count = len(indices)
            if not count:
                continue
            previous = seen[code]
            seen[code] += count
            capacity = min(limit, seen[code])
            # The hypergeometric draw preserves uniform sampling over all
            # processed pixels with a fixed memory bound per label.
            added = int(rng.hypergeometric(count, previous, capacity))
            if not added:
                continue
            if features is None:
                features = _features(gray, valid, box).reshape(-1, len(_FEATURES))
            old = reservoirs[code]
            retained = old[rng.choice(len(old), capacity - added, replace=False)]
            chosen = features[rng.choice(indices, added, replace=False)]
            reservoirs[code] = np.concatenate((retained, chosen))


def train_pixel_segmentation(project, dataset_ids, class_ids,
                             forest_tree_count=MODEL_DEFAULTS['forest_tree_count'], seed=42,
                             progress=None, cancelled=None):
    """Fit a balanced demo model from confirmed foreground and candidate background."""
    from joblib import dump
    import sklearn
    from sklearn.ensemble import RandomForestClassifier

    if (not isinstance(dataset_ids, list) or not dataset_ids or not all(isinstance(i, str) for i in dataset_ids)
            or not isinstance(class_ids, list) or not class_ids
            or any(type(label) is not int or label not in CLASS_IDS for label in class_ids)):
        raise ValueError(tr('Select a dataset and at least one supported class for pixel segmentation.'))
    low, high = FOREST_TREE_COUNT_RANGE
    if type(forest_tree_count) is not int or not low <= forest_tree_count <= high:
        raise ValueError(tr('Use {low}–{high} trees in the forest.', low=low, high=high))
    if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
        raise ValueError(tr('Use a seed from 0 to 2147483647.'))
    selected = set(class_ids)
    label_codes = [BACKGROUND, *(label + 1 for label in sorted(selected))]
    reservoirs = {code: np.empty((0, len(_FEATURES)), np.float32) for code in label_codes}
    seen = dict.fromkeys(label_codes, 0)
    rng = np.random.default_rng(seed)
    datasets = []
    for ident in sorted(set(dataset_ids)):
        service._check_cancel(cancelled)
        dataset = project.get_dataset(ident)
        if not service.results_are_current(dataset):
            raise ValueError(tr('Pixel segmentation needs current measurements and reviewed exact masks.'))
        output, _, _, rows, indexed, identity = _measurement(dataset)
        document = _load_document(output, indexed, identity)
        labels = document['labels']
        names = {label['Tile_Name'] for label in labels.values() if label['Manual_Class_ID'] in selected}
        if not names:
            continue
        records = {Path(record['filename']).stem: record for record in service.tile_records(dataset)
                   if not record['excluded']}
        rows_by_tile = defaultdict(list)
        for row in rows:
            rows_by_tile[row['Tile_Name']].append(row)
        source = dict(identity, manual_labels_signature=service.fingerprint(document), tiles=[])
        for number, name in enumerate(sorted(names), 1):
            service._check_cancel(cancelled)
            service._event(progress, 'pixel_segmentation', 'Sampling reviewed masks and candidate background',
                           current=number, total=len(names))
            if name not in records:
                raise ValueError(tr('Pixel segmentation needs current measurements and reviewed exact masks.'))
            gray, valid, provenance = _native_tile(dataset, records[name])
            source['tiles'].append(provenance)
            if provenance['contains_synthetic_signal']:
                # Painting changed the signal seen by the filters. Even a
                # nearby observed pixel would then get synthetic context.
                continue
            objects = exact_objects(dataset, name, rows_by_tile[name])
            provenance['mask_hashes'] = {str(obj['entry']['object_id']): obj['mask_sha256'] for obj in objects}
            provenance['location_manifest_sha256'] = file_sha256(output / 'verification_masks' / 'object_locations.json')
            codes = _label_pixels(valid, objects, labels, selected)
            _collect_samples(gray, valid, codes, reservoirs, seen, rng, cancelled)
        datasets.append(source)
    count = min(map(len, reservoirs.values()))
    if count < 2:
        missing = ', '.join(str(code) for code, data in reservoirs.items() if len(data) < 2)
        raise ValueError(tr('Too few usable pixels for these segmentation labels ({codes}). Review masks and background or change the selection.',
                            codes=missing))
    x = np.concatenate([data[rng.choice(len(data), count, replace=False)] for data in reservoirs.values()])
    y = np.repeat(np.asarray(label_codes, np.uint8), count)
    service._check_cancel(cancelled)
    service._event(progress, 'pixel_segmentation', 'Fitting the pixel model')
    model = RandomForestClassifier(n_estimators=forest_tree_count, max_depth=16, min_samples_leaf=2,
                                   random_state=seed, n_jobs=1)
    model.fit(x, y)

    root = _pixel_root(project)
    root.mkdir(exist_ok=True)
    metadata = dict(schema_version=1, kind='pixel_segmentation', created_at=timestamp(),
                    feature_version=FEATURE_VERSION, features=_FEATURES, class_catalog_version=CLASS_CATALOG_VERSION,
                    class_ids=sorted(selected), forest_tree_count=forest_tree_count, seed=seed,
                    samples_per_label=count, available_pixels=seen, datasets=datasets,
                    background_margin_px=DEFAULTS['background_margin'], label_codes=_code_names(selected),
                    background_assumption='Owned pixels outside the margin around all measured masks',
                    evaluation='demonstration_no_independent_test', runtime={'scikit-learn': sklearn.__version__})
    with tempfile.TemporaryDirectory(prefix='.pixel_', dir=root) as folder:
        staged = Path(folder) / 'model'
        staged.mkdir()
        service._check_cancel(cancelled)
        model_path = staged / 'model.joblib'
        dump(dict(kind='pixel_segmentation', feature_version=FEATURE_VERSION, estimator=model),
             model_path, compress=3)
        metadata['model_sha256'] = file_sha256(model_path)
        atomic_json(staged / 'metadata.json', metadata)
        path = _publish(staged, root, 'Model', cancelled)
    return dict(status='completed', path=str(path / 'model.joblib'), metadata=str(path / 'metadata.json'))


def _code_names(selected):
    codes = {str(BACKGROUND): 'background', str(IGNORE): 'outside_ownership'}
    codes.update({str(entry['id'] + 1): entry['key']
                  for entry in OBJECT_CLASS_CATALOG if entry['id'] in selected})
    return codes


def _load_model(project, model_path):
    from joblib import load
    from sklearn.ensemble import RandomForestClassifier

    root = _pixel_root(project)
    path = Path(model_path).resolve(strict=True)
    if (path.name != 'model.joblib' or path.parent.parent != root
            or not re.fullmatch(r'Model_\d{3,5}', path.parent.name)):
        raise ValueError(tr('Use a trusted pixel model saved in this project.'))
    metadata_path = path.with_name('metadata.json')
    if not metadata_path.is_file() or metadata_path.is_symlink():
        raise ValueError(tr('Use a trusted pixel model saved in this project.'))
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    message = tr('The pixel model or its metadata changed or is incompatible. Train it again.')
    if not isinstance(metadata, dict):
        raise ValueError(message)
    labels = metadata.get('class_ids')
    if (metadata.get('kind') != 'pixel_segmentation' or metadata.get('schema_version') != 1
            or metadata.get('feature_version') != FEATURE_VERSION or tuple(metadata.get('features', [])) != _FEATURES
            or metadata.get('class_catalog_version') != CLASS_CATALOG_VERSION
            or not isinstance(labels, list) or not labels
            or any(type(label) is not int or label not in CLASS_IDS for label in labels)
            or metadata.get('label_codes') != _code_names(labels)
            or metadata.get('model_sha256') != file_sha256(path)):
        raise ValueError(message)
    # Joblib executes pickle loading. This path accepts only the versioned
    # models created inside the user's trusted project, with an intact digest.
    bundle = load(path)
    if not isinstance(bundle, dict):
        raise ValueError(message)
    model = bundle.get('estimator')
    if (bundle.get('kind') != 'pixel_segmentation' or bundle.get('feature_version') != FEATURE_VERSION
            or not isinstance(model, RandomForestClassifier) or model.n_features_in_ != len(_FEATURES)
            or set(map(int, model.classes_)) != {BACKGROUND, *(label + 1 for label in labels)}):
        raise ValueError(message)
    return model, metadata, path.parent


def apply_pixel_segmentation(project, dataset_id, tile_id, model_path, progress=None, cancelled=None):
    """Predict a separate semantic map and overlay on one active native tile."""
    dataset = project.get_dataset(dataset_id)
    service._check_cancel(cancelled)
    record = next((record for record in service.tile_records(dataset) if record['id'] == tile_id), None)
    if record is None:
        raise ValueError(tr('Select active native tiles with valid grayscale pixels and ownership masks (up to 32 MP).'))
    gray, valid, tile = _native_tile(dataset, record)
    model, metadata, root = _load_model(project, model_path)
    classes = np.full(gray.shape, IGNORE, np.uint8)
    overlay = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    patches = list(_patches(gray.shape))
    for number, box in enumerate(patches, 1):
        service._check_cancel(cancelled)
        service._event(progress, 'pixel_segmentation', 'Predicting native pixels', current=number, total=len(patches))
        y0, y1, x0, x1 = box
        region = np.s_[y0:y1, x0:x1]
        owned = valid[region]
        if not owned.any():
            continue
        codes = model.predict(_features(gray, valid, box)[owned])
        class_region = classes[region]
        overlay_region = overlay[region]
        class_region[owned] = codes
        for label in metadata['class_ids']:
            mask = class_region == label + 1
            pixels = overlay_region[mask].astype(np.uint16)
            overlay_region[mask] = (pixels + np.asarray(_COLORS[label], np.uint16)) // 2
    with tempfile.TemporaryDirectory(prefix='.prediction_', dir=root) as folder:
        staged = Path(folder) / 'prediction'
        staged.mkdir()
        service._check_cancel(cancelled)
        _write_png(staged / 'classes.png', classes)
        _write_png(staged / 'overlay.png', overlay)
        colors = {str(label): list(reversed(_COLORS[label])) for label in metadata['class_ids']}
        atomic_json(staged / 'metadata.json', dict(schema_version=1, created_at=timestamp(), dataset_id=dataset_id,
                                                 tile=tile, label_codes=metadata['label_codes'],
                                                 overlay_colors_rgb=colors,
                                                 model_sha256=metadata['model_sha256']))
        path = _publish(staged, root, 'Prediction', cancelled)
    return dict(status='completed', path=str(path / 'classes.png'), overlay=str(path / 'overlay.png'),
                metadata=str(path / 'metadata.json'), overlay_colors_rgb=colors)
