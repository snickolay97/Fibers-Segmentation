"""Persistent local project state, independent of the Qt interface."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
import logging
import os
import sqlite3
import uuid

from .i18n import register_translations, tr

register_translations({
    'The project file already exists. Open it or choose a different filename.':
        'Файл проекта уже существует. Откройте его или выберите другое имя.',
    'Unsupported SoLoData project version.': 'Неподдерживаемая версия проекта SoLoData.',
    'The project source or dataset list is damaged.': 'Повреждён список исходников или наборов проекта.',
    'Dataset not found in the project.': 'Набор не найден в проекте.',
    'The previous process did not finish. Restart the incomplete stage.':
        'Предыдущий процесс не завершился. Повторите незавершённую стадию.',
})

LAST_PROJECT_KEY = 'projects/last_opened'


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    """Stage JSON beside its destination so readers see one complete version."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


@dataclass
class Project:
    """Persist identities, paths and run state while scientific files live beside the JSON."""

    path: str
    name: str = 'SoLoData'
    workspace: str = ''
    sources: list = field(default_factory=list)
    datasets: list = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    active_dataset_id: str = None
    history: list = field(default_factory=list)
    schema_version: int = 1

    @staticmethod
    def creation_path(path):
        """Return the canonical JSON path for a requested new project name."""
        path = Path(path).resolve()
        if path.name.casefold() != 'project.json':
            path = path.parent / path.stem / 'project.json'
        return path

    @classmethod
    def create(cls, path, name='SoLoData', *, settings=None, calibration_mode=None):
        from src.app_settings import PipelineSettings
        path = Path(path).resolve()
        if path.exists():
            raise FileExistsError(tr('The project file already exists. Open it or choose a different filename.'))
        # A project owns a directory, rather than sharing the parent of an
        # arbitrary JSON file with other projects. Keep the established
        # <folder>/project.json form; a chosen study.json becomes
        # <folder>/study/project.json.
        path = cls.creation_path(path)
        if path.exists():
            raise FileExistsError(tr('The project file already exists. Open it or choose a different filename.'))
        project = cls(path=str(path), name=name, workspace=str(path.parent),
                      settings=PipelineSettings.from_dict(settings).to_dict())
        project._extra_fields = {'storage_layout_version': 2}
        if calibration_mode in ('auto', 'manual'):
            project._extra_fields['calibration_mode'] = calibration_mode
        project.save()
        return project

    @classmethod
    def load(cls, path):
        path = Path(path).resolve()
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict) or value.get('schema_version') != 1:
            raise ValueError(tr('Unsupported SoLoData project version.'))
        fields = cls.__dataclass_fields__
        project = cls(**{k: v for k, v in value.items() if k in fields})
        # Preserve unrelated extensions when saving or repairing settings.
        project._extra_fields = {k:v for k,v in value.items() if k not in fields}
        # Trust the actual opened JSON location for the project root. Stored
        # data paths are resolved separately by the operations that use them.
        project.path = str(path)
        project.workspace = str(path.parent)
        if any(not isinstance(items, list) or any(not isinstance(item, dict) for item in items)
               for items in (project.sources, project.datasets)):
            raise ValueError(tr('The project source or dataset list is damaged.'))
        return project

    def save(self):
        """Apply the same settings validation used by the form before publishing."""
        from src.app_settings import inspect_settings, SettingsValidationError
        issues = inspect_settings(self.settings)
        if issues:
            raise SettingsValidationError(issues)
        atomic_json(self.path, self.to_dict())
        # The JSON commit remains sufficient even if a derived index is locked,
        # corrupt, from a newer release, or cannot fit on the current disk.
        self._catalog_error = None
        try:
            self.catalog().synchronize()
        except (OSError, ValueError, sqlite3.Error) as error:
            self._catalog_error = str(error)
            logging.getLogger(__name__).warning('Project saved; SQLite catalog unavailable: %s', error)

    def catalog(self):
        """Return the saved-state SQL index; queries refuse an outdated snapshot."""
        from .project_catalog import ProjectCatalog
        return ProjectCatalog(self.path)

    def to_dict(self):
        result = dict(getattr(self, '_extra_fields', {}))
        result.update({key: getattr(self, key) for key in self.__dataclass_fields__})
        return result

    def get_dataset(self, dataset_id):
        for dataset in self.datasets:
            if dataset['id'] == dataset_id:
                return dataset
        raise ValueError(tr('Dataset not found in the project.'))

    def add_history(self, action, **details):
        self.history.append(dict(time=timestamp(), action=action, **details))
        self.save()

    def recover_interrupted(self):
        """Mark unfinished stages after an earlier writer process disappeared."""
        changed = False
        for dataset in self.datasets:
            if dataset.get('status') == 'running':
                dataset['status'] = 'interrupted'
                dataset['error'] = tr('The previous process did not finish. Restart the incomplete stage.')
                changed = True
        if changed:
            self.add_history('recover_interrupted')
        return changed
