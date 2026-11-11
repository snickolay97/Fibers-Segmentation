"""Read reviewed tabular exports without inferring sources from tile IDs."""

from collections import defaultdict
from contextlib import contextmanager
import csv
import math
from pathlib import Path

from src.object_classes import CLASS_CATALOG_VERSION, OBJECT_CLASS_CATALOG
from .i18n import tr
from .object_labels import RF_PREDICTORS


@contextmanager
def _table(path):
    """Stream CSV or one worksheet, keeping the input read-only."""
    if path.suffix.casefold() == '.csv':
        with path.open('r', encoding='utf-8-sig', newline='') as stream:
            yield csv.reader(stream)
    elif path.suffix.casefold() == '.xlsx':
        from openpyxl import load_workbook

        # Keep formulas as strings so targets and predictors require actual
        # values. A formula's stored result can predate the user's edits.
        workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
        try:
            sheet = workbook['Training'] if 'Training' in workbook.sheetnames else workbook.worksheets[0]
            yield sheet.iter_rows(values_only=True)
        finally:
            workbook.close()
    else:
        raise ValueError(tr('Choose a .xlsx or .csv training table.'))


def _text(value):
    return '' if value is None else str(value).strip()


def _integer(value):
    if isinstance(value, bool):
        raise ValueError()
    if isinstance(value, str):
        return int(value.strip())
    integer = int(value)
    if integer != value:
        raise ValueError()
    return integer


def read_training_rows(path, area, check_cancel, class_ids=None):
    """Read canonical features and manual class IDs, then group by TIFF or experiment."""
    features = [area, *RF_PREDICTORS[1:]]
    classes = {entry['id']: entry['key'] for entry in OBJECT_CLASS_CATALOG}
    audits, rows = {}, []
    experiments = defaultdict(set)
    measurement_ids = defaultdict(set)
    dataset_ids = defaultdict(set)
    object_ids = set()
    with _table(Path(path)) as table:
        header = [_text(name) for name in next(table, ())]
        names = [name for name in header if name]
        if len(set(names)) != len(names):
            raise ValueError(tr('The training table contains duplicate column names.'))
        missing = [name for name in [*features, 'Large_Image', 'Manual_Class_ID'] if name not in names]
        if missing:
            raise ValueError(tr('Training table requires columns: {columns}.', columns=', '.join(missing)))
        for number, cells in enumerate(table, 2):
            check_cancel()
            row = dict(zip(header, cells))
            target = row.get('Manual_Class_ID')
            if not any(_text(value) for value in cells):
                continue
            try:
                # Unreviewed rows are skipped before numeric validation. The
                # YOLO Class_ID is metadata even if its value resembles a target.
                reviewed = _text(row.get('Reviewed')).casefold()
                if reviewed in ('0', 'false', '') and 'Reviewed' in names:
                    continue
                if reviewed not in ('1', 'true', ''):
                    raise ValueError()
                if not _text(target) and 'Reviewed' not in names:
                    continue
                target = _integer(target)
                manual_class = _text(row.get('Manual_Class'))
                version = _text(row.get('Class_Catalog_Version'))
                source = _text(row.get('Large_Image'))
                if (target not in classes or (manual_class and manual_class != classes[target])
                        or (version and _integer(version) != CLASS_CATALOG_VERSION) or not source):
                    raise ValueError()
                # Ignore excluded rows before checking predictors. They are
                # outside the model's input and may lack its calibrated area.
                if class_ids is not None and target not in class_ids:
                    continue
                values = [float(row[name]) for name in features]
                if values[0] <= 0 or not all(math.isfinite(value) for value in values):
                    raise ValueError()
                tile = _text(row.get('Tile_Name'))
                object_value = row.get('Object_ID')
                obj = _integer(object_value) if _text(object_value) else number
            except (KeyError, ValueError, TypeError, OverflowError):
                raise ValueError(tr('Invalid manual class, source or predictors on training table row {row}.',
                                    row=number)) from None

            # Case-insensitive source aliases prevent treating case variants as
            # independent TIFFs. Different measurement versions can contain the
            # same physical objects and must not inflate this training table.
            source_key = source.casefold()
            audit = audits.setdefault(source_key, dict(dataset_id=source_key, name=source,
                                      status='included', measured=0, reviewed=0))
            audit['measured'] += 1
            audit['reviewed'] += 1
            for key, distinct in [('Experiment_Group', experiments), ('Dataset_ID', dataset_ids),
                                  ('Measurement_Reference', measurement_ids)]:
                value = _text(row.get(key))
                if value:
                    distinct[source_key].add(value.casefold())
            identity = (source_key, tile.casefold(), obj)
            if tile and _text(object_value) and identity in object_ids:
                raise ValueError(tr('Duplicate reviewed object on training table row {row}.', row=number))
            if tile and _text(object_value):
                object_ids.add(identity)
            entry = dict(dataset_id=source_key, tile_name=tile, object_id=obj, values=values, target=target)
            if not tile or not _text(object_value) or not _text(row.get('Measurement_Reference')):
                entry['image_identity_missing'] = True
            rows.append(entry)
    seen_datasets, seen_measurements = set(), set()
    for source_key, audit in audits.items():
        if len(experiments[source_key]) > 1:
            raise ValueError(tr('One TIFF has conflicting experiment groups.'))
        if len(dataset_ids[source_key]) > 1 or len(measurement_ids[source_key]) > 1:
            raise ValueError(tr('Use only one measurement dataset per TIFF in the training table.'))
        if seen_datasets & dataset_ids[source_key] or seen_measurements & measurement_ids[source_key]:
            raise ValueError(tr('A measurement dataset in the training table refers to more than one TIFF.'))
        seen_datasets.update(dataset_ids[source_key])
        seen_measurements.update(measurement_ids[source_key])
        aliases = experiments[source_key]
        audit['group'] = 'group:' + next(iter(aliases)) if aliases else 'file-tiff:' + source_key
        audit['measurement_reference'] = next(iter(measurement_ids[source_key]), '')
    for row in rows:
        row['group'] = audits[row['dataset_id']]['group']
    return features, rows, list(audits.values())
