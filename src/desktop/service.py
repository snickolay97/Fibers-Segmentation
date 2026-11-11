"""Project operations used by both the desktop UI and isolated workers."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import os
import shutil
import tempfile
import uuid

from src.desktop.project import atomic_json, timestamp
from src.desktop.i18n import register_translations, tr
from src.default_settings import FACTORY_DEFAULTS, STRAIGHT_SHIFT_FIELDS
from .storage_names import readable_name, unused_file, new_version, version_path
from .source_options import source_options

register_translations({
    'Tile edits changed during measurement. Recalculate the features.': 'Правки тайлов изменились во время измерения. Пересчитайте признаки.',
}, hebrew={
    'Tile edits changed during measurement. Recalculate the features.': 'עריכות האריחים השתנו במהלך המדידה. חשבו מחדש את התכונות.',
})


def _copy_file(source, destination, cancelled=None):
    """Copy exact bytes in cancellable chunks, then preserve source metadata."""
    source, destination = Path(source), Path(destination)
    before = source_signature(source)
    with source.open('rb') as reader, destination.open('xb') as writer:
        while True:
            _check_cancel(cancelled)
            chunk = reader.read(4 * 1024 * 1024)
            if not chunk:
                break
            writer.write(chunk)
    if source_signature(source) != before:
        raise ValueError(tr('The source changed during import. Import it again.'))
    shutil.copystat(source, destination)


def _copy_dataset(source, destination, cancelled=None):
    """Copy a self-contained dataset into a new project-owned folder."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or source in destination.parents:
        raise ValueError(tr('The destination must be outside the imported dataset.'))
    for current, directories, files in os.walk(source, followlinks=False):
        _check_cancel(cancelled)
        current = Path(current)
        for entry in [current / name for name in directories + files]:
            # Reject symbolic links and entries that resolve outside the dataset
            # so the managed copy does not depend on external files.
            if entry.is_symlink() or source not in entry.resolve().parents:
                raise ValueError(tr('Linked files and folders cannot be imported as dataset data.'))
        target = destination / current.relative_to(source)
        target.mkdir(parents=True, exist_ok=True)
        for filename in files:
            _check_cancel(cancelled)
            _copy_file(current / filename, target / filename, cancelled=cancelled)


def add_sources(project, paths, progress=None, cancelled=None):
    """Inspect and stage each TIFF, then register only the finished local copy."""
    from src.image_io import inspect_tiff
    known = {str(Path(s[key]).resolve()).casefold()
             for s in project.sources for key in ('path', 'original_path') if s.get(key)}
    added = []
    try:
        for index, path in enumerate(paths):
            _check_cancel(cancelled)
            source = Path(path).resolve()
            if str(source).casefold() in known:
                continue
            info = inspect_tiff(source)
            ident = uuid.uuid4().hex
            parent = Path(project.workspace) / 'sources'
            parent.mkdir(parents=True, exist_ok=True)
            target = unused_file(parent, readable_name(source.name))
            _event(progress, 'sources', tr('Copying source into project: {name}', name=source.name),
                   current=index, total=len(paths))
            with tempfile.TemporaryDirectory(prefix='.import_', dir=parent) as temporary:
                staged = Path(temporary) / 'source'
                staged.mkdir()
                _copy_file(source, staged / source.name, cancelled=cancelled)
                _check_cancel(cancelled)
                os.rename(staged / source.name, target)
            info.update(id=ident, path=str(target), original_path=str(source))
            project.sources.append(info)
            added.append(info)
            known.update((str(source).casefold(), info['path'].casefold()))
    finally:
        # Earlier completed files remain usable if a later import is cancelled
        # or fails. A partially copied source is never added to project state.
        if added:
            project.add_history('add_sources', paths=[s['path'] for s in added])
    return added


def dataset_manifest(dataset):
    from src.partition_geometry import read_manifest
    base = Path(dataset['path'])
    path = base / 'overview' / (dataset['name'] + '_tiles_coords.json')
    if not path.is_file():
        paths = list((base / 'overview').glob('*_tiles_coords.json'))
        if len(paths) != 1:
            raise ValueError(tr('Не найден однозначный manifest нарезки.'))
        path = paths[0]
    return read_manifest(path)


def tile_records(dataset):
    """Combine saved tile geometry with the live inclusion state of model files."""
    base = Path(dataset['path'])
    from src.tile_edits import active_tile_edits, effective_tile_record
    edits = active_tile_edits(base)
    from src.black_tiles import exclusion_state
    state = exclusion_state(base)['tiles']
    return [dict(effective_tile_record(base, r, edits), excluded=not (base / r['filename']).is_file(),
                 exclusion_reason=state.get(str(r['id']),{}).get('kind'))
            for r in dataset_manifest(dataset)['tiles']]


def hit_test_tile(dataset, x, y):
    """Resolve exact ownership, including irregular and overlapping crop rectangles."""
    import cv2
    manifest = dataset_manifest(dataset)
    height, width = manifest['image_shape']
    x, y = int(x), int(y)
    if not (0 <= x < width and 0 <= y < height):
        return None
    for rec in manifest['tiles']:
        if rec['x1'] <= x < rec['x2'] and rec['y1'] <= y < rec['y2']:
            mask = cv2.imread(str(Path(dataset['path']) / rec['valid_mask']), cv2.IMREAD_GRAYSCALE)
            if mask is None:
                raise ValueError(tr('Не удалось прочитать маску принадлежности тайла.'))
            owned = bool(mask[y - rec['y1'], x - rec['x1']])
            del mask
            if owned:
                return rec['id']
    return None


def mark_reviewed(project, dataset_id):
    dataset = project.get_dataset(dataset_id)
    dataset['reviewed'] = True
    dataset['status'] = 'ready' if dataset.get('labels_dir') else 'awaiting_annotations'
    project.add_history('mark_reviewed', dataset_id=dataset_id)


def exclusion(project, dataset_id, specs, excluded=True):
    """Change the active tiles and retire measurements based on the old set."""
    from src.tile_manager import TileManager
    dataset = project.get_dataset(dataset_id)
    base = Path(dataset['path'])
    manager = TileManager(output_dir=str(base.parent),
                          raw_output_dir=str(Path(dataset['raw_path']).parent) if dataset.get('raw_path') else str(base.parent / '.no_raw'))
    count = manager.exclude(base.name, specs) if excluded else manager.restore(base.name, specs)
    if count:
        dataset['last_csv'] = None
        dataset['results_current'] = False
        dataset['status'] = 'ready' if dataset.get('labels_dir') else 'awaiting_annotations'
        project.add_history('exclude' if excluded else 'restore', dataset_id=dataset_id, specs=specs, count=count)
    return {'count': count, 'excluded': excluded}


def exclude_black_tiles(project, dataset_id, progress=None, cancelled=None):
    """Audit only project-owned pixels; retire results when inclusion changes."""
    from src.tile_manager import TileManager
    from src.overview_reconstructor import HighResOverviewReconstructor
    from . import black_tile_text
    dataset = project.get_dataset(dataset_id)
    base = Path(dataset['path']).resolve()
    if Path(project.workspace).resolve() not in base.parents:
        raise ValueError('Import this dataset into the project before changing tiles')
    manager = TileManager(output_dir=base.parent,
                          raw_output_dir=Path(dataset['raw_path']).parent if dataset.get('raw_path') else None)
    report = manager.exclude_black(base.name,progress,cancelled)
    if report['count']:
        dataset.update(results_current=False,last_csv=None)
        project.add_history('exclude_black_tiles',dataset_id=dataset_id,**report)
    # Always refresh this first-audit map so older manual exclusions get labels too.
    HighResOverviewReconstructor().reconstruct_dataset(base,
        target_dim=(dataset.get('settings') or project.settings).get('overview_size',6000),
        progress=progress,cancelled=cancelled)
    return dict(status='completed',**report)


def inspect_labels(project, dataset_id):
    from src.block3_feature_extractor import inspect_labels as inspect
    dataset = project.get_dataset(dataset_id)
    return inspect(dataset['path'], dataset.get('labels_dir') or str(Path(project.workspace) / '.missing_labels'))


def read_results(dataset):
    path = dataset.get('last_csv')
    if not path or not results_are_current(dataset) or not Path(path).is_file():
        return [], []
    with open(path, encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def export_csv(dataset, destination):
    from src.desktop.object_labels import validate_export_destination
    source = dataset.get('last_csv')
    if not source or not results_are_current(dataset) or not Path(source).is_file():
        raise ValueError(tr('У набора нет актуальной таблицы признаков.'))
    target = validate_export_destination(dataset, destination, allow_current_source=True)
    if Path(source).resolve() != target:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.export_', dir=target.parent) as temporary:
            staged = Path(temporary)/'features.csv'
            shutil.copy2(source, staged)
            os.replace(staged, target)
    return str(target)


def get_object_labels(dataset, *, current=None):
    """Load manual targets belonging to the selected measurement version."""
    from src.desktop.object_labels import load_object_labels
    if current is None:
        current = results_are_current(dataset)
    return load_object_labels(dataset, current=current)


def assign_object_class(project, dataset_id, tile_name, object_id, class_key, *, compact=False):
    from src.desktop.object_labels import save_object_class
    dataset = project.get_dataset(dataset_id)
    if not results_are_current(dataset):
        raise ValueError(tr('Пересчитайте признаки: разметка или состав тайлов изменились.'))
    report = save_object_class(dataset, tile_name, object_id, class_key, compact=compact)
    # The durable event is committed with the target. JSON is only a later
    # checkpoint, so a click never rewrites the growing project history.
    if report.get('audit_event'):
        project.history.append(report['audit_event'])
    return report


def export_training_csv(dataset, destination, only_labeled=True):
    from src.desktop.object_labels import write_training_csv
    if not results_are_current(dataset):
        raise ValueError(tr('Пересчитайте признаки перед экспортом обучающей таблицы.'))
    return write_training_csv(dataset, destination, only_labeled=only_labeled)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def _settings_fingerprints(source, settings, **extra):
    """Reuse older runs only where omitted tiling fields have equivalent defaults."""
    payload = dict(source=source, settings=settings, **extra)
    key = fingerprint(payload)
    compatible = {key}
    if settings['search_window_end'] is None:
        payload['settings'] = {field: value for field, value in settings.items()
                               if field != 'search_window_end'}
        compatible.add(fingerprint(payload))
    if settings['search_window_end'] is None and all(
            settings[field] == FACTORY_DEFAULTS[field] for field in STRAIGHT_SHIFT_FIELDS):
        payload['settings'] = {field: value for field, value in settings.items()
                               if field not in ('search_window_end', *STRAIGHT_SHIFT_FIELDS)}
        compatible.add(fingerprint(payload))
    return key, compatible


def source_signature(path):
    path = Path(path).resolve()
    stat = path.stat()
    return dict(path=str(path), size=stat.st_size, mtime_ns=stat.st_mtime_ns)


def content_signature(folder):
    """Hash annotation text to distinguish empty, changed and absent annotations."""
    digest = hashlib.sha256()
    if folder and Path(folder).is_dir():
        for path in sorted(Path(folder).glob('*.txt')):
            digest.update(path.name.encode('utf-8'))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def results_are_current(dataset):
    """Match a measurement against its original geometry, labels and tile set."""
    if not dataset.get('results_current', False) or not dataset.get('results_dir'):
        return False
    try:
        from src.tile_edits import tile_edit_signature
        provenance = json.loads((Path(dataset['results_dir']) / 'measurement_run.json').read_text(encoding='utf-8'))
        return (provenance['manifest_signature'] == fingerprint(dataset_manifest(dataset))
                and provenance['annotation_signature'] == content_signature(dataset.get('labels_dir'))
                and provenance['active_tile_ids'] == [r['id'] for r in tile_records(dataset) if not r['excluded']]
                and provenance.get('tile_edit_signature', {}) == tile_edit_signature(dataset['path']))
    except (OSError, ValueError, KeyError):
        return False


def _check_cancel(cancelled):
    from src.app_settings import PipelineCancelled
    if cancelled and cancelled():
        raise PipelineCancelled(tr('Обработка остановлена пользователем.'))


def _event(progress, stage, message, **details):
    if progress:
        progress(dict(stage=stage, message=message, **details))


def connect_dataset(project, dataset_path, progress=None, cancelled=None):
    """Validate and import a prepared dataset before enabling local review."""
    from src.partition_geometry import validate_dataset
    _check_cancel(cancelled)
    base = Path(dataset_path).resolve()
    _event(progress, 'validation', tr('Проверка сохранённого набора'))
    manifest = validate_dataset(base, require_v3=True)
    from src.tile_edits import tile_edit_signature
    imported_edits = tile_edit_signature(base)
    duplicate = next((d for d in project.datasets if Path(d['path']).resolve() == base
                      or (d.get('imported_from') == str(base)
                          and d.get('imported_edit_signature', {}) == imported_edits)), None)
    if duplicate:
        project.active_dataset_id = duplicate['id']
        project.save()
        return {'status': 'completed', 'dataset': duplicate, 'reused': True}
    ident = uuid.uuid4().hex
    parent = Path(project.workspace) / 'datasets'
    parent.mkdir(parents=True, exist_ok=True)
    _event(progress, 'validation', tr('Copying prepared tiles into project'))
    with tempfile.TemporaryDirectory(prefix='.import_', dir=parent) as temporary:
        staged = Path(temporary) / base.name
        _copy_dataset(base, staged, cancelled=cancelled)
        copied_manifest = validate_dataset(staged, require_v3=True)
        if (copied_manifest != manifest or tile_edit_signature(staged) != imported_edits
                or tile_edit_signature(base) != imported_edits):
            raise ValueError(tr('The dataset changed during import. Import it again.'))
        _check_cancel(cancelled)
        target = version_path(parent, 'Imported_' + readable_name(base.name))
        from src.tile_manager import TileManager
        black_report = TileManager(output_dir=staged.parent).exclude_black(staged.name,progress,cancelled)
        if black_report['count']:
            from src.overview_reconstructor import HighResOverviewReconstructor
            HighResOverviewReconstructor().reconstruct_dataset(staged,
                target_dim=project.settings.get('overview_size',6000),progress=progress,cancelled=cancelled)
        os.rename(staged, target)
    info = dict(id=ident, name=manifest.get('source_name', base.name),
                path=str(target), raw_path=None, source_path=None, status='awaiting_review',
                settings=manifest.get('run_info', {}).get('settings', project.settings),
                labels_dir=None, results_dir=None, last_csv=None, reviewed=False,
                results_current=False, created_at=timestamp(), imported=True, imported_from=str(base),
                imported_edit_signature=imported_edits)
    project.datasets.append(info)
    project.active_dataset_id = info['id']
    project.add_history('connect_dataset', dataset_id=info['id'], path=str(base))
    return {'status': 'completed', 'dataset': info, 'tiles': len(manifest['tiles'])}


def prepare(project, source_ids=None, settings=None, progress=None, cancelled=None):
    """Prepare a batch with per-source calibration and independently saved runs."""
    from src.app_settings import PipelineSettings, PipelineCancelled
    from src.pipeline_manager import BiomedicalPipelineManager
    from src.partition_geometry import validate_dataset
    from src.desktop.provenance import runtime_provenance
    base_options = PipelineSettings.from_dict(settings or project.settings).validate()
    project.settings = base_options.to_dict()
    selected = [s for s in project.sources if not source_ids or s['id'] in source_ids]
    if not selected:
        raise ValueError(tr('Добавьте и выберите исходные TIFF.'))
    overall = dict(status='completed', processed=0, skipped=0, failed=0, datasets=[], errors=[])
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    runtime = runtime_provenance()
    run_base = None
    used_names = set()
    project.add_history('prepare_start', run_id=run_id, settings=base_options.to_dict())
    for index, source in enumerate(selected):
        _check_cancel(cancelled)
        options, calibration = source_options(project, base_options.to_dict(), source=source)
        signature = source_signature(source['path'])
        key, compatible_keys = _settings_fingerprints(signature, options.to_dict())
        existing = next((d for d in reversed(project.datasets)
                         if d.get('preparation_key') in compatible_keys and d.get('status') not in ('error', 'cancelled', 'interrupted')
                         and d.get('path')), None)
        if existing:
            # A matching fingerprint is only a candidate. Check the stored
            # artifacts before treating that dataset as ready for review.
            try:
                validate_dataset(existing['path'], require_v3=True)
                overall['skipped'] += 1
                overall['datasets'].append(existing['id'])
                project.active_dataset_id = existing['id']
                _event(progress, 'prepare', tr('Проверенный набор используется повторно'), dataset=source['name'], current=index + 1, total=len(selected))
                continue
            except (ValueError, OSError):
                existing['status'] = 'interrupted'
        if run_base is None:
            run_base = new_version(Path(project.workspace) / 'runs', 'Preparation')
        name = Path(source['path']).stem
        source_run = run_base if name.casefold() not in used_names else new_version(run_base, readable_name(name))
        used_names.add(name.casefold())
        dataset = dict(id=uuid.uuid4().hex, name=Path(source['path']).stem,
                       path=str(source_run / 'tiles' / Path(source['path']).stem),
                       raw_path=str(source_run / 'raw' / Path(source['path']).stem) if options.save_raw_tiles else None,
                       source_path=source['path'], source_id=source['id'], status='running',
                       stage='prepare', run_id=run_id, settings=options.to_dict(),
                       preparation_key=key, source_signature=signature, labels_dir=None,
                       results_dir=None, last_csv=None, reviewed=False, results_current=False,
                       runtime=runtime, created_at=timestamp())
        dataset['calibration'] = calibration
        project.datasets.append(dataset)
        project.active_dataset_id = dataset['id']
        project.save()
        _event(progress, 'prepare', tr('Подготовка {name}', name=source['name']), dataset=source['name'], current=index, total=len(selected))
        try:
            manager = BiomedicalPipelineManager(input_dir=str(Path(source['path']).parent),
                input_files=[source['path']], output_dir=str(source_run / 'tiles'),
                raw_output_dir=str(source_run / 'raw'), labels_dir=str(source_run / 'labels'),
                features_dir=str(source_run / 'features'), settings=options,
                progress=progress, cancelled=cancelled)
            result = manager.run('filter_and_slice')
            if result.get('cancelled'):
                raise PipelineCancelled(tr('Обработка остановлена.'))
            if result.get('failed') or not (result.get('processed') or result.get('skipped')):
                raise ValueError(_summary_error(result))
            validate_dataset(dataset['path'], require_v3=True)
            exclude_black_tiles(project,dataset['id'],progress,cancelled)
            dataset['status'] = 'awaiting_review'
            dataset['stage'] = 'tiles'
            dataset['completed_at'] = timestamp()
            overall['processed'] += 1
            overall['datasets'].append(dataset['id'])
        except PipelineCancelled:
            dataset['status'] = 'cancelled'
            project.add_history('prepare_cancelled', dataset_id=dataset['id'])
            raise
        except Exception as error:
            dataset['status'] = 'error'
            dataset['error'] = str(error)
            overall['failed'] += 1
            overall['errors'].append(dict(dataset=dataset['name'], error=str(error)))
            _event(progress, 'error', str(error), dataset=dataset['name'])
        finally:
            project.save()
        _event(progress, 'prepare', tr('Набор обработан'), dataset=source['name'], current=index + 1, total=len(selected))
    overall['status'] = 'failed' if overall['failed'] else 'completed'
    project.add_history('prepare_finished', summary=overall)
    return overall


def _summary_error(summary):
    errors = summary.get('errors') or []
    if errors:
        first = errors[0]
        return str(first.get('error', first) if isinstance(first, dict) else first)
    for item in summary.get('datasets', []):
        if isinstance(item, dict) and item.get('error'):
            return item['error']
    return tr('Подготовка не завершилась. Подробности в журнале выполнения.')


def import_labels(project, dataset_id, labels_source, progress=None, cancelled=None):
    """Copy matching YOLO files into a fresh annotation version."""
    from src.block3_feature_extractor import inspect_labels as inspect, TopologicalFeatureExtractor
    dataset = project.get_dataset(dataset_id)
    source = Path(labels_source).resolve()
    if not source.is_dir():
        raise ValueError(tr('Выберите папку с текстовыми файлами разметки.'))
    _event(progress, 'labels', tr('Проверка полигонов разметки'))
    report = inspect(dataset['path'], str(source))
    if report['errors']:
        raise ValueError(tr('Разметка содержит ошибки:\n') + '\n'.join(str(e) for e in report['errors'][:20]))
    known_names = {Path(r['filename']).stem + '.txt' for r in tile_records(dataset)}
    # Preserve annotations for excluded tiles so restoring a tile restores its
    # annotation too; validate these matched files before publishing the import.
    for file in source.glob('*.txt'):
        if file.name in known_names:
            TopologicalFeatureExtractor._parse_yolo(str(file), 1, 1)
    _check_cancel(cancelled)
    target = version_path(Path(project.workspace) / 'annotations' / readable_name(dataset['name']), 'Labels')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.import_', dir=target.parent) as temporary:
        staged = Path(temporary) / 'labels'
        staged.mkdir()
        for file in source.glob('*.txt'):
            _check_cancel(cancelled)
            if file.name in known_names:
                shutil.copy2(file, staged / file.name)
        _check_cancel(cancelled)
        signature = content_signature(staged)
        os.rename(staged, target)
    dataset.update(labels_dir=str(target), labels_signature=signature, results_current=False, last_csv=None,
                   status='ready' if dataset.get('reviewed') else 'awaiting_review')
    project.add_history('import_labels', dataset_id=dataset_id, source=str(source), report=report, signature=signature)
    return dict(status='completed', report=report, labels_dir=str(target))


def extract(project, dataset_id, labels_mode='annotations_only', settings=None, progress=None, cancelled=None):
    """Measure active native tiles and publish a new results version with provenance."""
    from src.app_settings import PipelineSettings, PipelineCancelled
    from src.block3_feature_extractor import TopologicalFeatureExtractor, inspect_labels as inspect
    from src.partition_geometry import validate_dataset
    dataset = project.get_dataset(dataset_id)
    from src.tile_edits import tile_edit_signature
    edit_signature = tile_edit_signature(dataset['path'])
    validate_dataset(dataset['path'], require_v3=True)
    options, calibration = source_options(project, settings or project.settings or dataset.get('settings'), dataset=dataset)
    if labels_mode not in ('auto', 'annotations_only', 'require_annotations'):
        raise ValueError(tr('Неизвестный режим получения объектов.'))
    labels = dataset.get('labels_dir') or str(Path(project.workspace) / '.missing_labels')
    report = inspect(dataset['path'], labels)
    if report['errors']:
        raise ValueError(tr('Исправьте ошибки разметки перед расчётом.'))
    if labels_mode == 'require_annotations' and report['missing']:
        raise ValueError(tr('Для части активных тайлов отсутствуют файлы разметки.'))
    if labels_mode == 'annotations_only' and not (report['annotated'] or report['empty']):
        raise ValueError(tr('Сначала импортируйте разметку или выберите автоматическое выделение объектов.'))
    _check_cancel(cancelled)
    # Keep the previous result references until the new extraction and its
    # provenance finish. Error and cancellation paths restore those references.
    prior = {k: dataset.get(k) for k in ('status', 'results_dir', 'last_csv', 'results_current')}
    out = version_path(Path(project.workspace) / 'measurements' / readable_name(dataset['name']), 'Measurement')
    dataset.update(status='running', stage='features', results_current=False)
    project.save()
    try:
        extractor = TopologicalFeatureExtractor(image_dir=dataset['path'], labels_dir=labels,
            output_dir=str(out), large_image_name=dataset['name'], settings=options,
            progress=progress, cancelled=cancelled, labels_mode=labels_mode, allow_legacy=False)
        summary = extractor.execute()
        _check_cancel(cancelled)
        if tile_edit_signature(dataset['path']) != edit_signature:
            raise ValueError(tr('Tile edits changed during measurement. Recalculate the features.'))
        provenance = dict(dataset_id=dataset_id, dataset_path=dataset['path'],
            calibration=calibration,
            manifest_signature=fingerprint(dataset_manifest(dataset)), settings=options.to_dict(),
            annotation_signature=content_signature(labels), labels_mode=labels_mode,
            tile_edit_signature=edit_signature,
            active_tile_ids=[r['id'] for r in tile_records(dataset) if not r['excluded']],
            time=timestamp(), summary=summary)
        from src.desktop.provenance import runtime_provenance
        provenance['runtime'] = runtime_provenance()
        atomic_json(out / 'measurement_run.json', provenance)
        dataset.update(status='completed', results_dir=str(out), last_csv=summary['csv_path'],
                       results_current=True, labels_mode=labels_mode, objects=summary['objects'],
                       measured_at=timestamp(), measurement_signature=fingerprint(provenance))
        project.add_history('extract_finished', dataset_id=dataset_id, summary=summary)
        return summary
    except PipelineCancelled:
        dataset.update(prior)
        dataset['status'] = 'cancelled'
        project.add_history('extract_cancelled', dataset_id=dataset_id)
        raise
    except Exception as error:
        dataset.update(prior)
        dataset['status'] = 'error'
        dataset['error'] = str(error)
        project.add_history('extract_failed', dataset_id=dataset_id, error=str(error))
        raise


def use_saved_tile_edit(project, dataset_id, tile_id, metadata_file=None, restore=False,
                        progress=None, cancelled=None):
    from .tile_edit import TileEditContext, activate_tile_version, import_saved_tile_edit
    dataset = project.get_dataset(dataset_id)
    record = next(r for r in tile_records(dataset) if r['id'] == tile_id)
    context = TileEditContext(project.workspace, dataset_id, dataset['path'], record, 'native',
                              expected_revision=record.get('edit_reference'))
    _check_cancel(cancelled)
    if restore:
        activate_tile_version(context, None)
        path = None
    else:
        path = import_saved_tile_edit(context, metadata_file)
    dataset['results_current'] = False
    project.add_history('tile_edit_restored' if restore else 'tile_edit_imported',
                        dataset_id=dataset_id, tile_id=tile_id, path=str(path) if path else None)
    return dict(status='completed', tile_id=tile_id, path=str(path) if path else None)


def overview(project, dataset_id, full_resolution=False, progress=None, cancelled=None):
    from src.overview_reconstructor import HighResOverviewReconstructor
    dataset = project.get_dataset(dataset_id)
    _check_cancel(cancelled)
    target_dim = (max(dataset_manifest(dataset)['image_shape']) if full_resolution else
                  (dataset.get('settings') or project.settings).get('overview_size', 6000))
    result = HighResOverviewReconstructor().reconstruct_dataset(dataset['path'],
        target_dim=target_dim,
        progress=progress, cancelled=cancelled)
    return dict(status='completed', path=str(result), full_resolution=bool(full_resolution))


def preview(project, source_id=None, source_ids=None, settings=None, progress=None, cancelled=None,
            native_resolution=False):
    """Filter the whole selected plane and publish three display-size previews."""
    from src.image_io import inspect_tiff, load_tiff_channel
    from src.block1_preprocessor import GlobalPreprocessor
    from src.partition_geometry import checked_imwrite
    import cv2
    import tifffile
    _check_cancel(cancelled)
    selected_id = source_id or ((source_ids or [None])[0])
    source = next((s for s in project.sources if s['id'] == selected_id), None)
    if source is None:
        raise ValueError(tr('Выберите TIFF для предпросмотра.'))
    options, calibration = source_options(project, settings or project.settings, source=source)
    signature = source_signature(source['path'])
    key, compatible_keys = _settings_fingerprints(signature, options.to_dict(), preview_version=2)
    cached = source.get('last_preview', {})
    required = ['input_path', 'filtered_path', 'mask_path']
    if native_resolution:
        required += ['native_filtered_path', 'native_mask_path']
    if cached.get('key') in compatible_keys and all(Path(cached.get(k, '')).is_file() for k in required):
        return dict(cached, reused=True)
    _event(progress, 'preview', tr('Reading and filtering the whole TIFF at source resolution'))
    _raw, image = load_tiff_channel(source['path'], channel=options.channel, plane=options.plane)
    filtered, mask = GlobalPreprocessor(settings=options, progress=progress, cancelled=cancelled).process(image)
    _check_cancel(cancelled)
    if source_signature(source['path']) != signature:
        raise ValueError(tr('The source changed during import. Import it again.'))
    parent = Path(project.workspace) / 'previews' / readable_name(Path(source['path']).stem)
    parent.mkdir(parents=True, exist_ok=True)
    folder = version_path(parent, 'Preview')
    height, width = image.shape
    # Resize only after filtering so the displayed result reflects the same
    # image domain used by preparation. Preserve binary mask values on resize.
    factor = min(1, 2400 / max(height, width))
    size = (max(1, round(width*factor)), max(1, round(height*factor)))
    with tempfile.TemporaryDirectory(prefix='.preview_', dir=parent) as temporary:
        staged = Path(temporary)
        for name, array in [('before_filters', image), ('after_filters', filtered), ('protective_mask', mask)]:
            _check_cancel(cancelled)
            display = cv2.resize(array, size, interpolation=cv2.INTER_AREA if name != 'protective_mask' else cv2.INTER_NEAREST)
            checked_imwrite(staged / (name + '.png'), display)
        report = dict(status='completed', key=key, source_id=source['id'], source_name=source['name'],
                      source_shape=[height,width], display_shape=[size[1],size[0]],
                      input_path=str(folder/'before_filters.png'), filtered_path=str(folder/'after_filters.png'),
                      mask_path=str(folder/'protective_mask.png'), approximate=False,
                      settings=options.to_dict(), calibration=calibration)
        if native_resolution:
            # Keep native products mappable so opening a region does not decode
            # the entire processed image again.
            for key, name, array in (('native_filtered_path', 'filtered_native.tif', filtered),
                                     ('native_mask_path', 'mask_native.tif', mask)):
                _check_cancel(cancelled)
                tifffile.imwrite(staged / name, array, photometric='minisblack', metadata={'axes': 'YX'})
                report[key] = str(folder / name)
        atomic_json(staged / 'preview.json', report)
        _check_cancel(cancelled)
        os.rename(staged, folder)
    source.update(calibration=inspect_tiff(source['path'])['calibration'], last_preview=report)
    project.add_history('preview_complete', source_id=source['id'], folder=str(folder))
    return report


def pick_tile(project, dataset_id, x, y, progress=None, cancelled=None):
    _check_cancel(cancelled)
    ident = hit_test_tile(project.get_dataset(dataset_id), x, y)
    _check_cancel(cancelled)
    return dict(status='completed', tile_id=ident, dataset_id=dataset_id)


def execute_action(project, request, progress=None, cancelled=None):
    """Dispatch the worker protocol with an explicit argument list per action."""
    action = request['action']
    if action == 'model_evaluation':
        from .model_evaluation_data import run_evaluation
        fields = ('dataset_ids', 'groups', 'area', 'seed', 'folds', 'preview', 'planned_signature',
                  'training_file', 'class_ids', 'split_mode', 'forest_tree_count')
        return run_evaluation(project, progress=progress, cancelled=cancelled,
                              **{key: request[key] for key in fields if key in request})
    if action == 'object_prediction':
        from .object_prediction import predict_objects
        return predict_objects(project, request['evaluation_path'], request['model_key'], request['dataset_id'],
                               request.get('tile_names'), progress=progress, cancelled=cancelled)
    if action == 'train_pixel_segmentation':
        from .pixel_segmentation import train_pixel_segmentation
        fields = ('dataset_ids', 'class_ids', 'forest_tree_count', 'seed')
        return train_pixel_segmentation(project, progress=progress, cancelled=cancelled,
                                        **{key: request[key] for key in fields if key in request})
    if action == 'apply_pixel_segmentation':
        from .pixel_segmentation import apply_pixel_segmentation
        return apply_pixel_segmentation(project, request['dataset_id'], request['tile_id'], request['model_path'],
                                        progress=progress, cancelled=cancelled)
    functions = {'prepare': prepare, 'extract': extract, 'preview': preview,
                 'add_sources': lambda project, paths, progress=None, cancelled=None: dict(
                     status='completed', added=len(add_sources(project, paths, progress=progress, cancelled=cancelled))),
                 'connect': connect_dataset, 'import_labels': import_labels, 'overview': overview, 'pick_tile': pick_tile,
                 'tile_edit': use_saved_tile_edit, 'exclude_black': exclude_black_tiles}
    if action in ('merge_objects', 'undo_object_merge'):
        from .object_merging import merge_objects, undo_merge
        functions.update(merge_objects=merge_objects, undo_object_merge=undo_merge)
    if action in ('correct_objects', 'delete_objects'):
        from .object_corrections import correct_objects, delete_objects
        functions.update(correct_objects=correct_objects, delete_objects=delete_objects)
    if action not in functions:
        raise ValueError(tr('Неизвестная операция: {action}', action=action))
    allowed = {
        'prepare': ('source_ids', 'settings'),
        'add_sources': ('paths',),
        'extract': ('dataset_id', 'labels_mode', 'settings'),
        'preview': ('source_id', 'source_ids', 'settings', 'native_resolution'),
        'connect': ('dataset_path',),
        'import_labels': ('dataset_id', 'labels_source'),
        'overview': ('dataset_id', 'full_resolution'),
        'pick_tile': ('dataset_id', 'x', 'y'),
        'tile_edit': ('dataset_id', 'tile_id', 'metadata_file', 'restore'),
        'exclude_black': ('dataset_id',),
        'merge_objects': ('dataset_id', 'tile_name', 'object_ids', 'expected_signature'),
        'undo_object_merge': ('dataset_id', 'expected_signature'),
        'correct_objects': ('dataset_id', 'tile_name', 'object_ids', 'expected_signature', 'operations', 'keep_separate'),
        'delete_objects': ('dataset_id', 'tile_name', 'object_ids', 'expected_signature'),
    }
    args = {k: request[k] for k in allowed[action] if k in request}
    return functions[action](project, progress=progress, cancelled=cancelled, **args)
