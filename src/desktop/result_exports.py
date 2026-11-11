"""Portable copies of current measurements and reviewed training rows."""
import csv
import io
import json
import math
import os
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from src.object_classes import OBJECT_CLASS_CATALOG
from . import service
from .i18n import tr
from .object_labels import RF_PREDICTORS, validate_export_destination


def export_workbook(dataset, destination):
    """Write the full measured table with a fixed allowlist of numeric columns."""
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell

    fields, rows = service.read_results(dataset)
    if not fields:
        raise ValueError(tr('No current measurements to export.'))
    if len(rows) >= 1_048_576:
        raise ValueError(tr('Too many rows for one Excel sheet. Export CSV instead.'))
    target = validate_export_destination(dataset, destination)
    numeric = {*RF_PREDICTORS, 'Area_um2', 'Class_ID', 'Object_ID',
               'Source_Pixels_Per_Output_Pixel'}
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet('Measurements')
    sheet.freeze_panes = 'A2'
    sheet.append(fields)
    for row in rows:
        cells = []
        for field in fields:
            value = row[field]
            if field in numeric and value:
                number = float(value)
                if math.isfinite(number):
                    cells.append(number)
                    continue
            cell = WriteOnlyCell(sheet, value=value)
            cell.data_type = 's'  # Store values beginning with '=' as literal text.
            cells.append(cell)
        sheet.append(cells)
    with tempfile.TemporaryDirectory(prefix='.excel_', dir=target.parent) as directory:
        staged = Path(directory) / 'measurements.xlsx'
        workbook.save(staged)
        os.replace(staged, target)
    return len(rows)


def export_ml_bundle(dataset, destination):
    """Package aligned reviewed rows for training, targets and traceability."""
    target = validate_export_destination(dataset, destination)
    with tempfile.TemporaryDirectory(prefix='.ml_', dir=target.parent) as directory:
        staging = Path(directory)
        training = staging / 'training.csv'
        report = service.export_training_csv(dataset, training)
        if not report['rows']:
            raise ValueError(tr('Assign at least one manual type before exporting an ML bundle.'))
        with training.open(encoding='utf-8', newline='') as source:
            reader = csv.DictReader(source)
            predictors = report['predictors']
            target_column = report['target']
            metadata = [name for name in reader.fieldnames
                        if name not in (*predictors, target_column)]
            with ZipFile(staging / 'dataset.zip', 'w', ZIP_DEFLATED) as archive:
                archive.write(training, 'training.csv')
                buffers = [io.StringIO(newline='') for _ in range(3)]
                writers = [csv.DictWriter(buffer, fieldnames=columns, extrasaction='ignore')
                           for buffer, columns in zip(buffers, (predictors, [target_column], metadata))]
                for writer in writers:
                    writer.writeheader()
                # Write each source row to all three tables in the same order.
                # Readers align the feature, target and metadata rows by position.
                for row in reader:
                    for writer in writers:
                        writer.writerow(row)
                for name, buffer in zip(('X.csv', 'y.csv', 'objects.csv'), buffers):
                    archive.writestr(name, buffer.getvalue())
                manifest = {key: report[key] for key in ('rows', 'predictors', 'target',
                            'class_catalog_version', 'measurement_reference')}
                source = dataset.get('source_path')
                manifest.update(version=1, row_alignment='Same order in all CSV files',
                                classes={item['id']: item['key'] for item in OBJECT_CLASS_CATALOG},
                                source_id=dataset.get('source_id'),
                                source_filename=Path(source).name if source else None,
                                split_guidance='Group by original source image or experiment across bundles.')
                archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        os.replace(staging / 'dataset.zip', target)
    return report['rows']
