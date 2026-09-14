"""Reconstruct exact v2 overviews from saved valid masks, including after exclusion."""
import re
import tempfile
from pathlib import Path
import cv2
import numpy as np
from src import config
from src.partition_geometry import read_manifest, restore_ownership, render_overview, checked_imwrite


class HighResOverviewReconstructor:
    def __init__(self, project_root=None):
        self.project_root = Path(project_root) if project_root else Path(__file__).resolve().parents[1]

    @staticmethod
    def extract_tile_id(filename):
        match = re.search(r'tile_(\d+)',str(filename))
        return int(match.group(1)) if match else 0

    def reconstruct(self,dataset_name,target_dim=None,source_type='filtered'):
        if source_type not in ('filtered','raw'):
            raise ValueError('source_type must be filtered or raw')
        base = self.project_root/(config.OUTPUT_DIR if source_type=='filtered' else config.RAW_OUTPUT_DIR)/dataset_name
        manifest = read_manifest(base/'overview'/(dataset_name+'_tiles_coords.json'))
        active = {r['id'] for r in manifest['tiles'] if (base/r['filename']).is_file()}
        if not active:
            raise ValueError('No active tiles in {}'.format(base))
        h,w = manifest['image_shape']
        first = next(r for r in manifest['tiles'] if r['id'] in active)
        sample = cv2.imread(str(base/first.get('native_filename',first['filename'])),cv2.IMREAD_UNCHANGED)
        if sample is None:
            raise ValueError('Unreadable tile')
        shape = (h,w) if sample.ndim==2 else (h,w,sample.shape[2])
        with tempfile.TemporaryDirectory(prefix='.overview_',dir=str(base)) as work:
            owners = np.memmap(str(Path(work)/'owners.dat'),dtype=np.int32,mode='w+',shape=(h,w))
            canvas = np.memmap(str(Path(work)/'pixels.dat'),dtype=sample.dtype,mode='w+',shape=shape)
            try:
                restore_ownership(base,manifest,owners,active)
                for rec in manifest['tiles']:
                    path=base/rec['filename']
                    if not path.is_file():
                        path=base/'excluded_tiles'/rec['filename']
                    if not path.is_file():
                        continue
                    if 'native_filename' in rec:
                        path=base/rec['native_filename']
                    tile=cv2.imread(str(path),cv2.IMREAD_UNCHANGED)
                    x1,y1,x2,y2=[rec[k] for k in ('x1','y1','x2','y2')]
                    valid=cv2.imread(str(base/rec['valid_mask']),cv2.IMREAD_GRAYSCALE)
                    if tile is None or valid is None or tile.shape[0]<y2-y1 or tile.shape[1]<x2-x1:
                        raise ValueError('Missing/corrupt tile or valid mask')
                    canvas[y1:y2,x1:x2][valid>0]=tile[:y2-y1,:x2-x1][valid>0]
                dim=target_dim or config.OVERVIEW_MAP_SIZE
                result=render_overview(canvas,owners,[r for r in manifest['tiles'] if r['id'] in active],dim)
                output=base/'overview'/(dataset_name+'_TILE_INDEX_MAP_{}px.png'.format(dim))
                checked_imwrite(output,result)
                return str(output)
            finally:
                for a in (owners,canvas):
                    a.flush()
                    a._mmap.close()
