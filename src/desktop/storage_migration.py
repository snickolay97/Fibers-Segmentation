"""Transactional rename of managed legacy folders; scientific files stay intact."""
from copy import deepcopy
from pathlib import Path
import json
import os
import re
import shutil

from .project import atomic_json, timestamp
from .storage_names import readable_name, unused_file, version_path, new_version


_UUID = re.compile(r'^[0-9a-f]{12,32}$', re.I)


def _mapped(value, moves):
    """Replay nested renames in order to obtain the final absolute path."""
    if not value:
        return value
    path = Path(value).resolve()
    for old, new in moves:
        if path == old or old in path.parents:
            path = new / path.relative_to(old)
    return str(path)


def _rollback(moves):
    """Undo a completed prefix from child paths back to their parents."""
    for old, new in reversed(moves):
        if new.exists() and not old.exists():
            old.parent.mkdir(parents=True, exist_ok=True)
            os.rename(new, old)


def migrate_storage_names(project):
    """Plan moves, journal them, and commit the resulting project references.

    Moves are confined to recognized project-owned trees. The project JSON
    commit marker determines whether a pending journal needs to be reversed.
    """
    root = Path(project.workspace).resolve()
    # A commit marker distinguishes a completed rename from a crash before
    # the atomic project-file replacement. Pending operations roll back first.
    for log in (root/'backups').glob('Storage_layout_*/rename.json'):
        state = json.loads(log.read_text(encoding='utf-8'))
        if state.get('status') == 'pending':
            if any(root not in Path(value).resolve().parents for pair in state['moves'] for value in pair):
                raise ValueError('Storage recovery paths must stay inside their project')
            if getattr(project, '_extra_fields', {}).get('storage_migration') != log.parent.name:
                _rollback([(Path(a), Path(b)) for a,b in state['moves']])
            state['status'] = 'recovered'
            atomic_json(log, state)
    if getattr(project, '_extra_fields', {}).get('storage_layout_version', 1) >= 2:
        return dict(changed=False)
    moves, occupied = [], set()

    def add(old, new):
        old, new = Path(old), Path(new)
        if root not in old.resolve().parents or root not in new.resolve().parents:
            raise ValueError('Storage rename must stay inside its project')
        moves.append((old, new))
        occupied.add(str(new).casefold())

    def destination(parent, prefix):
        for index in range(1,100000):
            target = Path(parent)/f'{readable_name(prefix)}_{index:03d}'
            if not target.exists() and str(target).casefold() not in occupied:
                return target
        raise OSError('No unused storage name')

    # Source copies need no wrapper folder at all.
    for source in project.sources:
        path = Path(source['path']).resolve()
        if path.is_file() and path.parent.parent == root/'sources' and _UUID.fullmatch(path.parent.name):
            add(path, unused_file(root/'sources', readable_name(path.name), occupied))

    runs = root/'runs'
    for run in sorted(runs.iterdir()) if runs.exists() else []:
        if not run.is_dir() or not re.fullmatch(r'\d{8}T\d{6}-[0-9a-f]+', run.name, re.I):
            continue
        new_run = destination(runs, 'Preparation')
        add(run, new_run)
        stage_targets = set()
        for wrapper in sorted(run.iterdir()):
            if not wrapper.is_dir() or not _UUID.fullmatch(wrapper.name):
                continue
            for stage in sorted(wrapper.iterdir()):
                if not stage.is_dir() or stage.name not in ('tiles','raw','animations','labels','features'):
                    continue
                old = Path(_mapped(stage, moves))
                target = new_run/stage.name
                if target not in stage_targets:
                    add(old, target)
                    stage_targets.add(target)
                    occupied.update(str(target/item.name).casefold() for item in stage.iterdir())
                else:
                    for item in stage.iterdir():
                        add(Path(_mapped(item,moves)), unused_file(target, item.name, occupied))
            # Retain the wrapper's unrecognized contents under Other_data.
            add(Path(_mapped(wrapper,moves)), destination(new_run,'Other_data'))

    previews = root/'previews'
    preview_name = readable_name(Path(project.sources[0]['path']).stem) if len(project.sources) == 1 else 'Previous_previews'
    for path in sorted(previews.iterdir()) if previews.exists() else []:
        if path.is_dir() and _UUID.fullmatch(path.name):
            add(path, destination(previews/preview_name, 'Preview'))

    by_id = {dataset['id']:dataset for dataset in project.datasets}
    for stage, prefix in (('annotations','Labels'), ('measurements','Measurement')):
        parent = root/stage
        for folder in sorted(parent.iterdir()) if parent.exists() else []:
            if not folder.is_dir() or folder.name not in by_id:
                continue
            name = readable_name(by_id[folder.name]['name'])
            for version in sorted(folder.iterdir()):
                if version.is_dir():
                    add(version, destination(parent/name,prefix))
            add(folder, destination(parent,name+'_Other_data'))

    imported = root/'datasets'
    for folder in sorted(imported.iterdir()) if imported.exists() else []:
        if folder.is_dir() and _UUID.fullmatch(folder.name):
            children = list(folder.iterdir())
            if len(children)==1 and children[0].is_dir():
                add(children[0], destination(imported, 'Imported_'+readable_name(children[0].name)))
    if not moves:
        project._extra_fields['storage_layout_version'] = 2
        project.save()
        return dict(changed=False)

    backup = new_version(root/'backups', 'Storage_layout')
    # Capture the original project and all intended moves before renaming anything.
    shutil.copy2(project.path, backup/'project.json')
    record = dict(status='pending', time=timestamp(), moves=[[str(a),str(b)] for a,b in moves])
    atomic_json(backup/'rename.json', record)
    before = deepcopy(project.__dict__)
    completed = []
    try:
        for old,new in moves:
            new.parent.mkdir(parents=True, exist_ok=True)
            os.rename(old,new)
            completed.append((old,new))
        # Update the paths only after every rename has succeeded. Dataset and
        # object identities remain usable across the change in folder names.
        for source in project.sources:
            source['path'] = _mapped(source['path'], moves)
            preview = source.get('last_preview', {})
            for key in ('input_path', 'filtered_path', 'mask_path', 'native_filtered_path', 'native_mask_path'):
                if key in preview:
                    preview[key] = _mapped(preview[key], moves)
        from .service import fingerprint
        for dataset in project.datasets:
            for key in ('path','raw_path','source_path','labels_dir','results_dir','last_csv'):
                if dataset.get(key):
                    dataset[key] = _mapped(dataset[key], moves)
            if dataset.get('source_signature'):
                dataset['source_signature']['path'] = _mapped(dataset['source_signature']['path'], moves)
                dataset['preparation_key'] = fingerprint(dict(source=dataset['source_signature'], settings=dataset['settings']))
        project._extra_fields.update(storage_layout_version=2, storage_migration=backup.name)
        project.add_history('readable_storage_names', backup=str(backup), moves=record['moves'])
    except Exception:
        _rollback(completed)
        project.__dict__.clear()
        project.__dict__.update(before)
        record['status'] = 'rolled_back'
        atomic_json(backup/'rename.json',record)
        raise
    record['status'] = 'completed'
    try:
        atomic_json(backup/'rename.json', record)
    except OSError:
        pass  # The commit marker makes recovery deterministic on the next open.
    # Remove only empty directories in the managed trees, never scientific files.
    for name in ('sources','previews','runs','datasets','annotations','measurements'):
        parent = root/name
        if parent.exists():
            for path in sorted(parent.rglob('*'),key=lambda p:len(p.parts),reverse=True):
                if path.is_dir() and not path.is_symlink() and root in path.resolve().parents:
                    try: path.rmdir()
                    except OSError: pass
    return dict(changed=True, backup=str(backup), moves=len(moves))
