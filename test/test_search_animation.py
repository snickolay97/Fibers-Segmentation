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
            s.search_stats=dict(edge=0,corridor=0,dijkstra=0,deferred=0)
            mask=np.zeros((64,64),np.uint8);mask[:,45:60]=255
            trace=[]
            seam=s._boundary(mask, trace)
            s._save_tile_animations('case', np.zeros((100,100),np.uint8),
                                    dict(id=33, x1=10, y1=20), (trace, []))
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

    def test_animation_ids_and_origins_match_exported_tiles_in_both_directions(self):
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            s=SmartSlicer(target_size=64,margin_start=45,margin_end=60,min_margin_limit=18,
                          dynamic_step=3,enable_animation=True,animation_dir=root/'animations',
                          save_raw_tiles=False)
            # The entirely protected image loses all seam proposals after component repair.
            for name, value in (('empty', 0), ('protected', 255)):
                mask=np.full((110,110),value,np.uint8)
                result=s.slice(mask,mask,mask,name,root/name)
                tiles={tile['id']: tile for tile in result['tiles']}
                folder=root/'animations'/name
                files=list(folder.glob('*.json'))
                self.assertEqual(len(files),result['checks']['search_animations'])
                for file in files:
                    trace=json.loads(file.read_text())
                    tile=tiles[trace['tile_id']]
                    self.assertEqual(trace['origin_xy'], [tile['x1'], tile['y1']])
                    self.assertEqual(file.stem, f"{name}_search_{tile['id']:04d}_{trace['axis']}")
                    self.assertTrue(file.with_suffix('.gif').is_file())
                if name == 'empty':
                    for axis in ('right', 'bottom'):
                        self.assertTrue((folder/f'empty_search_0002_{axis}.gif').is_file())
                else:
                    self.assertEqual(files, [])

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
