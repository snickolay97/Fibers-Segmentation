import tempfile,unittest,json
from pathlib import Path
import numpy as np
import cv2
from src.block2_slicer import SmartSlicer
from src.tile_scale import scale_metadata,fixed_canvas,output_to_source,measurement_factors
from src import config
from src.partition_geometry import connected_components_striped


class ScaleTests(unittest.TestCase):
    def test_4000_to_2000(self):
        tr=scale_metadata(4000,4000,2000)
        self.assertEqual(tr['source_pixels_per_output_pixel'],2)
        self.assertEqual(tr['source_area_per_output_pixel'],4)
        rec={'transform':tr,'x1':100,'y1':200}
        np.testing.assert_allclose(output_to_source([[10,20]],rec,True),[[120,240]])
        np.testing.assert_allclose(output_to_source([[10,20]],rec,pixel_centers=True),[[20.5,40.5]])
        self.assertAlmostEqual(measurement_factors(rec,.4)['um_per_output_pixel'],.8)

    def test_rectangular_crop_is_isotropic(self):
        tr=scale_metadata(60,120,50)
        self.assertEqual(tr['padding_native_ltrb'],[0,0,0,60])
        im=np.full((60,120),160,np.uint8)
        output=fixed_canvas(im,tr)
        self.assertEqual(output.shape,(50,50))
        self.assertTrue(np.all(output[:25]==160));self.assertTrue(np.all(output[25:]==0))
        self.assertEqual(tr['source_pixels_per_output_pixel'],2.4)

    def test_intact_component_keeps_existing_owner(self):
        mask=np.zeros((20,20),np.uint8);mask[7:10,12:15]=1
        labels=np.zeros(mask.shape,np.int32);stats=connected_components_striped(mask,labels)
        owners=np.ones(mask.shape,np.int32);owners[:,10:]=2
        records=[dict(id=1,x1=0,y1=0,x2=20,y2=20),dict(id=2,x1=0,y1=0,x2=20,y2=20)]
        result=SmartSlicer()._allocate_components(labels,stats,owners,records)
        self.assertTrue(np.all(owners[mask>0]==2));self.assertEqual(result['reassigned_components'],0)

    def test_fixed_export_native_and_reconstruction(self):
        from src.overview_reconstructor import HighResOverviewReconstructor
        with tempfile.TemporaryDirectory() as work:
            root=Path(work);out=root/config.OUTPUT_DIR/'sample';rawout=root/config.RAW_OUTPUT_DIR/'sample'
            raw=np.arange(9000,dtype=np.uint8).reshape(75,120);mask=np.ones_like(raw)
            s=SmartSlicer(enable_animation=False,target_size=64,margin_start=45,margin_end=60,min_margin_limit=18,dynamic_step=3)
            old=config.OVERVIEW_MAP_SIZE;config.OVERVIEW_MAP_SIZE=120
            try:r=s.slice(raw,raw,mask,'sample',out,rawout)
            finally:config.OVERVIEW_MAP_SIZE=old
            rec=r['tiles'][0]
            self.assertEqual(cv2.imread(str(out/rec['filename']),0).shape,(64,64))
            np.testing.assert_array_equal(cv2.imread(str(out/rec['native_filename']),0),raw)
            path=HighResOverviewReconstructor(root).reconstruct('sample',120)
            self.assertTrue(Path(path).exists())

    def test_polygon_mapping_and_padding(self):
        from src.block3_feature_extractor import TopologicalFeatureExtractor
        with tempfile.TemporaryDirectory() as work:
            p=Path(work)/'label.txt';p.write_text('0 0.1 0.2 0.3 0.2 0.3 0.4\n')
            polygon=TopologicalFeatureExtractor._parse_yolo(str(p),4000,4000)[0][1]
            np.testing.assert_array_equal(polygon[:,0],[[400,800],[1200,800],[1200,1600]])
            p.write_text('0 0.1 0.2 0.3 0.4\n')
            with self.assertRaises(ValueError):TopologicalFeatureExtractor._parse_yolo(str(p),4000,4000)

    def test_feature_extraction_uses_native_pixels(self):
        from src.block3_feature_extractor import TopologicalFeatureExtractor
        import pandas as pd
        with tempfile.TemporaryDirectory() as work:
            root=Path(work);dataset=root/'images';labels=root/'labels';out=root/'features'
            (dataset/'native').mkdir(parents=True);(dataset/'overview').mkdir();labels.mkdir()
            native=np.zeros((64,64),np.uint8);native[20:44,20:44]=100
            cv2.imwrite(str(dataset/'native/native_0001.png'),native)
            cv2.imwrite(str(dataset/'sample_tile_0001.png'),np.zeros((32,32),np.uint8))
            (labels/'sample_tile_0001.txt').write_text('0 0.25 0.25 0.75 0.25 0.75 0.75 0.25 0.75\n')
            rec=dict(filename='sample_tile_0001.png',native_filename='native/native_0001.png',transform=scale_metadata(64,64,32))
            (dataset/'overview/sample_tiles_coords.json').write_text(json.dumps(dict(schema_version=3,tiles=[rec])))
            TopologicalFeatureExtractor(str(dataset),str(labels),str(out),'sample').execute()
            rows=pd.read_csv(str(out/'sample_features.csv'))
            self.assertEqual(len(rows),1);self.assertEqual(rows.iloc[0]['Area'],576)
            self.assertEqual(rows.iloc[0]['Source_Pixels_Per_Output_Pixel'],2)
            self.assertEqual(rows.iloc[0]['Measurement_Space'],'source_pixels')

    def test_target_config_1500(self):
        namespace={}
        code=Path(config.__file__).read_text().replace('TARGET_SIZE = 2000','TARGET_SIZE = 1500')
        exec(compile(code,'config_1500','exec'),namespace)
        s=SmartSlicer(target_size=namespace['TARGET_SIZE'],margin_start=namespace['MARGIN_START'],margin_end=namespace['MARGIN_END'],dynamic_step=namespace['DYNAMIC_EXPANSION_STEP'],min_margin_limit=namespace['MIN_MARGIN_LIMIT'])
        self.assertEqual(s.target_size,1500);self.assertLess(s.max_step,1500)

if __name__=='__main__':unittest.main()
