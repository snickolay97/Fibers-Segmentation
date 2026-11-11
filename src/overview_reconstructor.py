"""Reconstruct v2/v3 overviews from saved valid masks, including after exclusion."""
import re
import json
import tempfile
from pathlib import Path
import cv2
import numpy as np
from src import config
from src.partition_geometry import (read_manifest, restore_ownership, render_overview,
                                    checked_imwrite, validate_dataset, dataset_path,
                                    find_dataset_manifest)
from src.tile_edits import effective_tile_record, active_tile_edits, tile_artifact_path, tile_edit_signature


class HighResOverviewReconstructor:
    """Rebuild the display and active boundaries in source coordinates."""
    def __init__(self, project_root=None, progress=None, cancelled=None):
        self.project_root = Path(project_root) if project_root else Path(__file__).resolve().parents[1]
        self.progress, self.cancelled = progress, cancelled

    @staticmethod
    def extract_tile_id(filename):
        match = re.search(r'tile_(\d+)',str(filename))
        return int(match.group(1)) if match else 0

    def reconstruct(self,dataset_name,target_dim=None,source_type='filtered'):
        if source_type not in ('filtered','raw'):
            raise ValueError('source_type must be filtered or raw')
        root = self.project_root/(config.OUTPUT_DIR if source_type=='filtered' else config.RAW_OUTPUT_DIR)
        base = dataset_path(root, dataset_name)
        return self.reconstruct_dataset(base, target_dim)

    def reconstruct_dataset(self, dataset_dir, target_dim=None, progress=None, cancelled=None):
        """Compose the saved crops into a full source canvas before rendering."""
        base = Path(dataset_dir).resolve()
        progress = progress if progress is not None else self.progress
        cancelled = cancelled if cancelled is not None else self.cancelled
        def check_cancelled():
            if cancelled and cancelled():
                from src.app_settings import PipelineCancelled
                raise PipelineCancelled('Operation cancelled')
        check_cancelled()
        manifest = validate_dataset(base, require_v3=False)
        edit_signature = tile_edit_signature(base)
        edits = active_tile_edits(base)
        records = [effective_tile_record(base, record, edits) for record in manifest['tiles']]
        dataset_name = manifest.get('source_name', base.name)
        output_name = dataset_name+'_TILE_INDEX_MAP_{}px.png'
        # Validate the manifest-derived filename before writing anything.
        dataset_path(base, 'overview/'+output_name.format(1))
        # Excluded tiles remain visible and labelled in this display map.
        # The physical file locations alone decide measurement inclusion.
        active = {r['id'] for r in manifest['tiles'] if (base/r['filename']).is_file()}
        for rec in records:
            rec['excluded'] = rec['id'] not in active
        h,w = manifest['image_shape']
        first = records[0]
        sample_path = tile_artifact_path(base, first, 'native_filename' if first.get('native_filename') else 'filename')
        if not sample_path.is_file():
            sample_path = dataset_path(base, 'excluded_tiles/'+first['filename'])
        sample = cv2.imread(str(sample_path),cv2.IMREAD_UNCHANGED)
        if sample is None:
            raise ValueError('Unreadable tile')
        shape = (h,w) if sample.ndim==2 else (h,w,sample.shape[2])
        with tempfile.TemporaryDirectory(prefix='.overview_',dir=str(base)) as work:
            owners = np.memmap(str(Path(work)/'owners.dat'),dtype=np.int32,mode='w+',shape=(h,w))
            canvas = np.memmap(str(Path(work)/'pixels.dat'),dtype=sample.dtype,mode='w+',shape=shape)
            try:
                canvas[:] = 0
                restore_ownership(base,manifest,owners)
                for index, rec in enumerate(records):
                    check_cancelled()
                    path=dataset_path(base,rec['filename'])
                    if not path.is_file():
                        path=dataset_path(base,'excluded_tiles/'+rec['filename'])
                    # v3 stores a source-scale crop independently of the model.
                    # v2 reconstruction can crop its model directly.
                    if 'native_filename' in rec:
                        path=tile_artifact_path(base, rec, 'native_filename')
                    tile=cv2.imread(str(path),cv2.IMREAD_UNCHANGED)
                    x1,y1,x2,y2=[rec[k] for k in ('x1','y1','x2','y2')]
                    valid=cv2.imread(str(tile_artifact_path(base, rec, 'valid_mask')),cv2.IMREAD_GRAYSCALE)
                    if tile is None or valid is None or tile.shape[0]<y2-y1 or tile.shape[1]<x2-x1:
                        raise ValueError('Missing/corrupt tile or valid mask')
                    canvas[y1:y2,x1:x2][valid>0]=tile[:y2-y1,:x2-x1][valid>0]
                    if rec.get('edit_reference'):
                        local_owners = owners[y1:y2, x1:x2]
                        local_owners[(local_owners == rec['id']) & (valid == 0)] = 0
                    if progress:
                        progress(dict(stage='overview',completed=index+1,total=len(manifest['tiles']),tile=rec['filename']))
                dim=target_dim or config.OVERVIEW_MAP_SIZE
                if not isinstance(dim,int) or dim <= 0:
                    raise ValueError('Overview dimension must be a positive integer')
                check_cancelled()
                result=render_overview(canvas,owners,records,dim)
                check_cancelled()
                output=dataset_path(base,'overview/'+output_name.format(dim))
                staged=Path(work)/'overview.png'
                checked_imwrite(staged,result)
                check_cancelled()
                if tile_edit_signature(base) != edit_signature:
                    raise ValueError('Tile edits changed during overview reconstruction')
                staged.replace(output)
                marker = Path(work) / 'edits.json'
                marker.write_text(json.dumps(edit_signature, ensure_ascii=False), encoding='utf-8')
                marker.replace(output.with_suffix('.edits.json'))
                inclusion = Path(work)/'inclusion.json'
                inclusion.write_text(json.dumps(sorted(active)),encoding='utf8')
                inclusion.replace(output.with_suffix('.inclusion.json'))
                return str(output)
            finally:
                for a in (owners,canvas):
                    a.flush()
                    a._mmap.close()
