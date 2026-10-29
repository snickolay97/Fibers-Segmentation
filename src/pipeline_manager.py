"""Per-run orchestration with validated outputs and cooperative cancellation."""
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone

from src import config
from src.app_settings import PipelineSettings, PipelineCancelled
from src.image_io import inspect_tiff, load_tiff_channel
from src.block1_preprocessor import GlobalPreprocessor
from src.block2_slicer import SmartSlicer
from src.block3_feature_extractor import TopologicalFeatureExtractor
from src.tile_manager import TileManager
from src.partition_geometry import validate_dataset


class BiomedicalPipelineManager:
    def __init__(self, input_dir=config.INPUT_DIR, output_dir=config.OUTPUT_DIR,
                 raw_output_dir=config.RAW_OUTPUT_DIR, labels_dir=config.LABELS_DIR,
                 features_dir=config.FEATURES_DIR, settings=None, progress=None,
                 cancelled=None, input_files=None):
        self.input_dir = str(Path(input_dir).resolve())
        self.output_dir = str(Path(output_dir).resolve())
        self.raw_output_dir = str(Path(raw_output_dir).resolve())
        self.labels_dir = str(Path(labels_dir).resolve())
        self.features_dir = str(Path(features_dir).resolve())
        self.settings = (PipelineSettings.from_dict(settings.to_dict()) if isinstance(settings, PipelineSettings)
                         else PipelineSettings.from_dict(settings)).validate()
        self.progress, self.cancelled = progress, cancelled
        self.input_files = list(input_files) if input_files is not None else None
        self.preprocessor = GlobalPreprocessor(self.settings, progress=self._event,
                                               cancelled=self.cancelled)
        self.slicer = SmartSlicer(settings=self.settings, progress=self._event,
                                  cancelled=self.cancelled,
                                  animation_dir=str(Path(self.output_dir).parent/'animations'))
        self.tile_manager = TileManager(output_dir=self.output_dir,
                                        raw_output_dir=self.raw_output_dir)
        self._current_dataset = None

    @staticmethod
    def _summary():
        return dict(processed=0, skipped=0, failed=0, cancelled=False, datasets=[])

    def _event(self, event):
        if self.progress:
            payload = dict(event)
            if self._current_dataset is not None:
                payload.setdefault('dataset', self._current_dataset)
            self.progress(payload)

    def _checkpoint(self):
        if self.cancelled and self.cancelled():
            raise PipelineCancelled('Operation cancelled')

    def run(self, mode='filter_and_slice', **kwargs):
        summary = self._summary()
        try:
            self._checkpoint()
            if mode in ('filter_and_slice', 'end_to_end'):
                summary = self._execute_filter_and_slice()
                if mode == 'end_to_end' and not summary['cancelled']:
                    records = [record for record in summary['datasets']
                               if record['status'] in ('processed', 'skipped')]
                    self._execute_extract_features(records=records, summary=summary,
                                                   labels_mode=kwargs.get('labels_mode', 'auto'),
                                                   allow_legacy=False)
            elif mode == 'extract_features':
                summary = self._execute_extract_features(
                    labels_mode=kwargs.get('labels_mode', 'auto'),
                    allow_legacy=kwargs.get('allow_legacy', False),
                    dataset_names=kwargs.get('dataset_names') or
                    ([kwargs['dataset_name']] if kwargs.get('dataset_name') else None))
            elif mode == 'manage_tiles':
                dataset = kwargs.get('dataset_name', 'FL01_G3_RGB_Red')
                self._current_dataset = dataset
                self._event(dict(stage='exclude', status='running', message='Excluding selected tiles'))
                moved = self.tile_manager.exclude(dataset, kwargs.get('exclude_specs', []))
                status = 'processed' if moved else 'skipped'
                summary[status] += 1
                summary['datasets'].append(dict(name=dataset, status=status, tiles=moved,
                                                path=str(Path(self.output_dir)/dataset)))
            else:
                raise ValueError('Unknown pipeline mode: ' + str(mode))
        except PipelineCancelled:
            summary['cancelled'] = True
        except Exception as error:
            summary['failed'] += 1
            summary['datasets'].append(dict(name=self._current_dataset or '',
                                            path=self.output_dir, status='failed', error=str(error)))
        finally:
            self._current_dataset = None
        self._event(dict(stage='pipeline', status='cancelled' if summary['cancelled'] else
                         ('failed' if summary['failed'] else 'completed'),
                         message='Pipeline finished', summary=summary))
        return summary

    @staticmethod
    def _has_output_files(folder):
        return os.path.isdir(folder) and any(files for _, _, files in os.walk(folder))

    @staticmethod
    def _source_signature(path):
        source = Path(path).resolve()
        stat = source.stat()
        return dict(path=str(source), size_bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)

    def _run_info(self, path):
        return dict(settings=self.settings.to_dict(), source=self._source_signature(path),
                    source_image=inspect_tiff(path),
                    created_at=datetime.now(timezone.utc).isoformat())

    def _validate_existing(self, folder, path):
        manifest = validate_dataset(folder, require_v3=True, check_pixels=False)
        previous = manifest.get('run_info')
        if previous:
            if previous.get('settings') != self.settings.to_dict():
                raise ValueError('Existing dataset uses different settings. Choose a new output folder.')
            if previous.get('source') != self._source_signature(path):
                raise ValueError('Existing dataset comes from a different or modified source. Choose a new output folder.')
        else:
            self._event(dict(stage='validate', status='warning',
                             message='Existing tiles validated; original settings/source signature are unavailable'))
        return manifest

    @staticmethod
    def _publish(stage, destination, root):
        stage, destination, root = Path(stage).resolve(), Path(destination).resolve(), Path(root).resolve()
        if root not in stage.parents or destination.parent != root:
            raise ValueError('Dataset publication must stay inside the selected output directory')
        if destination.exists():
            raise FileExistsError('Existing outputs will not be overwritten: ' + str(destination))
        os.rename(stage, destination)

    def _execute_filter_and_slice(self):
        summary = self._summary()
        if self.input_files is not None:
            sources = [Path(path).resolve() for path in self.input_files]
        else:
            source_root = Path(self.input_dir)
            if not source_root.is_dir():
                self._event(dict(stage='load', status='warning', message='Input directory does not exist'))
                return summary
            sources = sorted(path for path in source_root.iterdir()
                             if path.is_file() and path.suffix.lower() in ('.tif', '.tiff'))
        if not sources:
            self._event(dict(stage='load', status='warning', message='No TIFF files selected'))
            return summary
        out_root, raw_root = Path(self.output_dir), Path(self.raw_output_dir)
        out_root.mkdir(parents=True, exist_ok=True)
        if self.settings.save_raw_tiles:
            raw_root.mkdir(parents=True, exist_ok=True)
        for index, source in enumerate(sources):
            name = source.stem
            final = out_root/name
            raw_final = raw_root/name if self.settings.save_raw_tiles else None
            record = dict(name=name, source=str(source), path=str(final), status='pending')
            summary['datasets'].append(record)
            self._current_dataset = name
            self._event(dict(stage='dataset', status='running', message='Processing ' + name,
                             current=index, total=len(sources)))
            try:
                self._checkpoint()
                if final.exists():
                    manifest = self._validate_existing(final, source)
                    if raw_final is not None:
                        raw_manifest = self._validate_existing(raw_final, source)
                        if raw_manifest['tiles'] != manifest['tiles']:
                            raise ValueError('Filtered and raw outputs have different tile manifests')
                    record.update(status='skipped', tiles=len(manifest['tiles']))
                    summary['skipped'] += 1
                    self._event(dict(stage='validate', status='completed', message='Complete existing tiles reused'))
                    continue
                if raw_final is not None and raw_final.exists():
                    raise FileExistsError('Raw output already exists without matching filtered output. Choose new output folders.')
                self._event(dict(stage='load', status='running', message='Loading selected channel and plane'))
                run_info = self._run_info(source)
                native_raw, processing = load_tiff_channel(source, self.settings.channel, self.settings.plane)
                self._checkpoint()
                filtered, protective = self.preprocessor.process(processing)
                self._checkpoint()
                # Staging directories belong to this run and are cleaned by
                # their contexts. Only complete datasets become visible.
                with tempfile.TemporaryDirectory(prefix='.staging-', dir=out_root) as stage_dir:
                    stage = Path(stage_dir)/name
                    if raw_final is not None:
                        with tempfile.TemporaryDirectory(prefix='.staging-', dir=raw_root) as raw_stage_dir:
                            raw_stage = Path(raw_stage_dir)/name
                            manifest = self.slicer.slice(filtered, native_raw, protective, name, stage,
                                                         raw_stage, run_info=run_info)
                            validate_dataset(stage, manifest, require_v3=True)
                            validate_dataset(raw_stage, require_v3=True)
                            self._checkpoint()
                            if self._source_signature(source) != run_info['source']:
                                raise ValueError('Source TIFF changed during processing; results were not published')
                            self._publish(raw_stage, raw_final, raw_root)
                            try:
                                self._publish(stage, final, out_root)
                            except Exception:
                                # Roll back only this run's just-published raw
                                # directory into its owned staging location.
                                if raw_final.parent.resolve() != raw_root.resolve() or raw_root.resolve() not in raw_stage.resolve().parents:
                                    raise ValueError('Unsafe publication rollback path')
                                os.rename(raw_final, raw_stage)
                                raise
                    else:
                        manifest = self.slicer.slice(filtered, native_raw, protective, name, stage,
                                                     run_info=run_info)
                        validate_dataset(stage, manifest, require_v3=True)
                        self._checkpoint()
                        if self._source_signature(source) != run_info['source']:
                            raise ValueError('Source TIFF changed during processing; results were not published')
                        self._publish(stage, final, out_root)
                record.update(status='processed', tiles=len(manifest['tiles']))
                summary['processed'] += 1
                self._event(dict(stage='dataset', status='completed', message='Complete dataset published',
                                 current=index+1, total=len(sources)))
            except PipelineCancelled:
                record.update(status='cancelled')
                summary['cancelled'] = True
                self._event(dict(stage='dataset', status='cancelled', message='Cancelled; incomplete tiles were not published'))
                break
            except Exception as error:
                record.update(status='failed', error=str(error))
                summary['failed'] += 1
                self._event(dict(stage='dataset', status='failed', message=str(error)))
        return summary

    def _execute_extract_features(self, records=None, summary=None, labels_mode='auto',
                                  allow_legacy=False, dataset_names=None):
        summary = self._summary() if summary is None else summary
        combined = records is not None
        if records is None:
            root = Path(self.output_dir)
            selected = set(dataset_names) if dataset_names is not None else None
            if selected is not None:
                if any(Path(name).name != name or name in ('.', '..') for name in selected):
                    raise ValueError('Dataset names must be safe filenames')
                folders = sorted(root/name for name in selected)
            else:
                folders = sorted(path for path in root.iterdir() if path.is_dir() and
                                 not path.name.startswith('.')) if root.is_dir() else []
            records = [dict(name=folder.name, path=str(folder), status='pending') for folder in folders]
            summary['datasets'].extend(records)
            if not records:
                self._event(dict(stage='features', status='warning', message='No tile datasets selected'))
        for record in records:
            name, folder = record['name'], Path(record['path'])
            self._current_dataset = name
            prior_status = record['status']
            try:
                self._checkpoint()
                if not allow_legacy:
                    validate_dataset(folder, require_v3=True)
                extractor = TopologicalFeatureExtractor(
                    image_dir=str(folder), labels_dir=self.labels_dir,
                    output_dir=str(Path(self.features_dir)/name), large_image_name=name,
                    settings=self.settings, progress=self._event, cancelled=self.cancelled,
                    labels_mode=labels_mode, allow_legacy=allow_legacy)
                result = extractor.execute()
                record['features'] = result
                if combined:
                    record['slice_status'] = prior_status
                else:
                    record['status'] = 'processed'
                    summary['processed'] += 1
                self._event(dict(stage='features', status='completed', message='Feature analysis finished', result=result))
            except PipelineCancelled:
                if combined and prior_status in ('processed', 'skipped'):
                    summary[prior_status] -= 1
                    record['slice_status'] = prior_status
                record['status'] = 'cancelled'
                summary['cancelled'] = True
                break
            except Exception as error:
                if combined and prior_status in ('processed', 'skipped'):
                    summary[prior_status] -= 1
                    record['slice_status'] = prior_status
                record.update(status='failed', error=str(error))
                summary['failed'] += 1
                self._event(dict(stage='features', status='failed', message=str(error)))
        return summary
