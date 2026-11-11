"""Resolve immutable edited tile versions while keeping prepared tile identities."""

import hashlib
import json
from pathlib import Path

from src.partition_geometry import dataset_path, png_shape


ACTIVE_EDITS_FILE = 'active_tile_edits.json'
EDIT_ARTIFACTS = dict(filename='model.png', native_filename='native.png',
                      valid_mask='valid_mask.png', coverage_mask='coverage.png')


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def active_tile_edits(base):
    path = Path(base) / ACTIVE_EDITS_FILE
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('schema_version') != 1 or not isinstance(value.get('tiles'), dict):
        raise ValueError('Invalid active tile edit registry')
    return value['tiles']


def active_edit_revision(base, tile_id):
    return active_tile_edits(base).get(str(tile_id), {}).get('version')


def effective_tile_record(base, record, edits=None):
    """Keep filename as the label/CSV key and resolve pixels through a separate map."""
    active = (active_tile_edits(base) if edits is None else edits).get(str(record['id']))
    result = dict(record)
    if active is not None:
        version = active['version']
        folder = dataset_path(base, version)
        metadata = json.loads((folder / 'edit.json').read_text(encoding='utf-8'))
        if (metadata.get('schema_version') != 2 or metadata.get('tile_id') != record['id']
                or metadata.get('tile_filename') != record['filename']):
            raise ValueError('Active edit belongs to another tile')
        if metadata.get('transform') != record.get('transform'):
            raise ValueError('Active edit has a different native transform')
        artifacts = {key: version + '/' + name for key, name in EDIT_ARTIFACTS.items()}
        transform = record['transform']
        for key, shape in (('native_filename', transform['native_crop_shape']),
                           ('valid_mask', transform['native_crop_shape']),
                           ('filename', transform['output_shape']),
                           ('coverage_mask', transform['output_shape'])):
            if png_shape(dataset_path(base, artifacts[key])) != tuple(shape):
                raise ValueError('Active edit artifact has an unexpected shape')
        result.update(edit_artifacts=artifacts, edit_reference=version,
                      valid_pixels=metadata['valid_pixels'])
    return result


def tile_artifact_path(base, record, key):
    """Resolve effective image data, retaining explicit model exclusion separately."""
    relative = record.get('edit_artifacts', {}).get(key, record.get(key))
    return dataset_path(base, relative)


def tile_edit_signature(base):
    """Fingerprint selected versions and their immutable content for provenance."""
    edits = active_tile_edits(base)
    signatures = {}
    for tile_id, entry in sorted(edits.items()):
        folder = dataset_path(base, entry['version'])
        hashes = {name: file_sha256(folder / name) for name in (*EDIT_ARTIFACTS.values(), 'edit.json')}
        if hashes != entry['sha256']:
            raise ValueError('Active tile edit files changed after saving')
        signatures[tile_id] = dict(version=entry['version'], sha256=hashes)
    return signatures
