"""Persistent local project state, independent of the Qt interface."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
import os
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


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
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
    path: str
    name: str = 'SoLoData'
    workspace: str = ''
    sources: list = field(default_factory=list)
    datasets: list = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    active_dataset_id: str = None
    history: list = field(default_factory=list)
    schema_version: int = 1

    @classmethod
    def create(cls, path, name='SoLoData'):
        from src.app_settings import PipelineSettings
        path = Path(path).resolve()
        if path.exists():
            raise FileExistsError(tr('The project file already exists. Open it or choose a different filename.'))
        project = cls(path=str(path), name=name, workspace=str(path.parent),
                      settings=PipelineSettings().to_dict())
        project.save()
        return project

    @classmethod
    def load(cls, path):
        path = Path(path).resolve()
        value = json.loads(path.read_text(encoding='utf-8'))
        if value.get('schema_version') != 1:
            raise ValueError(tr('Unsupported SoLoData project version.'))
        fields = cls.__dataclass_fields__
        project = cls(**{k: v for k, v in value.items() if k in fields})
        # Preserve unrelated extensions when saving or repairing settings.
        project._extra_fields = {k:v for k,v in value.items() if k not in fields}
        project.path = str(path)
        project.workspace = str(path.parent)
        if not isinstance(project.sources, list) or not isinstance(project.datasets, list):
            raise ValueError(tr('The project source or dataset list is damaged.'))
        return project

    def save(self):
        from src.app_settings import inspect_settings, SettingsValidationError
        issues = inspect_settings(self.settings)
        if issues:
            raise SettingsValidationError(issues)
        atomic_json(self.path, self.to_dict())

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
        changed = False
        for dataset in self.datasets:
            if dataset.get('status') == 'running':
                dataset['status'] = 'interrupted'
                dataset['error'] = tr('The previous process did not finish. Restart the incomplete stage.')
                changed = True
        if changed:
            self.add_history('recover_interrupted')
        return changed
