"""Exact-zero exclusion audit for source-scale pixels, independent of display."""
import json
import os
from pathlib import Path
import tempfile

import cv2
import numpy as np

from src.partition_geometry import dataset_path, find_dataset_manifest, read_manifest
from src.tile_edits import active_tile_edits, effective_tile_record, tile_artifact_path

STATE_FILE = 'tile_exclusions.json'


def exclusion_state(base):
    path = Path(base)/STATE_FILE
    if not path.exists():
        return dict(schema_version=1, tiles={})
    value = json.loads(path.read_text(encoding='utf8'))
    if value.get('schema_version') != 1 or not isinstance(value.get('tiles'), dict):
        raise ValueError('Invalid tile exclusion state')
    return value


def save_exclusion_state(base, state):
    """Publish the sidecar after all model renames, permitting rollback on failure."""
    base = Path(base)
    with tempfile.TemporaryDirectory(prefix='.exclusions_', dir=base) as temporary:
        path = Path(temporary)/STATE_FILE
        path.write_text(json.dumps(state,indent=2),encoding='utf8')
        os.replace(path, base/STATE_FILE)


def pixel_revision(base, record):
    """Cache only immutable input file identities; a manual restore retains them."""
    if not record.get('native_filename') or not record.get('valid_mask'):
        return None
    values = {'edit': record.get('edit_reference')}
    for key in ('native_filename','valid_mask'):
        path = tile_artifact_path(base,record,key)
        stat = path.stat()
        values[key] = dict(path=path.relative_to(Path(base).resolve()).as_posix(),
                           size=stat.st_size,mtime_ns=stat.st_mtime_ns)
    return values


def _records(base):
    manifest = read_manifest(find_dataset_manifest(base))
    edits = active_tile_edits(base)
    return [effective_tile_record(base,r,edits) for r in manifest['tiles']]


def black_scan_needed(base):
    state = exclusion_state(base)['tiles']
    for record in _records(base):
        if dataset_path(base,record['filename']).is_file():
            revision = pixel_revision(base,record)
            if revision is not None and state.get(str(record['id']),{}).get('revision') != revision:
                return True
    return False


def inspect_black_tiles(base, progress=None, cancelled=None):
    """Plan the complete batch before excluding anything; preserve even value 1.

    Validity padding is excluded from the test. An empty valid region also has
    no measurable signal. IMREAD_UNCHANGED prevents uint16 down-conversion.
    """
    from src.app_settings import PipelineCancelled
    state = exclusion_state(base)
    records = _records(base)
    selected = []
    def check():
        if cancelled and cancelled():
            raise PipelineCancelled('Operation cancelled')
    for index,record in enumerate(records):
        check()
        if not dataset_path(base,record['filename']).is_file():
            continue
        revision = pixel_revision(base,record)
        if revision is None or state['tiles'].get(str(record['id']),{}).get('revision') == revision:
            continue
        native = cv2.imdecode(np.frombuffer(tile_artifact_path(base,record,'native_filename').read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
        valid = cv2.imdecode(np.frombuffer(tile_artifact_path(base,record,'valid_mask').read_bytes(),np.uint8),cv2.IMREAD_GRAYSCALE)
        if native is None or valid is None or native.shape[:2] != valid.shape:
            raise ValueError('Unreadable native tile or validity mask')
        black = not np.any(native[valid > 0])
        if pixel_revision(base,record) != revision:
            raise ValueError('Tile changed during empty-tile inspection')
        state['tiles'][str(record['id'])] = dict(revision=revision,kind='black' if black else 'checked',
                                                valid_pixels=int(np.count_nonzero(valid)),all_zero=bool(black))
        if black:
            selected.append(record['id'])
        if progress:
            progress(dict(stage='exclude_black',completed=index+1,total=len(records)))
    check()
    return selected,state
