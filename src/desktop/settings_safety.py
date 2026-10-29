"""Minimal, backed-up recovery of invalid persisted project settings."""
from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import uuid

from src.app_settings import PipelineSettings, inspect_settings
from src.default_settings import DEFAULTS_VERSION, FACTORY_DEFAULTS, factory_defaults
from .project import atomic_json, timestamp


def _json_safe(value):
    """Keep bad historical values descriptive without writing NaN into JSON."""
    if isinstance(value,float) and not math.isfinite(value):
        return dict(type='float', representation=repr(value))
    if value is None or isinstance(value,(str,int,float,bool)):
        return value
    if isinstance(value,Mapping):
        return {str(key):_json_safe(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):
        return [_json_safe(item) for item in value]
    return dict(type=type(value).__name__, representation=repr(value))


def backup_project(project, reason='Project settings recovery'):
    """Back up exact disk bytes, returning their unique backup filename.

    This does not save or otherwise modify the project itself. A sibling
    metadata file records the reason, checksum and factory-default revision.
    """
    source = Path(project.path).resolve()
    original = source.read_bytes()
    recovery = source.parent/'.recovery'
    if source.parent not in recovery.resolve().parents:
        raise ValueError('Recovery backups must remain beside the project')
    recovery.mkdir(exist_ok=True)
    moment = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    directory = recovery/(moment+'-'+uuid.uuid4().hex[:12])
    directory.mkdir()
    target = directory/source.name
    with target.open('xb') as handle:
        handle.write(original)
    metadata_name = 'backup_metadata.json' if source.name.casefold() != 'backup_metadata.json' else '.backup_metadata.json'
    atomic_json(directory/metadata_name, dict(
        source_path=str(source), reason=str(reason), time=timestamp(),
        defaults_version=DEFAULTS_VERSION,
        sha256=hashlib.sha256(original).hexdigest()))
    return str(target)


def recover_project_settings(project):
    """Repair only invalid settings, preserving valid choices and project data.

    Missing known keys are valid legacy settings and do not trigger recovery.
    Unknown keys are removed only after an exact backup and recorded in history.
    Calling this again on repaired settings has no further side effects.
    """
    issues = inspect_settings(project.settings)
    report = dict(status='unchanged', changed=False, issues=issues, changes=[],
                  backup_path=None, defaults_version=DEFAULTS_VERSION)
    if not issues:
        return report
    if not isinstance(project.history,list):
        raise ValueError('Project history must be a list before settings can be recovered')
    settings = dict(project.settings) if isinstance(project.settings,Mapping) else factory_defaults()
    changes = []
    for issue in issues:
        name = issue['field']
        if issue['code'] == 'container_type':
            replacement = factory_defaults()
            action = 'replace_invalid_settings_container'
        elif issue['code'] == 'unknown':
            settings.pop(name,None)
            replacement, action = None, 'remove_unknown_setting'
        else:
            replacement = FACTORY_DEFAULTS[name]
            settings[name] = replacement
            action = 'restore_factory_value'
        changes.append(dict(field=name, code=issue['code'], reason=issue['message'],
                            action=action, old=_json_safe(issue['value']),
                            new=_json_safe(replacement), defaults_version=DEFAULTS_VERSION))
    # Fail before a backup/write if a future coupled rule cannot be repaired by
    # replacing just its reported fields. Never silently reset every setting.
    PipelineSettings.from_dict(settings)
    backup_path = backup_project(project, reason='Repair invalid project settings')
    event = dict(time=timestamp(), action='recover_project_settings',
                 reason='Invalid persisted project settings', changes=changes,
                 defaults_version=DEFAULTS_VERSION, backup_path=backup_path)
    original_settings, original_history = project.settings, project.history
    project.settings = settings
    project.history = list(original_history)+[event]
    try:
        project.save()
    except BaseException:
        project.settings, project.history = original_settings, original_history
        raise
    report.update(status='recovered', changed=True, changes=changes, backup_path=backup_path)
    return report
