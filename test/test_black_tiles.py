"""Exclude exact-zero native tiles without losing faint signal or user overrides."""
import hashlib
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import cv2
import numpy as np
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from src.app_settings import PipelineSettings,PipelineCancelled
from src.block2_slicer import SmartSlicer
from src.black_tiles import black_scan_needed,exclusion_state
from src.desktop import service
from src.desktop.main_window import MainWindow
from src.desktop.project import Project
from src.desktop.qt import QtCore,QtWidgets
from src.desktop.widgets import image_pool
from src.partition_geometry import checked_imwrite,validate_dataset
from src.tile_manager import TileManager


class BlackTileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.project=Project.create(self.root/'project.json')
        self.project.settings=PipelineSettings(target_size=64,overview_size=240,min_sub_object_area=1).to_dict()
        self.base=self.root/'datasets/sample'
        image=np.zeros((120,120),np.uint8)
        SmartSlicer(settings=PipelineSettings.from_dict(self.project.settings)).slice(image,image,np.ones_like(image),'sample',self.base)
        self.dataset=dict(id='one',name='sample',path=str(self.base),labels_dir=None,settings=self.project.settings,
                          results_current=False,reviewed=True)
        self.project.datasets.append(self.dataset);self.project.active_dataset_id='one';self.project.save()
        self.record=service.tile_records(self.dataset)[0]
        self.native=self.base/self.record['native_filename']
        self.valid=self.base/self.record['valid_mask']
        self.model=self.base/self.record['filename']

    def tearDown(self):
        if hasattr(self,'window'):
            if self.window.process is not None:
                self.window.process.kill();self.window.process.waitForFinished(5000)
            self.window.close();self.window.deleteLater()
        image_pool().waitForDone(10000);self.app.processEvents();self.temp.cleanup()

    def hashes(self,base):
        return {str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest() for p in base.rglob('*') if p.is_file()}

    def test_excludes_black_preserves_bytes_and_labels_map_and_retires_results(self):
        service.extract(self.project,'one',labels_mode='auto')
        csv=Path(self.dataset['last_csv']);old=csv.read_bytes()
        native,valid,model=self.native.read_bytes(),self.valid.read_bytes(),self.model.read_bytes()
        self.assertTrue(black_scan_needed(self.base))
        with patch('src.partition_geometry.cv2.putText',wraps=cv2.putText) as put:
            result=service.exclude_black_tiles(self.project,'one')
        self.assertEqual(result['count'],1)
        self.assertTrue(any(call.args[1]=='EXCLUDED' for call in put.call_args_list))
        self.assertFalse(self.model.exists())
        self.assertEqual((self.base/'excluded_tiles'/self.model.name).read_bytes(),model)
        self.assertEqual(self.native.read_bytes(),native);self.assertEqual(self.valid.read_bytes(),valid)
        self.assertEqual(csv.read_bytes(),old);self.assertFalse(self.dataset['results_current'])
        self.assertTrue(service.tile_records(self.dataset)[0]['excluded'])
        self.assertEqual(service.tile_records(self.dataset)[0]['exclusion_reason'],'black')
        self.assertFalse(black_scan_needed(self.base))
        validate_dataset(self.base,require_v3=True,check_pixels=True)

    def test_faint_native_signal_survives_a_black_model_and_16bit_is_not_shifted(self):
        image=np.zeros((120,120),np.uint8);image[57,59]=1
        checked_imwrite(self.native,image)
        self.assertFalse(cv2.imread(str(self.model),0).any())
        self.assertEqual(service.exclude_black_tiles(self.project,'one')['count'],0)
        self.assertTrue(self.model.is_file())
        image16=np.zeros((120,120),np.uint16);image16[57,59]=1
        checked_imwrite(self.native,image16)
        self.assertTrue(black_scan_needed(self.base))
        self.assertEqual(service.exclude_black_tiles(self.project,'one')['count'],0)
        self.assertTrue(self.model.is_file())

    def test_ignores_nonzero_padding_and_remembers_manual_restore(self):
        mask=np.zeros((120,120),np.uint8);mask[:60]=255
        image=np.zeros_like(mask);image[80,80]=200
        checked_imwrite(self.valid,mask);checked_imwrite(self.native,image)
        manager=TileManager(output_dir=self.base.parent)
        self.assertEqual(manager.exclude_black(self.base.name)['count'],1)
        self.assertEqual(manager.restore(self.base.name,[self.record['id']]),1)
        self.assertFalse(black_scan_needed(self.base))
        self.assertEqual(manager.exclude_black(self.base.name)['count'],0)
        self.assertTrue(self.model.exists())
        self.assertEqual(exclusion_state(self.base)['tiles'][str(self.record['id'])]['kind'],'restored')

    def test_import_copies_and_excludes_without_changing_external_dataset(self):
        before=self.hashes(self.base)
        other=Project.create(self.root/'private/project.json')
        other.settings=self.project.settings
        result=service.connect_dataset(other,self.base)
        imported=result['dataset'];record=service.tile_records(imported)[0]
        self.assertTrue(record['excluded']);self.assertEqual(record['exclusion_reason'],'black')
        self.assertEqual(self.hashes(self.base),before)

    def test_cancel_and_failed_state_publication_leave_model_active(self):
        manager=TileManager(output_dir=self.base.parent)
        with self.assertRaises(PipelineCancelled):manager.exclude_black(self.base.name,cancelled=lambda:True)
        self.assertTrue(self.model.exists())
        with patch('src.black_tiles.save_exclusion_state',side_effect=OSError('test write failure')):
            with self.assertRaises(OSError):manager.exclude_black(self.base.name)
        self.assertTrue(self.model.exists())
        self.assertFalse((self.base/'tile_exclusions.json').exists())

    def test_tiles_page_runs_background_check_and_shows_reason(self):
        prefs=QtCore.QSettings(str(self.root/'prefs.ini'),QtCore.QSettings.Format.IniFormat)
        self.window=MainWindow(self.project,language='en',preferences=prefs)
        self.window.show();self.window.sidebar.setCurrentRow(2)
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            self.app.processEvents();time.sleep(.01)
            if self.window.process is None and (self.base/'tile_exclusions.json').is_file():break
        self.assertIsNone(self.window.process,self.window.log.toPlainText())
        self.assertIn('excluded automatically',self.window.tile_list.item(0).text())
        self.assertTrue(self.window.check_black_button.toolTip())


if __name__=='__main__':unittest.main()
