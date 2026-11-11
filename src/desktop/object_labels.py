"""Manual object targets scoped to one immutable measurement version.

Training exports pair numeric features with the reviewed Manual_Class_ID.
The original YOLO Class_ID and Class_Name serve as provenance metadata.
Calibrated measurements also include Area_um2.
"""
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import tempfile
import sqlite3

from .project import atomic_json, timestamp
from .i18n import tr
from . import label_storage_text
from .file_revision import file_revision
from .label_database import LabelDatabase, DATABASE_FILENAME, STORAGE_FILENAME
from src.object_classes import OBJECT_CLASS_CATALOG, CLASS_CATALOG_VERSION


CANONICAL_MANUAL_CLASSES = OBJECT_CLASS_CATALOG
OBJECT_CLASSES = CANONICAL_MANUAL_CLASSES
CLASS_BY_KEY = {item['key']: item for item in CANONICAL_MANUAL_CLASSES}
LEGACY_CLASS_IDS = dict(particle=0, fiber=1, agglomeration=2, crossed_tubes=3,
                       self_crossed_tube=4, adhered_objects=5)
RF_PREDICTORS = ('Area', 'Aspect_Ratio', 'Solidity', 'Euler_Number', 'Endpoints', 'Branch_Points')
TRACEABILITY_COLUMNS = ('Large_Image', 'Tile_Name', 'Object_ID', 'Class_ID', 'Class_Name',
                        'Measurement_Space', 'Source_Pixels_Per_Output_Pixel')
MANUAL_COLUMNS = ('Manual_Class_ID', 'Manual_Class', 'Reviewed', 'Dataset_ID',
                  'Measurement_Reference', 'Class_Catalog_Version')
LABELS_FILENAME = 'manual_object_labels.json'
_MEASUREMENT_CACHE = {}


def object_key(tile_name, object_id):
    """Return the local identity shared by the CSV, gallery and label sidecar."""
    if not isinstance(tile_name, str) or not tile_name or any(c in tile_name for c in '/\\:') or tile_name in ('.','..'):
        raise ValueError(tr('Invalid object tile name'))
    if isinstance(object_id, bool):
        raise ValueError(tr('Object ID must be a positive integer'))
    try:
        ident = int(object_id)
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError(tr('Object ID must be a positive integer')) from error
    if ident <= 0 or (isinstance(object_id, float) and object_id != ident):
        raise ValueError(tr('Object ID must be a positive integer'))
    return '{}/{}'.format(tile_name, ident)


def _measurement(dataset, *, fresh=False):
    """Index an immutable feature table and bind labels to its byte digest."""
    dataset_id, signature = dataset.get('id'), dataset.get('measurement_signature')
    if not isinstance(dataset_id, str) or not dataset_id or not isinstance(signature, str) or not signature:
        raise ValueError(tr('Object classification requires a saved measurement version'))
    output = Path(dataset.get('results_dir') or '').resolve()
    source = Path(dataset.get('last_csv') or '').resolve()
    if not output.is_dir() or not source.is_file() or source.parent != output:
        raise ValueError(tr('Measurement CSV is missing or outside its measurement directory'))
    revision = file_revision(source)
    cache_key = (str(source), dataset_id, signature, revision)
    cached = _MEASUREMENT_CACHE.get(cache_key) if revision[-1] is not None else None
    if not fresh and cached is not None:
        return cached
    raw_csv = source.read_bytes()
    with io.StringIO(raw_csv.decode('utf-8-sig'), newline='') as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        if not {'Tile_Name', 'Object_ID'}.issubset(fields) or len(set(fields)) != len(fields):
            raise ValueError(tr('Measurement CSV has invalid object identity columns'))
        if set(fields).intersection(MANUAL_COLUMNS):
            raise ValueError(tr('Scientific measurement CSV must not contain manual targets'))
        rows = list(reader)
    indexed = {}
    for row in rows:
        key = object_key(row.get('Tile_Name'), row.get('Object_ID'))
        if key in indexed:
            raise ValueError(tr('Measurement CSV contains duplicate object identities'))
        indexed[key] = row
    reference = dataset_id + ':' + signature
    identity = dict(dataset_id=dataset_id, measurement_signature=signature,
                    measurement_reference=reference,
                    csv_sha256=hashlib.sha256(raw_csv).hexdigest())
    if file_revision(source) != revision:
        raise ValueError(tr('Measurement CSV changed while being read. Reload measurements.'))
    # Keep one immutable measurement snapshot, not an unbounded project cache.
    # Callers must not mutate its scientific rows or identity.
    result = output, source, fields, rows, indexed, identity
    _MEASUREMENT_CACHE.clear()
    _MEASUREMENT_CACHE[cache_key] = result
    return result


def _load_legacy_document(output, indexed, identity):
    path = output/LABELS_FILENAME
    if not path.exists():
        return dict(schema_version=1, class_catalog_version=CLASS_CATALOG_VERSION, **identity, labels={})
    if path.is_symlink():
        raise ValueError(tr('Manual label output must not be a symlink'))
    document = json.loads(path.read_text(encoding='utf-8'))
    return _validate_document(document, indexed, identity)


def _validate_document(document, indexed, identity):
    if not isinstance(document, dict) or type(document.get('schema_version')) is not int or document.get('schema_version') != 1:
        raise ValueError(tr('Unsupported manual object labels format'))
    catalog_version = document.get('class_catalog_version')
    if type(catalog_version) is not int or catalog_version not in (1, CLASS_CATALOG_VERSION):
        raise ValueError(tr('Unsupported manual object labels format'))
    if any(document.get(key) != value for key, value in identity.items()):
        raise ValueError(tr('Manual labels belong to a different measurement version or CSV'))
    labels = document.get('labels')
    if not isinstance(labels, dict):
        raise ValueError(tr('Invalid manual object labels'))
    catalog_ids = LEGACY_CLASS_IDS if catalog_version == 1 else {key:item['id'] for key,item in CLASS_BY_KEY.items()}
    for key, label in labels.items():
        if key not in indexed or not isinstance(label, dict):
            raise ValueError(tr('Manual label references an unknown measured object'))
        class_key = label.get('Manual_Class')
        ident = label.get('Manual_Class_ID')
        expected_id = catalog_ids.get(class_key) if isinstance(class_key,str) else None
        if not isinstance(class_key,str) or class_key not in CLASS_BY_KEY or not isinstance(ident,int) or isinstance(ident,bool) or ident != expected_id or label.get('Reviewed') is not True:
            raise ValueError(tr('Invalid manual class or review state'))
        if object_key(label.get('Tile_Name'), label.get('Object_ID')) != key:
            raise ValueError(tr('Manual label object identity mismatch'))
    if catalog_version == 1:
        # Interpret the old IDs only through their validated semantic keys.
        # Read-only loads and exports never rewrite historical annotations.
        for label in labels.values():
            label['Manual_Class_ID'] = CLASS_BY_KEY[label['Manual_Class']]['id']
        document['class_catalog_version'] = CLASS_CATALOG_VERSION
        document['migrated_from_class_catalog_version'] = 1
    return document


def _load_document(output, indexed, identity):
    store = LabelDatabase(output)
    try:
        if store.present:
            return _validate_document(store.document(identity), indexed, identity)
        return _load_legacy_document(output, indexed, identity)
    except sqlite3.Error as error:
        raise ValueError(tr('The manual-label database cannot be read. Restore it from a full project backup.')) from error


def _report(output, indexed, document, current):
    labels = document['labels']
    counts = {key: 0 for key in CLASS_BY_KEY}
    for label in labels.values():
        counts[label['Manual_Class']] += 1
    return dict(classes=[dict(item) for item in CANONICAL_MANUAL_CLASSES],
                labels={key:dict(value) for key,value in labels.items()}, assigned=len(labels),
                total=len(indexed), unassigned=len(indexed)-len(labels), class_counts=counts,
                class_catalog_version=CLASS_CATALOG_VERSION,
                measurement_reference=document['measurement_reference'],
                path=str(output/(DATABASE_FILENAME if LabelDatabase(output).present else LABELS_FILENAME)),
                storage='sqlite' if LabelDatabase(output).present else 'json', current=bool(current))


def load_object_labels(dataset, current=True):
    if not dataset.get('results_dir') or not dataset.get('last_csv'):
        return dict(classes=[dict(item) for item in CANONICAL_MANUAL_CLASSES], labels={},
                    assigned=0, total=0, unassigned=0, class_counts={key:0 for key in CLASS_BY_KEY},
                    class_catalog_version=CLASS_CATALOG_VERSION,
                    measurement_reference=None, path=None, current=False)
    output, source, fields, rows, indexed, identity = _measurement(dataset)
    document = _load_document(output, indexed, identity)
    return _report(output, indexed, document, current)


def _save_object_class(dataset, tile_name, object_id, class_key, *, compact=False):
    """Persist one assignment atomically, using None to clear the target."""
    if class_key is not None and (not isinstance(class_key,str) or class_key not in CLASS_BY_KEY):
        raise ValueError(tr('Unknown manual object class'))
    csv_path = Path(dataset.get('last_csv') or '').resolve()
    if not csv_path.is_file():
        raise ValueError(tr('Measurement CSV is missing or outside its measurement directory'))
    revision = file_revision(csv_path)
    output, source, fields, rows, indexed, identity = _measurement(dataset)
    # Bind the transaction check to the snapshot, not a later file revision.
    if file_revision(source) != revision:
        raise ValueError(tr('Measurement CSV changed while being read. Reload measurements.'))
    key = object_key(tile_name, object_id)
    if key not in indexed:
        raise ValueError(tr('The selected object does not exist in this measurement version'))
    store = LabelDatabase(output)
    if not store.present:
        legacy = output/LABELS_FILENAME
        legacy_revision = file_revision(legacy) if legacy.exists() else None
        document = _load_legacy_document(output, indexed, identity)
        store.initialize(document, indexed, legacy_revision=legacy_revision)
    label = None
    if class_key is not None:
        definition = CLASS_BY_KEY[class_key]
        label = dict(Tile_Name=tile_name, Object_ID=int(object_id),
            Manual_Class_ID=definition['id'], Manual_Class=class_key, Reviewed=True,
            updated_at=timestamp())
    delta = store.assign(identity, key, label, csv_path=source, csv_revision=revision)
    if compact:
        report = dict(class_catalog_version=CLASS_CATALOG_VERSION,
                      measurement_reference=identity['measurement_reference'],
                      path=str(store.path), storage='sqlite', current=True,
                      unassigned=delta['total']-delta['assigned'])
    else:
        report = _report(output, indexed, _load_document(output, indexed, identity), True)
    report.update(delta)
    return report


def save_object_class(dataset, tile_name, object_id, class_key, *, compact=False):
    """Keep storage failures distinct from the rebuildable catalog's errors."""
    try:
        return _save_object_class(dataset, tile_name, object_id, class_key, compact=compact)
    except sqlite3.Error as error:
        raise ValueError(tr('Manual label database operation failed: {error}', error=str(error))) from error


def export_label_snapshot(dataset, destination):
    """Explicit JSON interchange for older readers; never replace live authority."""
    output, source, fields, rows, indexed, identity = _measurement(dataset, fresh=True)
    document = _load_document(output, indexed, identity)
    target = validate_export_destination(dataset, destination)
    atomic_json(target, document)
    return dict(path=str(target), assigned=len(document['labels']), measurement_reference=identity['measurement_reference'])


def validate_export_destination(dataset, destination, allow_current_source=False):
    """Return a checked output path; protect immutable measurement artifacts.

    This helper only needs results_dir and last_csv, so CSV widgets can use it
    without loading class labels, provenance or the project's scientific data.
    """
    source_value = dataset.get('last_csv')
    if not source_value:
        raise ValueError(tr('Measurement CSV is missing or outside its measurement directory'))
    source = Path(source_value).resolve()
    output = Path(dataset.get('results_dir') or source.parent).resolve()
    if source.parent != output:
        raise ValueError(tr('Measurement CSV is missing or outside its measurement directory'))
    target = Path(destination).resolve()
    if target == source and allow_current_source:
        return target
    version_root = output.parent
    protected = target == source or target.name.casefold() in {
        'project.json', 'project.sqlite3', 'local_runtime.json', DATABASE_FILENAME.casefold(),
        STORAGE_FILENAME.casefold(), *(DATABASE_FILENAME+suffix for suffix in ('-journal','-wal','-shm'))}
    if version_root in target.parents:
        relative = target.relative_to(version_root)
        reserved = (source.name, LABELS_FILENAME, DATABASE_FILENAME, STORAGE_FILENAME,
                    DATABASE_FILENAME+'-journal', DATABASE_FILENAME+'-wal',
                    DATABASE_FILENAME+'-shm', 'measurement_run.json')
        protected |= target.name.casefold() in {name.casefold() for name in reserved}
        protected |= 'verification_masks' in {part.casefold() for part in relative.parts}
    if protected:
        raise ValueError(tr('Export must not overwrite measurement data, object masks, or manual labels'))
    return target


def write_training_csv(dataset, destination, only_labeled=True):
    """Export reviewed targets and numeric features with their source references."""
    output, source, fields, rows, indexed, identity = _measurement(dataset, fresh=True)
    document = _load_document(output, indexed, identity)
    target = validate_export_destination(dataset, destination)
    missing = [name for name in RF_PREDICTORS if name not in fields]
    if missing:
        raise ValueError(tr('Training export requires feature columns: {columns}', columns=', '.join(missing)))
    # Original Class_ID/Class_Name remain traceable metadata, not predictors;
    # the separately reviewed Manual_Class_ID is the supervised target.
    export_fields = [name for name in fields if name in TRACEABILITY_COLUMNS or name in RF_PREDICTORS or name == 'Area_um2']
    selected = []
    for row in rows:
        label = document['labels'].get(object_key(row['Tile_Name'], row['Object_ID']))
        if only_labeled and not label:
            continue
        manual = dict(Manual_Class_ID=label['Manual_Class_ID'] if label else '',
                      Manual_Class=label['Manual_Class'] if label else '', Reviewed=bool(label),
                      Dataset_ID=identity['dataset_id'], Measurement_Reference=identity['measurement_reference'],
                      Class_Catalog_Version=CLASS_CATALOG_VERSION)
        selected.append(dict({name:row[name] for name in export_fields}, **manual))
    predictors = list(RF_PREDICTORS) + (['Area_um2'] if 'Area_um2' in fields else [])
    for row in selected:
        for feature in predictors:
            try:
                value = float(row[feature])
                valid = math.isfinite(value)
            except (ValueError, TypeError, OverflowError):
                valid = False
            if not valid:
                raise ValueError(tr('Feature {feature} must be a finite number for object {object}',
                                    feature=feature, object=object_key(row['Tile_Name'], row['Object_ID'])))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        # Stage on the output filesystem so a failed export leaves the
        # previous destination intact and replacement is atomic.
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                         prefix='.training_', suffix='.csv', dir=target.parent, delete=False) as handle:
            temporary = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=export_fields+list(MANUAL_COLUMNS))
            writer.writeheader()
            writer.writerows(selected)
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return dict(path=str(target), rows=len(selected), assigned=len(document['labels']),
                only_labeled=bool(only_labeled), target='Manual_Class_ID', predictors=predictors,
                class_catalog_version=CLASS_CATALOG_VERSION,
                measurement_reference=identity['measurement_reference'])
