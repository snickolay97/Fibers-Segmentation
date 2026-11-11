"""Editable display names beside the immutable evaluation artifacts."""

import json
from pathlib import Path

from .i18n import tr
from .project import atomic_json


def _name_path(report, model):
    if model not in ('tree', 'forest'):
        raise ValueError(model)
    return Path(report).with_name(f'{model}_name.json')


def model_alias(report, model):
    if model in ('tree', 'forest'):
        try:
            name = json.loads(_name_path(report, model).read_text(encoding='utf-8'))['name']
            if isinstance(name, str):
                return name.strip()[:80]
        except (OSError, ValueError, TypeError, KeyError):
            pass
    return ''


def model_display_name(report, model):
    alias = model_alias(report, model)
    return f'{alias} ({tr(model)})' if alias else tr(model)


def save_model_name(report, model, name):
    atomic_json(_name_path(report, model), {'name': name.strip()[:80]})
