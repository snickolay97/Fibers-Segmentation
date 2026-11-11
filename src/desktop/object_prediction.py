"""Apply a saved object classifier and keep human review separate from training labels."""

from errno import EEXIST, ENOTEMPTY
import json
import math
from pathlib import Path
import re
import tempfile

from src.object_classes import CLASS_CATALOG_VERSION
from .evaluation_crops import EvaluationCrops
from .i18n import register_translations, tr
from .model_evaluation import CLASS_IDS
from .model_evaluation_data import _sha256
from .object_labels import RF_PREDICTORS, _load_document, _measurement, object_key
from .project import atomic_json, timestamp
from .service import _check_cancel, _event, fingerprint, results_are_current, tile_records
from .storage_names import version_path


_TEXT = {
    'Select a saved decision tree or forest from this project.': (
        'Выберите сохранённое дерево или лес из этого проекта.',
        'בחרו עץ החלטה או יער שנשמר בפרויקט זה.'),
    'The saved model or its training report is damaged or incompatible.': (
        'Сохранённая модель или отчёт об обучении повреждены либо несовместимы.',
        'המודל השמור או דוח האימון פגומים או אינם תואמים.'),
    'The saved model requires scikit-learn {version}.': (
        'Для сохранённой модели нужна версия scikit-learn {version}.',
        'המודל השמור דורש scikit-learn בגרסה {version}.'),
    'Recalculate the selected measurements before predicting object classes.': (
        'Пересчитайте выбранные измерения перед прогнозом классов объектов.',
        'חשבו מחדש את המדידות שנבחרו לפני חיזוי מחלקות העצמים.'),
    'Select measured tiles from the current dataset.': (
        'Выберите тайлы с измеренными объектами из текущего набора.',
        'בחרו אריחים עם עצמים שנמדדו ממערך הנתונים הנוכחי.'),
    'There are no objects without a manual class in the selected measurements.': (
        'В выбранных измерениях нет объектов без ручного класса.',
        'אין עצמים ללא מחלקה ידנית במדידות שנבחרו.'),
    'Reading unlabelled measured objects': (
        'Чтение измеренных объектов без ручного класса',
        'קריאת עצמים שנמדדו ללא מחלקה ידנית'),
    'Predicting object classes': ('Прогноз классов объектов', 'חיזוי מחלקות עצמים'),
    'The prediction report or review is damaged or belongs to another project.': (
        'Отчёт прогнозов или отметки проверки повреждены либо относятся к другому проекту.',
        'דוח התחזיות או סימוני הסקירה פגומים או שייכים לפרויקט אחר.'),
    'Select an object from this prediction and a valid review decision.': (
        'Выберите объект из этого прогона и допустимую отметку проверки.',
        'בחרו עצם מהתחזית הזו והחלטת סקירה תקינה.'),
    'Another window is saving this review. Try again.': (
        'Другое окно сохраняет эту проверку. Повторите попытку.',
        'חלון אחר שומר את הסקירה הזו. נסו שוב.'),
}
register_translations({key: pair[0] for key, pair in _TEXT.items()},
                      hebrew={key: pair[1] for key, pair in _TEXT.items()})

PREDICTION_FOLDER = 'object_predictions'
_BAD_MODEL = 'The saved model or its training report is damaged or incompatible.'
_BAD_REVIEW = 'The prediction report or review is damaged or belongs to another project.'


def _folder(workspace, name, error):
    folder = workspace / name
    if folder.resolve() != folder:
        raise ValueError(tr(error))
    return folder


def _report_path(workspace, value, folder, prefix, error):
    root = _folder(workspace, folder, error)
    candidate = workspace / Path(value)
    path = candidate.resolve(strict=True)
    if (path != candidate or path.name != 'report.json' or path.parent.parent != root
            or not re.fullmatch(rf'{prefix}_\d{{3,}}', path.parent.name) or not path.is_file()):
        raise ValueError(tr(error))
    return path


def _load_classifier(workspace, evaluation_path, model_key, cancelled):
    """Load a local evaluation artifact after checking its report and expected schema."""
    if model_key not in ('tree', 'forest'):
        raise ValueError(tr('Select a saved decision tree or forest from this project.'))
    import numpy as np
    import sklearn
    from joblib import load
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.tree import DecisionTreeClassifier

    selection_error = 'Select a saved decision tree or forest from this project.'
    try:
        path = _report_path(workspace, evaluation_path, 'model_evaluations', 'Evaluation', selection_error)
        evaluation = json.loads(path.read_text(encoding='utf-8'))
        model_info = evaluation['report']['models'][model_key]
        snapshot, plan = evaluation['snapshot'], evaluation['plan']
        features = snapshot['features']
        identity = dict(snapshot=snapshot, plan=plan)
        if 'training_options' in evaluation:
            identity['training_options'] = evaluation['training_options']
        classes = sorted({snapshot['rows'][index]['target'] for index in plan['train']})
        filename = model_key + '.joblib'
        if (evaluation['schema_version'] != 1 or evaluation['signature'] != fingerprint(identity)
                or snapshot['class_catalog_version'] != CLASS_CATALOG_VERSION or not classes
                or any(type(label) is not int or label not in CLASS_IDS for label in classes)
                or features not in [list(RF_PREDICTORS), ['Area_um2', *RF_PREDICTORS[1:]]]
                or model_info['artifact'] != filename):
            raise ValueError(tr(_BAD_MODEL))
        model_path = path.with_name(filename)
        if model_path.resolve(strict=True) != model_path or not model_path.is_file():
            raise ValueError(tr(selection_error))
        version = evaluation['report']['runtime']['scikit-learn']
    except (OSError, KeyError, IndexError, TypeError, AttributeError, RuntimeError, json.JSONDecodeError) as exc:
        raise ValueError(tr(_BAD_MODEL)) from exc
    if version != sklearn.__version__:
        raise ValueError(tr('The saved model requires scikit-learn {version}.', version=version))
    digest = _sha256(model_path, cancelled)
    if 'artifact_sha256' in model_info and model_info['artifact_sha256'] != digest:
        raise ValueError(tr(_BAD_MODEL))
    _check_cancel(cancelled)
    # Joblib loads pickle. Only use evaluation artifacts from the current
    # trusted project, and check the publisher's digest when it was recorded.
    try:
        bundle = load(model_path)
        estimator = bundle['estimator']
        expected_type = DecisionTreeClassifier if model_key == 'tree' else RandomForestClassifier
        if (bundle['schema_version'] != 1 or bundle['model'] != model_key
                or bundle['features'] != features or bundle['classes'] != classes
                or bundle['class_catalog_version'] != CLASS_CATALOG_VERSION
                or bundle['signature'] != evaluation['signature']
                or bundle['runtime'] != {'scikit-learn': version, 'numpy': np.__version__}
                or type(estimator) is not expected_type or estimator.n_features_in_ != len(features)
                or estimator.classes_.tolist() != classes):
            raise ValueError(tr(_BAD_MODEL))
    except Exception as exc:
        raise ValueError(tr(_BAD_MODEL)) from exc
    if _sha256(model_path, cancelled) != digest:
        raise ValueError(tr(_BAD_MODEL))
    provenance = dict(name=model_key, classes=classes, report_path=path.relative_to(workspace).as_posix(),
                      sha256=digest, training_signature=evaluation['signature'],
                      training_split_mode=bundle.get('split_mode', 'group'), training_demo=bundle.get('demo', False))
    return estimator, evaluation, provenance


def _source_overlap(dataset, identity, evaluation, cancelled):
    """Match exact measurement identities or TIFF bytes, keeping name hints separate."""
    snapshot, plan = evaluation['snapshot'], evaluation['plan']
    seen_ids = {snapshot['rows'][index]['dataset_id'] for index in (*plan['train'], *plan['test'])}
    audits = [entry for entry in snapshot['datasets'] if entry['dataset_id'] in seen_ids]
    reference = identity['measurement_reference'].casefold()
    matching_ids = {entry['dataset_id'] for entry in audits
                    if entry.get('measurement_reference', '').casefold() == reference}
    exact_rows = {
        object_key(row['tile_name'], row['object_id']): part
        for part in ('train', 'test') for index in plan[part]
        if (row := snapshot['rows'][index])['dataset_id'] in matching_ids and row.get('tile_name')
    }
    source_path = Path(dataset['source_path']) if dataset.get('source_path') else None
    known_hashes = [entry.get('source_sha256') for entry in audits]
    source_digest = (_sha256(source_path, cancelled)
                     if not matching_ids and any(known_hashes) and source_path and source_path.is_file() else None)
    overlap = 'unknown'
    if matching_ids or (source_digest is not None and source_digest in known_hashes):
        overlap = 'same_source'
    elif source_digest is not None and all(known_hashes):
        overlap = 'different_source'
    names = {Path(str(dataset.get('name', ''))).stem.casefold()}
    if source_path is not None:
        names.add(source_path.stem.casefold())
    name_matches = any(Path(entry.get('name', '')).stem.casefold() in names for entry in audits)
    return dict(source_overlap=overlap, source_name_matches=name_matches,
                same_measurement=bool(matching_ids)), exact_rows


def predict_objects(project, evaluation_path, model_key, dataset_id, tile_names=None, *,
                    progress=None, cancelled=None):
    """Publish predictions for unlabelled objects of one current measurement."""
    import numpy as np

    _check_cancel(cancelled)
    workspace = Path(project.workspace).resolve()
    dataset = project.get_dataset(dataset_id)
    if not results_are_current(dataset):
        raise ValueError(tr('Recalculate the selected measurements before predicting object classes.'))
    output, source, _, _, indexed, identity = _measurement(dataset)
    if workspace not in output.parents:
        raise ValueError(tr('Recalculate the selected measurements before predicting object classes.'))
    available = {Path(record['filename']).stem for record in tile_records(dataset) if not record['excluded']}
    if tile_names is not None:
        if (not isinstance(tile_names, list) or not tile_names
                or any(not isinstance(tile, str) or tile not in available for tile in tile_names)):
            raise ValueError(tr('Select measured tiles from the current dataset.'))
        available = set(tile_names)
    _event(progress, 'object_prediction', tr('Reading unlabelled measured objects'))
    labels = _load_document(output, indexed, identity)['labels']
    selected = [(key, row) for key, row in indexed.items()
                if row['Tile_Name'] in available and key not in labels]
    if not selected:
        raise ValueError(tr('There are no objects without a manual class in the selected measurements.'))
    estimator, evaluation, provenance = _load_classifier(workspace, evaluation_path, model_key, cancelled)
    features = evaluation['snapshot']['features']
    scope, exact_rows = _source_overlap(dataset, identity, evaluation, cancelled)
    provenance.update(scope)
    crops = EvaluationCrops(workspace)
    dataset_info = dict(identity, name=dataset.get('name', dataset_id),
                        results_dir=output.relative_to(workspace).as_posix(),
                        source_id=dataset.get('source_id'))
    mask_root = output / 'verification_masks'
    rows = []
    for key, row in selected:
        _check_cancel(cancelled)
        tile, ident = row['Tile_Name'], int(row['Object_ID'])
        try:
            values = [float(row[feature]) for feature in features]
            if (values[0] <= 0 or not all(math.isfinite(value) for value in values)
                    or row.get('Measurement_Space', 'source_pixels') != 'source_pixels'):
                raise ValueError()
        except (ValueError, TypeError, KeyError, OverflowError):
            raise ValueError(tr('Missing or invalid predictors in {dataset}. Check area units and calibration.',
                                dataset=dataset_info['name'])) from None
        mask, crop = crops.paths(dataset_info['results_dir'], tile, ident)
        rows.append(dict(dataset_id=dataset_id, tile_name=tile, object_id=ident, values=values,
                         evaluation_overlap=exact_rows.get(key),
                         mask_path=mask.relative_to(workspace).as_posix() if mask and mask_root in mask.parents else None,
                         crop_path=crop.relative_to(workspace).as_posix() if crop and mask_root in crop.parents else None))
    for start in range(0, len(rows), 4096):
        _check_cancel(cancelled)
        batch = rows[start:start + 4096]
        # Only this numeric matrix reaches scikit-learn. Both supported
        # estimators predict the class with maximum estimated probability.
        scores = estimator.predict_proba(np.asarray([row['values'] for row in batch], dtype=float))
        for row, probabilities, winner in zip(batch, scores, scores.argmax(axis=1)):
            row.update(predicted=provenance['classes'][winner], confidence=float(probabilities[winner]))
        _event(progress, 'object_prediction', tr('Predicting object classes'),
               current=start + len(batch), total=len(rows))
    # Bind the report to the measurement bytes and eligible identities used
    # above. An intervening change must leave the destination unpublished.
    current_labels = _load_document(output, indexed, identity)['labels']
    if (identity['csv_sha256'] != _sha256(source, cancelled) or not results_are_current(dataset)
            or any(key in current_labels for key, _ in selected)):
        raise ValueError(tr('Recalculate the selected measurements before predicting object classes.'))
    snapshot = dict(features=features, datasets=[dataset_info], rows=rows, tile_names=sorted(available),
                    class_catalog_version=CLASS_CATALOG_VERSION)
    payload = dict(schema_version=1, model=provenance, snapshot=snapshot, created_at=timestamp())
    payload['signature'] = fingerprint(payload)
    root = _folder(workspace, PREDICTION_FOLDER, _BAD_REVIEW)
    root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.prediction_', dir=root) as directory:
        staged = Path(directory) / 'prediction'
        atomic_json(staged / 'report.json', payload)
        while True:
            _check_cancel(cancelled)
            destination = version_path(root, 'Prediction')
            try:
                staged.rename(destination)
                break
            except OSError as error:
                if error.errno not in (EEXIST, ENOTEMPTY):
                    raise
    return dict(status='completed', path=str(destination / 'report.json'), rows=len(rows))


def _load_prediction(project, prediction_path, *, check_images):
    """Read and validate a project-owned prediction, including its frozen row paths."""
    workspace = Path(project.workspace).resolve()
    try:
        path = _report_path(workspace, prediction_path, PREDICTION_FOLDER, 'Prediction', _BAD_REVIEW)
        report = json.loads(path.read_text(encoding='utf-8'))
        signature = report.pop('signature')
        snapshot = report['snapshot']
        model = report['model']
        classes = model['classes']
        dataset, = snapshot['datasets']
        relative_results = Path(dataset['results_dir'])
        results = (workspace / relative_results).resolve()
        if (report['schema_version'] != 1 or fingerprint(report) != signature
                or snapshot['class_catalog_version'] != CLASS_CATALOG_VERSION
                or model['name'] not in ('tree', 'forest') or not isinstance(classes, list) or not classes
                or any(type(label) is not int or label not in CLASS_IDS for label in classes)
                or not snapshot['rows']
                or relative_results.is_absolute() or '..' in relative_results.parts
                or workspace not in results.parents):
            raise ValueError(tr(_BAD_REVIEW))
        mask_root = relative_results / 'verification_masks'
        resolved_masks = (workspace / mask_root).resolve() if check_images else None
        keys = set()
        for row in snapshot['rows']:
            key = object_key(row['tile_name'], row['object_id'])
            if (key in keys or row['dataset_id'] != dataset['dataset_id']
                    or type(row['predicted']) is not int or row['predicted'] not in classes):
                raise ValueError(tr(_BAD_REVIEW))
            keys.add(key)
            for field in ('mask_path', 'crop_path'):
                if row.get(field):
                    relative = Path(row[field])
                    if mask_root not in relative.parents or '..' in relative.parts:
                        raise ValueError(tr(_BAD_REVIEW))
                    if check_images and (results not in resolved_masks.parents
                                         or resolved_masks not in (workspace / relative).resolve().parents):
                        raise ValueError(tr(_BAD_REVIEW))
        return dict(report, signature=signature)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        raise ValueError(tr(_BAD_REVIEW)) from exc


def load_prediction(project, prediction_path):
    return _load_prediction(project, prediction_path, check_images=True)


def _review_predictions(report):
    return {object_key(row['tile_name'], row['object_id']): row['predicted']
            for row in report['snapshot']['rows']}


def _valid_correction(actual_class, predicted):
    return type(actual_class) is int and actual_class in CLASS_IDS and actual_class != predicted


def _decisions(path, report, predictions):
    try:
        if path.is_symlink():
            raise ValueError()
        if not path.exists():
            return {}
        document = json.loads(path.read_text(encoding='utf-8'))
        decisions = document['decisions']
        if document['schema_version'] != 1 or document['prediction_signature'] != report['signature']:
            raise ValueError()
        for key, value in decisions.items():
            if (key not in predictions or value['decision'] not in ('correct', 'incorrect')
                    or not isinstance(value['time'], str)):
                raise ValueError()
            # Older errors have no reference class. Keep the decision without
            # guessing which class was meant, even for a two-class model.
            if 'actual_class' in value and (value['decision'] != 'incorrect'
                    or not _valid_correction(value['actual_class'], predictions[key])):
                raise ValueError()
        return decisions
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(tr(_BAD_REVIEW)) from exc


def load_review(project, prediction_path):
    report = _load_prediction(project, prediction_path, check_images=False)
    path = (Path(project.workspace) / prediction_path).with_name('review.json')
    return _decisions(path, report, _review_predictions(report))


def save_review(project, prediction_path, tile_name, object_id, decision, *, actual_class=None):
    """Record a human judgment separately, without touching measurement labels."""
    from .qt import QtCore

    report = _load_prediction(project, prediction_path, check_images=False)
    path = (Path(project.workspace) / prediction_path).with_name('review.json')
    key = object_key(tile_name, object_id)
    predictions = _review_predictions(report)
    if (key not in predictions or decision not in (None, 'correct', 'incorrect')
            or (decision == 'incorrect' and not _valid_correction(actual_class, predictions[key]))
            or (decision != 'incorrect' and actual_class is not None)):
        raise ValueError(tr('Select an object from this prediction and a valid review decision.'))
    lock_path = path.with_suffix('.lock')
    if lock_path.is_symlink():
        raise ValueError(tr(_BAD_REVIEW))
    lock = QtCore.QLockFile(str(lock_path))
    if not lock.tryLock(0):
        raise ValueError(tr('Another window is saving this review. Try again.'))
    try:
        decisions = _decisions(path, report, predictions)
        if decision is None:
            decisions.pop(key, None)
        else:
            decisions[key] = dict(decision=decision, time=timestamp())
            if decision == 'incorrect':
                decisions[key]['actual_class'] = actual_class
        atomic_json(path, dict(schema_version=1, prediction_signature=report['signature'],
                               decisions=decisions))
        return decisions
    finally:
        lock.unlock()
