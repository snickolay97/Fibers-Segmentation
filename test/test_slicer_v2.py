import json
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from src import config
from src.block2_slicer import SmartSlicer
from src.partition_geometry import connected_components_striped, restore_ownership, ownership_boundary


def slicer(**kwargs):
    options=dict(target_size=64,margin_start=45,margin_end=60,dynamic_step=3,min_margin_limit=18,min_corridor_width=5,enable_animation=False,save_raw_tiles=True)
    options.update(kwargs)
    return SmartSlicer(**options)


class SlicerTests(unittest.TestCase):
    def test_trailing_corridor(self):
        for vector in ([1]*10+[0]*7,[1]*10+[0]*7+[1]):
            self.assertEqual(SmartSlicer._find_safe_corridor_cut(np.array(vector),15),13)

    def test_blocked_start_is_unreachable(self):
        m=np.zeros((10,10),np.uint8);m[0]=255
        seam,cost=slicer().find_topographical_seam(m,'vertical')
        self.assertEqual(seam.size,0);self.assertFalse(np.isfinite(cost))

    def test_monotone_path(self):
        m=np.full((30,20),255,np.uint8)
        for y in range(30):
            x=5+min(y,29-y)//3;m[y,x:x+3]=0
        for axis,mask in [('vertical',m),('horizontal',m.T)]:
            seam,cost=slicer().find_topographical_seam(mask,axis)
            self.assertTrue(np.isfinite(cost));self.assertEqual(len(seam),30)
            self.assertTrue(np.all(np.abs(np.diff(seam))<=1));self.assertFalse(np.any(m[np.arange(30),seam]))

    def test_striped_components_match_opencv(self):
        rng=np.random.RandomState(5)
        m=(rng.rand(99,81)<.22).astype(np.uint8)
        m[np.arange(81),np.arange(81)]=1
        labels=np.zeros(m.shape,np.int32)
        stats=connected_components_striped(m,labels,stripe_height=7)
        n,expected=cv2.connectedComponents(m,connectivity=8)
        self.assertEqual(len(stats),n)
        for k in range(1,n):
            self.assertEqual(len(np.unique(labels[expected==k])),1)
        self.assertEqual(int(stats[:,4].sum()),int(m.sum()))

    def roundtrip(self,mask,**options):
        raw=np.arange(mask.size,dtype=np.uint8).reshape(mask.shape)
        filtered=(raw//2).astype(np.uint8)
        with tempfile.TemporaryDirectory() as work:
            out=Path(work)/'filtered';rawout=Path(work)/'raw'
            previous=config.OVERVIEW_MAP_SIZE;config.OVERVIEW_MAP_SIZE=150
            try: manifest=slicer(**options).slice(filtered,raw,mask,'case',str(out),str(rawout))
            finally: config.OVERVIEW_MAP_SIZE=previous
            own=np.zeros(mask.shape,np.int32);restore_ownership(out,manifest,own)
            self.assertFalse(np.any(own==0))
            n,labels=cv2.connectedComponents((mask>0).astype(np.uint8),connectivity=8)
            for k in range(1,n): self.assertEqual(len(np.unique(own[labels==k])),1)
            reconstructed=np.zeros_like(raw);seen=np.zeros(mask.shape,np.uint8)
            for rec in manifest['tiles']:
                x1,y1,x2,y2=[rec[k] for k in ('x1','y1','x2','y2')]
                valid=cv2.imread(str(out/rec['valid_mask']),0)>0
                a=cv2.imread(str(rawout/rec.get('native_filename',rec['filename'])),0)[:y2-y1,:x2-x1]
                b=cv2.imread(str(out/rec.get('native_filename',rec['filename'])),0)[:y2-y1,:x2-x1]
                self.assertTrue(np.array_equal(b[valid],filtered[y1:y2,x1:x2][valid]))
                reconstructed[y1:y2,x1:x2][valid]=a[valid]
                seen[y1:y2,x1:x2]+=valid.astype(np.uint8)
            self.assertTrue(np.array_equal(raw,reconstructed));self.assertTrue(np.all(seen==1))
            with self.assertRaises(FileExistsError):slicer().slice(filtered,raw,mask,'case',str(out),str(rawout))
            return manifest

    def test_empty_background_roundtrip(self):self.roundtrip(np.zeros((103,117),np.uint8))
    def test_occupied_window_preserved_oversized(self):
        manifest=self.roundtrip(np.full((103,117),255,np.uint8))
        self.assertEqual(manifest['checks']['oversized_crops'],1)
    def test_touching_diagonals_and_crossings(self):
        m=np.zeros((130,145),np.uint8)
        m[44:48,10:125]=255;m[5:105,57:61]=255
        m[np.arange(80),np.arange(80)]=255
        m[100:108,125:133]=255
        self.roundtrip(m)
    def test_long_fiber_fits_repositioned_tile(self):
        m=np.zeros((120,120),np.uint8);m[35:85,51:54]=255
        self.roundtrip(m)
    def test_oversized_error_before_export(self):
        with tempfile.TemporaryDirectory() as w:
            m=np.ones((100,100),np.uint8)
            with self.assertRaises(ValueError):slicer(oversized_policy='error').slice(m,m,m,'x',w,w+'/raw')
            self.assertFalse(list(Path(w).glob('*tile*.png')))
    def test_invalid_config(self):
        with self.assertRaises(ValueError):slicer(dynamic_step=0)
        with self.assertRaises(ValueError):slicer(margin_end=70)
    def test_boundary_has_no_tail(self):
        o=np.array([[1,1,2,2],[1,1,2,2],[3,3,3,3],[3,3,3,3]])
        edge=ownership_boundary(o)
        self.assertTrue(edge[0,2]);self.assertTrue(edge[1,2]);self.assertFalse(edge[3,2])
    def test_reconstructor_and_exclusion(self):
        from src.overview_reconstructor import HighResOverviewReconstructor
        with tempfile.TemporaryDirectory() as w:
            root=Path(w);out=root/config.OUTPUT_DIR/'tiny';rawout=root/config.RAW_OUTPUT_DIR/'tiny'
            m=np.zeros((100,100),np.uint8)
            previous=config.OVERVIEW_MAP_SIZE;config.OVERVIEW_MAP_SIZE=100
            try:r=slicer().slice(m,m,m,'tiny',str(out),str(rawout))
            finally:config.OVERVIEW_MAP_SIZE=previous
            path=HighResOverviewReconstructor(w).reconstruct('tiny',target_dim=100)
            self.assertTrue(Path(path).is_file())
            (out/'excluded_tiles').mkdir();first=r['tiles'][0]
            (out/first['filename']).rename(out/'excluded_tiles'/first['filename'])
            HighResOverviewReconstructor(w).reconstruct('tiny',target_dim=100)

if __name__=='__main__':unittest.main()
