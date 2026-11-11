"""Assemble a traceable snapshot and publish completed evaluation reports."""

from collections import defaultdict
from errno import EEXIST, ENOTEMPTY
from importlib.util import find_spec
from pathlib import Path
import hashlib
import math
import tempfile

from src.object_classes import CLASS_CATALOG_VERSION
from src.default_settings import MODEL_DEFAULTS
from .i18n import tr
from . import model_evaluation_text
from .model_evaluation import CLASS_IDS, FOREST_TREE_COUNT_RANGE, evaluate, plan_split
from .model_training_input import read_training_rows
from .object_labels import RF_PREDICTORS, _load_document, _measurement, object_key
from .project import atomic_json, timestamp
from .service import _check_cancel, _event, fingerprint, results_are_current


def _sha256(path, cancelled):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            _check_cancel(cancelled)
            digest.update(block)
    return digest.hexdigest()


def assemble_snapshot(project, dataset_ids, groups, area, progress=None, cancelled=None, class_ids=None):
    """Pair reviewed labels with current predictors and traceable group identities."""
    if area not in ('Area', 'Area_um2'):
        raise ValueError(tr('Select a supported area unit.'))
    # Pick one consistent area unit for the entire comparison. Identifiers
    # and class labels are kept alongside the predictor vector for auditing.
    features = [area, *RF_PREDICTORS[1:]]
    workspace = Path(project.workspace).resolve()
    rows, audits, hashes = [], [], {}
    group_overrides = defaultdict(set)
    prepared = []
    ids = sorted(set(dataset_ids))
    for number, ident in enumerate(ids, 1):
        _check_cancel(cancelled)
        _event(progress, 'model_evaluation', 'Checking selected measurements', current=number, total=len(ids))
        dataset = project.get_dataset(ident)
        override = groups.get(ident, '').strip()
        audit = dict(dataset_id=ident, name=dataset.get('name', ident), status='included', measured=0, reviewed=0)
        audits.append(audit)
        if not results_are_current(dataset):
            audit['status'] = 'Missing or stale measurements'
            continue
        output, _, _, measured, indexed, identity = _measurement(dataset)
        document = _load_document(output, indexed, identity)
        reviewed = document['labels'].values()
        audit.update(measured=len(measured), reviewed=len(reviewed))
        if not reviewed:
            audit['status'] = 'No reviewed objects'
            continue
        labels = [label for label in reviewed if class_ids is None or label['Manual_Class_ID'] in class_ids]
        if not labels:
            audit['status'] = 'No reviewed objects in selected classes'
            continue
        source_id = dataset.get('source_id')
        source_path = dataset.get('source_path')
        source = Path(source_path) if source_path else None
        if source_id and source and source.is_file():
            # Hash the TIFF bytes to detect identical imports under different
            # paths. Reuse the hash when the same path appears again.
            if source not in hashes:
                hashes[source] = _sha256(source, cancelled)
            source_key = hashes[source]
            if override:
                group_overrides[source_key].add(override.casefold())
        else:
            if not override:
                audit['status'] = 'Confirm source or experiment'
                continue
            source_key = None
        prepared.append((dataset, audit, indexed, identity, output, labels, source_key, override))
    source_keys = set()
    # Resolve experiment aliases after reading every selected dataset so all
    # aliases of the same source participate in conflict detection.
    for dataset, audit, indexed, identity, output, labels, source_key, override in prepared:
        _check_cancel(cancelled)
        if source_key in source_keys:
            raise ValueError(tr('Select only one measurement dataset per original TIFF, including copies.'))
        if source_key:
            source_keys.add(source_key)
        aliases = group_overrides[source_key] if source_key else {override.casefold()}
        if len(aliases) > 1:
            raise ValueError(tr('One TIFF has conflicting experiment groups.'))
        group = 'group:' + next(iter(aliases)) if aliases else 'tiff:' + dataset['source_id']
        audit.update(measurement_reference=identity['measurement_reference'], csv_sha256=identity['csv_sha256'],
                     source_id=dataset.get('source_id'), source_sha256=source_key, group=group,
                     results_dir=output.relative_to(workspace).as_posix())
        for label in labels:
            tile, ident = label['Tile_Name'], int(label['Object_ID'])
            row = indexed[object_key(tile, ident)]
            try:
                values = [float(row[name]) for name in features]
                if not all(math.isfinite(value) for value in values) or values[0] <= 0:
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                raise ValueError(tr('Missing or invalid predictors in {dataset}. Check area units and calibration.',
                                    dataset=audit['name'])) from None
            rows.append(dict(dataset_id=dataset['id'], tile_name=tile, object_id=ident,
                             group=group, values=values, target=label['Manual_Class_ID']))
    return dict(features=features, rows=rows, datasets=audits, class_catalog_version=CLASS_CATALOG_VERSION)


def run_evaluation(project, dataset_ids, groups, area, seed, folds, preview=False,
                   planned_signature=None, progress=None, cancelled=None, training_file=None,
                   class_ids=None, split_mode=MODEL_DEFAULTS['split_mode'],
                   forest_tree_count=MODEL_DEFAULTS['forest_tree_count']):
    """Preview a frozen split or publish a report for the same confirmed split."""
    if find_spec('sklearn') is None:
        raise ValueError(tr('Install scikit-learn from requirements.txt in the application environment.'))
    if not 0 <= seed <= 2**31 - 1 or folds not in (0, *range(2, 11)):
        raise ValueError(tr('Use a seed from 0 to 2147483647 and K from 2 to 10.'))
    low, high = FOREST_TREE_COUNT_RANGE
    if type(forest_tree_count) is not int or not low <= forest_tree_count <= high:
        raise ValueError(tr('Use {low}–{high} trees in the forest.', low=low, high=high))
    if class_ids is not None:
        if (not isinstance(class_ids, (list, tuple))
                or any(type(label) is not int or label not in CLASS_IDS for label in class_ids)
                or len(set(class_ids)) < 2):
            raise ValueError(tr('Select at least two supported object classes.'))
        class_ids = sorted(set(class_ids))
        if class_ids == list(CLASS_IDS):
            class_ids = None
    if training_file:
        if dataset_ids:
            raise ValueError(tr('Choose either a training table or project datasets.'))
        if area not in ('Area', 'Area_um2'):
            raise ValueError(tr('Select a supported area unit.'))
        source = Path(training_file).resolve(strict=True)
        _event(progress, 'model_evaluation', 'Reading reviewed training table')
        digest = _sha256(source, cancelled)
        features, rows, audits = read_training_rows(source, area, lambda: _check_cancel(cancelled), class_ids)
        if digest != _sha256(source, cancelled):
            raise ValueError(tr('The training table changed while it was being read.'))
        snapshot = dict(features=features, rows=rows, datasets=audits,
                        class_catalog_version=CLASS_CATALOG_VERSION,
                        training_file=dict(name=source.name, sha256=digest))
    else:
        snapshot = assemble_snapshot(project, dataset_ids, groups, area, progress, cancelled, class_ids)
    training_options = dict(forest_tree_count=forest_tree_count, class_ids=class_ids, split_mode=split_mode)
    try:
        if class_ids is not None:
            missing = set(class_ids) - {row['target'] for row in snapshot['rows']}
            if missing:
                raise ValueError(tr('Selected classes without reviewed objects (IDs {ids}).',
                                    ids=', '.join(map(str, sorted(missing)))))
        plan = plan_split(snapshot['rows'], seed, folds, cancelled, split_mode)
        if class_ids is not None:
            plan['classes'] = class_ids
        plan_error = ''
    except ValueError as error:
        if not preview:
            raise
        plan, plan_error = None, str(error)
    signature = fingerprint(dict(snapshot=snapshot, plan=plan, training_options=training_options))
    payload = dict(schema_version=1, snapshot=snapshot, plan=plan, signature=signature,
                   training_options=training_options, plan_error=plan_error)
    _check_cancel(cancelled)
    if preview:
        from .storage_names import version_file
        path = version_file(Path(project.workspace) / 'jobs', 'Model_plan')
        atomic_json(path, payload)
    else:
        # Verify the current labels, features, groups and split against the
        # preview before fitting. An intervening relabel invalidates approval.
        if planned_signature != signature:
            raise ValueError(tr('The data or split changed. Preview the plan again.'))

        def notify(current, total):
            _event(progress, 'model_evaluation', 'Fitting and evaluating models', current=current, total=total)

        from joblib import dump
        import numpy as np
        import sklearn

        folder = Path(project.workspace) / 'model_evaluations'
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.evaluation_', dir=folder) as temp:
            staged = Path(temp) / 'evaluation'
            staged.mkdir()

            def save_model(key, model):
                _check_cancel(cancelled)
                filename = key + '.joblib'
                # Persist the exact final fit and enough context to reconstruct
                # its input schema and match it to the evaluation snapshot.
                dump(dict(schema_version=1, estimator=model, model=key,
                          features=snapshot['features'], classes=model.classes_.tolist(),
                          class_catalog_version=CLASS_CATALOG_VERSION, signature=signature,
                          demo=plan['demo'], split_mode=split_mode,
                          runtime={'scikit-learn': sklearn.__version__, 'numpy': np.__version__}),
                     staged / filename, compress=3)
                return filename

            payload['report'] = evaluate(snapshot['rows'], snapshot['features'], plan, notify, cancelled,
                                         save_model, forest_tree_count)
            for result in payload['report']['models'].values():
                if result.get('artifact'):
                    result['artifact_sha256'] = _sha256(staged / result['artifact'], cancelled)
            payload['created_at'] = timestamp()
            atomic_json(staged / 'report.json', payload)
            # Publish one complete folder. A cancellation or failed artifact
            # write leaves the previous evaluations visible and intact.
            number = 1
            while True:
                _check_cancel(cancelled)
                destination = folder / f'Evaluation_{number:03d}'
                try:
                    staged.rename(destination)
                    break
                except OSError as error:
                    if error.errno not in (EEXIST, ENOTEMPTY):
                        raise
                    number += 1
            path = destination / 'report.json'
    return dict(status='completed', preview=preview, path=str(path))
