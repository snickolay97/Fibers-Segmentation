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
from src.desktop.i18n import tr


def add_sources(project, paths):
    from src.image_io import inspect_tiff
    known = {str(Path(s['path']).resolve()).casefold() for s in project.sources}
    added = []
    for path in paths:
        path = str(Path(path).resolve())
        if path.casefold() in known:
            continue
        info = inspect_tiff(path)
        info.update(id=uuid.uuid4().hex, path=path)
        project.sources.append(info)
        added.append(info)
        known.add(path.casefold())
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
    base = Path(dataset['path'])
    return [dict(r, excluded=not (base / r['filename']).is_file())
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


def get_object_labels(dataset):
    """Load manual targets belonging to the selected measurement version."""
    from src.desktop.object_labels import load_object_labels
    return load_object_labels(dataset, current=results_are_current(dataset))


def assign_object_class(project, dataset_id, tile_name, object_id, class_key):
    from src.desktop.object_labels import save_object_class
    dataset = project.get_dataset(dataset_id)
    if not results_are_current(dataset):
        raise ValueError(tr('Пересчитайте признаки: разметка или состав тайлов изменились.'))
    report = save_object_class(dataset, tile_name, object_id, class_key)
    project.add_history('assign_object_class', dataset_id=dataset_id,
                       measurement_reference=report['measurement_reference'],
                       tile_name=tile_name, object_id=int(object_id), class_key=class_key,
                       previous_class=report['previous_class'], assigned=report['assigned'])
    return report


def export_training_csv(dataset, destination, only_labeled=True):
    from src.desktop.object_labels import write_training_csv
    if not results_are_current(dataset):
        raise ValueError(tr('Пересчитайте признаки перед экспортом обучающей таблицы.'))
    return write_training_csv(dataset, destination, only_labeled=only_labeled)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


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
    if not dataset.get('results_current', False) or not dataset.get('results_dir'):
        return False
    try:
        provenance = json.loads((Path(dataset['results_dir']) / 'measurement_run.json').read_text(encoding='utf-8'))
        return (provenance['manifest_signature'] == fingerprint(dataset_manifest(dataset))
                and provenance['annotation_signature'] == content_signature(dataset.get('labels_dir'))
                and provenance['active_tile_ids'] == [r['id'] for r in tile_records(dataset) if not r['excluded']])
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
    from src.partition_geometry import validate_dataset
    _check_cancel(cancelled)
    base = Path(dataset_path).resolve()
    _event(progress, 'validation', tr('Проверка сохранённого набора'))
    manifest = validate_dataset(base, require_v3=True)
    duplicate = next((d for d in project.datasets if Path(d['path']).resolve() == base), None)
    if duplicate:
        project.active_dataset_id = duplicate['id']
        project.save()
        return {'status': 'completed', 'dataset': duplicate, 'reused': True}
    info = dict(id=uuid.uuid4().hex, name=manifest.get('source_name', base.name),
                path=str(base), raw_path=None, source_path=None, status='awaiting_review',
                settings=manifest.get('run_info', {}).get('settings', project.settings),
                labels_dir=None, results_dir=None, last_csv=None, reviewed=False,
                results_current=False, created_at=timestamp(), imported=True)
    _check_cancel(cancelled)
    project.datasets.append(info)
    project.active_dataset_id = info['id']
    project.add_history('connect_dataset', dataset_id=info['id'], path=str(base))
    return {'status': 'completed', 'dataset': info, 'tiles': len(manifest['tiles'])}


def prepare(project, source_ids=None, settings=None, progress=None, cancelled=None):
    from src.app_settings import PipelineSettings, PipelineCancelled
    from src.pipeline_manager import BiomedicalPipelineManager
    from src.partition_geometry import validate_dataset
    from src.desktop.provenance import runtime_provenance
    options = PipelineSettings.from_dict(settings or project.settings).validate()
    project.settings = options.to_dict()
    selected = [s for s in project.sources if not source_ids or s['id'] in source_ids]
    if not selected:
        raise ValueError(tr('Добавьте и выберите исходные TIFF.'))
    overall = dict(status='completed', processed=0, skipped=0, failed=0, datasets=[], errors=[])
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    runtime = runtime_provenance()
    run_base = Path(project.workspace) / 'runs' / run_id
    project.add_history('prepare_start', run_id=run_id, settings=options.to_dict())
    for index, source in enumerate(selected):
        _check_cancel(cancelled)
        signature = source_signature(source['path'])
        key = fingerprint(dict(source=signature, settings=options.to_dict()))
        existing = next((d for d in reversed(project.datasets)
                         if d.get('preparation_key') == key and d.get('status') not in ('error', 'cancelled', 'interrupted')
                         and d.get('path')), None)
        if existing:
            try:
                validate_dataset(existing['path'], require_v3=True)
                overall['skipped'] += 1
                overall['datasets'].append(existing['id'])
                project.active_dataset_id = existing['id']
                _event(progress, 'prepare', tr('Проверенный набор используется повторно'), dataset=source['name'], current=index + 1, total=len(selected))
                continue
            except (ValueError, OSError):
                existing['status'] = 'interrupted'
        source_run = run_base / source['id'][:12]
        dataset = dict(id=uuid.uuid4().hex, name=Path(source['path']).stem,
                       path=str(source_run / 'tiles' / Path(source['path']).stem),
                       raw_path=str(source_run / 'raw' / Path(source['path']).stem) if options.save_raw_tiles else None,
                       source_path=source['path'], source_id=source['id'], status='running',
                       stage='prepare', run_id=run_id, settings=options.to_dict(),
                       preparation_key=key, source_signature=signature, labels_dir=None,
                       results_dir=None, last_csv=None, reviewed=False, results_current=False,
                       runtime=runtime, created_at=timestamp())
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
    version = uuid.uuid4().hex[:12]
    target = Path(project.workspace) / 'annotations' / dataset_id / version
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
    from src.app_settings import PipelineSettings, PipelineCancelled
    from src.block3_feature_extractor import TopologicalFeatureExtractor, inspect_labels as inspect
    from src.partition_geometry import validate_dataset
    dataset = project.get_dataset(dataset_id)
    validate_dataset(dataset['path'], require_v3=True)
    options = PipelineSettings.from_dict(settings or project.settings or dataset.get('settings')).validate()
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
    prior = {k: dataset.get(k) for k in ('status', 'results_dir', 'last_csv', 'results_current')}
    run_id = uuid.uuid4().hex
    out = Path(project.workspace) / 'measurements' / dataset_id / run_id
    dataset.update(status='running', stage='features', results_current=False)
    project.save()
    try:
        extractor = TopologicalFeatureExtractor(image_dir=dataset['path'], labels_dir=labels,
            output_dir=str(out), large_image_name=dataset['name'], settings=options,
            progress=progress, cancelled=cancelled, labels_mode=labels_mode, allow_legacy=False)
        summary = extractor.execute()
        _check_cancel(cancelled)
        provenance = dict(dataset_id=dataset_id, dataset_path=dataset['path'],
            manifest_signature=fingerprint(dataset_manifest(dataset)), settings=options.to_dict(),
            annotation_signature=content_signature(labels), labels_mode=labels_mode,
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


def overview(project, dataset_id, progress=None, cancelled=None):
    from src.overview_reconstructor import HighResOverviewReconstructor
    dataset = project.get_dataset(dataset_id)
    _check_cancel(cancelled)
    result = HighResOverviewReconstructor().reconstruct_dataset(dataset['path'],
        target_dim=(dataset.get('settings') or project.settings).get('overview_size', 6000),
        progress=progress, cancelled=cancelled)
    return dict(status='completed', path=str(result))


def preview(project, source_id=None, source_ids=None, settings=None, progress=None, cancelled=None):
    from src.app_settings import PipelineSettings
    from src.image_io import preview_tiff
    from src.block1_preprocessor import GlobalPreprocessor
    from src.partition_geometry import checked_imwrite
    selected_id = source_id or ((source_ids or [None])[0])
    source = next((s for s in project.sources if s['id'] == selected_id), None)
    if source is None:
        raise ValueError(tr('Выберите TIFF для предпросмотра.'))
    options = PipelineSettings.from_dict(settings or project.settings).validate()
    _event(progress, 'preview', tr('Чтение фрагмента для предпросмотра'))
    image = preview_tiff(source['path'], channel=options.channel, plane=options.plane, max_size=1200, crop=True)
    filtered, mask = GlobalPreprocessor(settings=options, progress=progress, cancelled=cancelled).process(image)
    _check_cancel(cancelled)
    folder = Path(project.workspace) / 'previews' / uuid.uuid4().hex
    folder.mkdir(parents=True)
    for name, array in [('input', image), ('filtered', filtered), ('mask', mask)]:
        checked_imwrite(folder / (name + '.png'), array)
    return dict(status='completed', input_path=str(folder / 'input.png'),
                filtered_path=str(folder / 'filtered.png'), mask_path=str(folder / 'mask.png'),
                approximate=True)


def pick_tile(project, dataset_id, x, y, progress=None, cancelled=None):
    _check_cancel(cancelled)
    ident = hit_test_tile(project.get_dataset(dataset_id), x, y)
    _check_cancel(cancelled)
    return dict(status='completed', tile_id=ident, dataset_id=dataset_id)


def execute_action(project, request, progress=None, cancelled=None):
    action = request['action']
    functions = {'prepare': prepare, 'extract': extract, 'preview': preview,
                 'connect': connect_dataset, 'import_labels': import_labels, 'overview': overview, 'pick_tile': pick_tile}
    if action not in functions:
        raise ValueError(tr('Неизвестная операция: {action}', action=action))
    allowed = {
        'prepare': ('source_ids', 'settings'),
        'extract': ('dataset_id', 'labels_mode', 'settings'),
        'preview': ('source_id', 'source_ids', 'settings'),
        'connect': ('dataset_path',),
        'import_labels': ('dataset_id', 'labels_source'),
        'overview': ('dataset_id',),
        'pick_tile': ('dataset_id', 'x', 'y'),
    }
    args = {k: request[k] for k in allowed[action] if k in request}
    return functions[action](project, progress=progress, cancelled=cancelled, **args)
