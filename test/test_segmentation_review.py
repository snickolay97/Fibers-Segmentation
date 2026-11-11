"""Corrected segmentation must preserve pixel evidence and old measurement versions."""
import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from src.app_settings import PipelineSettings, PipelineCancelled
from src.block2_slicer import SmartSlicer
from src.block3_feature_extractor import TopologicalFeatureExtractor
from src.desktop import service
from src.desktop.object_merging import merge_objects, undo_merge, exact_objects
from src.desktop.main_window import MainWindow
from src.desktop.project import Project
from src.desktop.qt import QtCore, QtWidgets
from src.desktop.widgets import image_pool


class SegmentationReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.project = Project.create(self.root/'project.json')
        self.project.settings = PipelineSettings(target_size=64,overview_size=100,min_sub_object_area=1,pixel_size_um=.5).to_dict()
        self.image = np.zeros((80,120),np.uint8)
        self.image[10:20,10:30]=200; self.image[10:20,45:65]=180; self.image[45:55,80:100]=160
        base = self.root/'dataset'
        SmartSlicer(settings=PipelineSettings.from_dict(self.project.settings)).slice(
            self.image,self.image,np.ones_like(self.image),'sample',base)
        self.dataset = dict(id='one',name='sample',path=str(base),labels_dir=None,reviewed=True,
                            results_current=False,settings=self.project.settings)
        self.project.datasets.append(self.dataset); self.project.active_dataset_id='one'; self.project.save()
        service.extract(self.project,'one',labels_mode='auto')
        self.fields,self.rows = service.read_results(self.dataset)
        self.tile = self.rows[0]['Tile_Name']
        self.old_signature = self.dataset['measurement_signature']
        self.old_dir = Path(self.dataset['results_dir'])

    def tearDown(self):
        if hasattr(self,'window'):
            self.window.close(); self.window.deleteLater()
        image_pool().waitForDone(10000); self.app.processEvents()
        self.temp.cleanup()

    def hashes(self,folder):
        return {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob('*') if p.is_file()}

    def test_union_recomputes_features_preserves_versions_and_unaffected_labels(self):
        self.assertEqual(len(self.rows),3)
        for row in self.rows:
            service.assign_object_class(self.project,'one',self.tile,int(row['Object_ID']),'fiber')
        original = self.hashes(self.old_dir); tiles = self.hashes(Path(self.dataset['path']))
        objects = exact_objects(self.dataset,self.tile,self.rows)
        ids = [int(o['row']['Object_ID']) for o in objects[:2]]
        unaffected = int(objects[2]['row']['Object_ID'])
        summary = merge_objects(self.project,'one',self.tile,ids,self.old_signature)
        self.assertTrue(service.results_are_current(self.dataset))
        fields,rows = service.read_results(self.dataset); self.assertEqual(len(rows),2)
        merged = next(r for r in rows if int(r['Object_ID']) == summary['object_id'])
        self.assertEqual(float(merged['Area']),400)
        self.assertEqual(float(merged['Area_um2']),100)
        self.assertEqual(float(merged['Euler_Number']),2)  # No synthetic bridge.
        self.assertLess(float(merged['Solidity']),1)
        self.assertEqual(self.hashes(self.old_dir),original)
        self.assertEqual(self.hashes(Path(self.dataset['path'])),tiles)
        report = service.get_object_labels(self.dataset)
        self.assertEqual(set(report['labels']),{f'{self.tile}/{unaffected}'})
        self.assertNotIn(f"{self.tile}/{summary['object_id']}",report['labels'])
        located = exact_objects(self.dataset,self.tile,rows)
        self.assertEqual(len(located),2)
        union = next(o for o in located if int(o['row']['Object_ID']) == summary['object_id'])
        self.assertEqual(np.count_nonzero(union['mask']),400)
        self.assertAlmostEqual(float(merged['Aspect_Ratio']),TopologicalFeatureExtractor._extract_geometry(union['mask'])['Aspect_Ratio'])
        new_dir = Path(self.dataset['results_dir']); new_hash = self.hashes(new_dir)
        undo_merge(self.project,'one',self.dataset['measurement_signature'])
        self.assertEqual(Path(self.dataset['results_dir']),self.old_dir)
        self.assertTrue(service.results_are_current(self.dataset))
        self.assertEqual(service.get_object_labels(self.dataset)['assigned'],3)
        self.assertEqual(self.hashes(new_dir),new_hash)

    def test_stale_missing_and_cancelled_merges_do_not_publish(self):
        before = dict(self.dataset)
        ids = [int(r['Object_ID']) for r in self.rows[:2]]
        with self.assertRaises(ValueError): merge_objects(self.project,'one',self.tile,ids,'wrong')
        with self.assertRaises(ValueError): merge_objects(self.project,'one',self.tile,[ids[0]],self.old_signature)
        with self.assertRaises(PipelineCancelled):
            merge_objects(self.project,'one',self.tile,ids,self.old_signature,cancelled=lambda:True)
        checks = []
        def cancel_copy():
            checks.append(True)
            return len(checks) > 3
        with self.assertRaises(PipelineCancelled):
            merge_objects(self.project,'one',self.tile,ids,self.old_signature,cancelled=cancel_copy)
        self.assertEqual(self.dataset,before)
        self.assertEqual([p.name for p in self.old_dir.parent.iterdir()],['Measurement_001'])
        (self.old_dir/'verification_masks/object_locations.json').unlink()
        with self.assertRaisesRegex(ValueError,'Recalculate'):
            merge_objects(self.project,'one',self.tile,ids,self.old_signature)
        self.assertEqual(self.dataset,before)

    def test_overlapping_masks_count_pixels_once_and_keep_six_predictors(self):
        labels = self.root/'labels'; labels.mkdir()
        polygons = [(8,8,32,22),(20,8,42,22)]
        lines = []
        for x0,y0,x1,y1 in polygons:
            values = [x0,y0,x1,y0,x1,y1,x0,y1]
            lines.append('0 '+' '.join(str(v/120) for v in values))
        (labels/(self.tile+'.txt')).write_text('\n'.join(lines),encoding='utf8')
        self.dataset['labels_dir'] = str(labels)
        service.extract(self.project,'one',labels_mode='annotations_only')
        fields,rows = service.read_results(self.dataset)
        self.assertEqual(len(rows),2)
        total = sum(float(r['Area']) for r in rows)
        summary = merge_objects(self.project,'one',self.tile,[int(r['Object_ID']) for r in rows],self.dataset['measurement_signature'])
        fields,rows = service.read_results(self.dataset)
        self.assertEqual(len(rows),1)
        self.assertEqual(float(rows[0]['Area']),200)
        self.assertLess(float(rows[0]['Area']),total)
        self.assertEqual(float(rows[0]['Euler_Number']),1)
        from src.desktop.object_labels import RF_PREDICTORS
        self.assertEqual(len(RF_PREDICTORS),6)
        self.assertTrue(all(np.isfinite(float(rows[0][f])) for f in RF_PREDICTORS))

    def test_page_order_exact_selection_and_final_charts(self):
        preferences = QtCore.QSettings(str(self.root/'prefs.ini'),QtCore.QSettings.Format.IniFormat)
        self.window = MainWindow(self.project,language='en',preferences=preferences)
        self.window.show(); self.window.sidebar.setCurrentRow(3)
        review = self.window.segmentation_review
        until = time.monotonic()+8
        while time.monotonic() < until and (len(review._objects)!=3 or review.objects_view._pixmap_item is None):
            self.app.processEvents(); time.sleep(.01)
        self.assertEqual(len(review._objects),3)
        self.assertEqual(self.window.pages.count(),7)
        self.assertIn('Object labeling',self.window.sidebar.item(4).text())
        self.assertIn('Results',self.window.sidebar.item(6).text())
        self.assertEqual(review.objects_view.original_size,(120,80))
        review.tabs.setCurrentIndex(0)
        self.app.processEvents()
        self.assertTrue(review.native_view.isVisible())
        review.tabs.setCurrentIndex(2)
        self.app.processEvents()
        self.assertTrue(review.objects_view.isVisible())
        review.tabs.setCurrentIndex(3)
        self.app.processEvents()
        self.assertIn('No YOLO annotation file', review.polygons_status.text())
        from src.desktop.yolo_preview import show_yolo_polygons
        labels = self.root / 'preview_labels'
        labels.mkdir()
        txt = labels / (Path(review.record['filename']).stem + '.txt')
        context = dict(review.dataset, labels_dir=str(labels))
        for body, expected, count in (
            ('', 'Empty YOLO TXT', 0),
            ('0 .1 .2 .3 .4 .5 .6', 'Imported YOLO outlines: 1', 1),
            ('0 nan .2 .3 .4 .5 .6', 'Cannot display YOLO annotations', 0),
        ):
            txt.write_text(body, encoding='utf8')
            show_yolo_polygons(review.polygons_view, review.polygons_status, context, review.record)
            self.assertIn(expected, review.polygons_status.text())
            self.assertEqual(len(review.polygons_view._polygons), count)
        review.tabs.setCurrentIndex(review.tabs.count() - 1)
        self.app.processEvents()
        self.assertTrue(review.native_view.isVisible())
        self.assertTrue(review.objects_view.isVisible())
        self.assertTrue(review.comparison.isAncestorOf(review.native_view))
        self.assertTrue(review.comparison.isAncestorOf(review.objects_view))
        review.tabs.setCurrentIndex(2)
        self.app.processEvents()
        self.assertFalse(review.comparison.isAncestorOf(review.objects_view))
        self.assertTrue(review.objects_view.isVisible())
        for obj in review._objects[:2]:
            ys,xs=np.nonzero(obj['mask']); x,y=obj['origin']
            review._clicked(x+int(xs[0]),y+int(ys[0]))
        self.assertEqual(len(review.selected_ids()),2)
        self.assertTrue(review.merge_button.isEnabled())
        review.merge_requested.disconnect(self.window.merge_segmented_objects)
        emitted=[]; review.merge_requested.connect(lambda *args:emitted.append(args)); review.merge_button.click()
        self.assertEqual(len(emitted),1)
        self.window.sidebar.setCurrentRow(6); self.app.processEvents()
        self.assertIsNotNone(self.window.analytics._plot)
        self.assertEqual(len(self.window.analytics.table.rows),3)

    def test_mask_result_keeps_the_base_frame_and_reloads_overlays(self):
        preferences = QtCore.QSettings(str(self.root/'prefs.ini'), QtCore.QSettings.Format.IniFormat)
        self.window = MainWindow(self.project, language='en', preferences=preferences)
        self.window.show()
        self.window.sidebar.setCurrentRow(3)
        review = self.window.segmentation_review
        image_pool().waitForDone(10000)
        self.app.processEvents()
        frame = review.objects_view._pixmap_item
        self.assertIsNotNone(frame)
        ids = [int(row['Object_ID']) for row in self.rows[:2]]
        self.window.merge_segmented_objects(self.tile, ids, self.old_signature)
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline and (self.window.process is not None or len(review._objects) != 2):
            self.app.processEvents()
            time.sleep(.01)
        self.assertIsNone(self.window.process, self.window.log.toPlainText())
        self.assertIsNone(self.window._job_error, self.window.log.toPlainText())
        summary = self.window._job_result['summary']
        self.assertIs(review.objects_view._pixmap_item, frame)
        self.assertEqual(len(review._objects), 2)
        self.assertEqual(review.selected_ids(), [summary['object_id']])


if __name__=='__main__': unittest.main()
