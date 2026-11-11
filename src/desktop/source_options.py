"""Resolve per-source calibration without rewriting immutable factory defaults."""
from src.app_settings import PipelineSettings
from src.image_io import inspect_tiff


def calibration_mode(project, settings=None):
    """Interpret older projects with a saved pixel size as manual overrides."""
    stored = getattr(project, '_extra_fields', {}).get('calibration_mode')
    if stored in ('auto', 'manual'):
        return stored
    return 'manual' if (settings or project.settings).get('pixel_size_um') is not None else 'auto'


def source_options(project, settings, source=None, dataset=None):
    """Return a run settings snapshot and the calibration evidence for its source.

    A linked TIFF is re-inspected for new work. Imported tiles without a source
    TIFF can use the calibration recorded when they were prepared.
    """
    options = PipelineSettings.from_dict(settings).to_dict()
    mode = calibration_mode(project, options)
    if mode == 'manual':
        return PipelineSettings.from_dict(options), dict(mode=mode, pixel_size_um=options['pixel_size_um'])
    if source is None and dataset:
        source = next((s for s in project.sources if s.get('id') == dataset.get('source_id')
                       or s.get('path') == dataset.get('source_path')), None)
    if source:
        info = inspect_tiff(source['path'])
        calibration = info['calibration']
    else:
        calibration = (dataset or {}).get('calibration', {})
        if not calibration and dataset:
            from .service import dataset_manifest
            run = dataset_manifest(dataset).get('run_info', {})
            calibration = run.get('source_image', {}).get('calibration', {})
            saved = (dataset.get('settings') or run.get('settings') or {}).get('pixel_size_um')
            if not calibration and saved is not None:
                calibration = dict(status='valid', pixel_size_um=saved, source='Saved dataset calibration')
    # Missing or unsupported physical metadata leaves measurements in source pixels.
    options['pixel_size_um'] = calibration.get('pixel_size_um') if calibration.get('status') == 'valid' else None
    return PipelineSettings.from_dict(options), dict(calibration, mode=mode)
