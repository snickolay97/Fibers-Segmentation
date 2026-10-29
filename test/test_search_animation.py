import tempfile,unittest,json
from pathlib import Path
import numpy as np
from PIL import Image,ImageChops
from src import config
from src.block2_slicer import SmartSlicer
from src.search_animation import save_search_animation

class AnimationTests(unittest.TestCase):
    def test_actual_trials_and_frames(self):
        with tempfile.TemporaryDirectory() as work:
            s=SmartSlicer(target_size=64,margin_start=45,margin_end=60,min_margin_limit=18,dynamic_step=3,enable_animation=True,animation_dir=work)
            s._animation_name='case';s._animation_axis='right';s._animation_origin=(10,20)
            s._animation_counter=0;s.search_stats=dict(edge=0,corridor=0,dijkstra=0,deferred=0)
            mask=np.zeros((64,64),np.uint8);mask[:,45:60]=255
            s._animation_background=np.zeros_like(mask)
            seam=s._boundary(mask)
            trace=json.loads(next((Path(work)/'case').glob('*.json')).read_text())
            self.assertGreater(len(trace['windows']),1)
            gif=Image.open(str(next((Path(work)/'case').glob('*.gif'))))
            self.assertGreater(gif.n_frames,3)
            first=gif.convert('RGB');gif.seek(gif.n_frames-1)
            self.assertIsNotNone(ImageChops.difference(first,gif.convert('RGB')).getbbox())
            final=np.asarray(gif.convert('RGB'))
            self.assertGreater(np.count_nonzero((final[:,:,0]>220)&(final[:,:,1]>200)&(final[:,:,2]<80)),10)
            gif.close()
            self.assertFalse(np.any(mask[np.arange(64),seam]))

    def test_unreachable_animation(self):
        with tempfile.TemporaryDirectory() as work:
            mask=np.ones((20,20),np.uint8)*255
            save_search_animation(work,'blocked',1,'right',(0,0),mask,None,[[4,18]],None,'unreachable')
            self.assertTrue(next(Path(work).glob('*.gif')).is_file())

    def test_coverage_disabled(self):
        with tempfile.TemporaryDirectory() as work:
            out=Path(work)/'filtered';rawout=Path(work)/'raw';m=np.zeros((30,30),np.uint8)
            s=SmartSlicer(target_size=64,margin_start=45,margin_end=60,min_margin_limit=18,dynamic_step=3,enable_animation=False)
            r=s.slice(m,m,m,'case',out,rawout)
            self.assertNotIn('coverage_mask',r['tiles'][0])
            self.assertFalse((out/'coverage_masks').exists())
            self.assertTrue((out/r['tiles'][0]['valid_mask']).exists())

if __name__=='__main__':unittest.main()
