"""Manual connectivity changes must remain explicit, reversible and native-grid."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from src.desktop.mask_connection import MaskCorrection, component_count, endpoint_pairs
from src.desktop.mask_correction_dialog import MaskCorrectionDialog
from src.desktop.object_corrections import correction_context
from src.desktop.object_merging import exact_objects
from src.desktop import service
from src.desktop.project import Project
from src.desktop.qt import QtCore, QtWidgets, BINDING
if BINDING == 'PyQt6':
    from PyQt6 import QtTest
else:
    from PySide6 import QtTest
from src.desktop.widgets import image_pool
import test_segmentation_review as baseline


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.mask=np.zeros((80,120),bool)
        self.mask[37:44,10:31]=True; self.mask[37:44,85:106]=True
        self.gray=np.zeros(self.mask.shape,np.uint8)
        self.gray[self.mask]=210
        # A real-valued intensity ridge guides the route upward through the gap.
        self.gray[20:41,30:34]=200; self.gray[20:24,30:89]=200; self.gray[20:41,85:89]=200
        self.edit=MaskCorrection(self.mask,np.ones_like(self.mask),np.zeros_like(self.mask),self.gray)

    def test_route_follows_intensity_and_width_changes_only_bridge(self):
        first,last=[30,40],[85,40]
        op=self.edit.route(first,last,3,24)
        self.assertLess(min(p[1] for p in op['points']),30)
        self.edit.apply(op); self.edit.validate()
        self.assertEqual(component_count(self.edit.mask),1)
        self.assertTrue(np.all(self.edit.mask[self.mask]))
        self.assertTrue(np.array_equal(self.gray,self.edit.gray))
        thinner=MaskCorrection(self.mask,np.ones_like(self.mask),np.zeros_like(self.mask),self.gray)
        thinner.apply(dict(tool='bridge',points=op['points'],width=1))
        self.assertLess(np.count_nonzero(thinner.mask),np.count_nonzero(self.edit.mask))
        self.edit.undo(); np.testing.assert_array_equal(self.edit.mask,self.mask)

    def test_foreign_mask_and_padding_reject_swept_width(self):
        other=np.zeros_like(self.mask); other[42:47,50:60]=True
        model=MaskCorrection(self.mask,np.ones_like(self.mask),other,self.gray)
        op=model.route([30,40],[85,40],1,24,'straight')
        model.apply(op); model.validate()
        with self.assertRaises(ValueError): model.apply(dict(tool='paint',points=[[55,40]],width=7))
        valid=np.ones_like(self.mask); valid[:,57:59]=False
        blocked=MaskCorrection(self.mask,valid,np.zeros_like(self.mask),self.gray)
        with self.assertRaises(ValueError): blocked.route([30,40],[85,40],3,24,'straight')
        with self.assertRaises(ValueError): blocked.route([30,40],[85,40],3,24)

    def test_ends_are_from_distinct_components_and_replay_is_exact(self):
        ends,pairs=endpoint_pairs(self.mask)
        self.assertTrue(pairs)
        a,b=ends[pairs[0]['first']],ends[pairs[0]['last']]
        self.assertNotEqual(a['component'],b['component'])
        first,last=[a['x'],a['y']],[b['x'],b['y']]
        self.edit.apply(self.edit.route(first,last,3,12,'straight'))
        self.edit.apply(dict(tool='erase',points=[[15,37]],width=3))
        replay=MaskCorrection(self.mask,np.ones_like(self.mask),np.zeros_like(self.mask),self.gray)
        for op in json.loads(json.dumps(self.edit.operations)): replay.apply(op)
        np.testing.assert_array_equal(self.edit.mask,replay.mask)
        with self.assertRaises(ValueError): replay.apply(dict(tool='paint',points=[[-1,0]],width=3))
        with self.assertRaises(ValueError): replay.route(first,last,2,12)
        empty=MaskCorrection(self.mask,np.ones_like(self.mask),np.zeros_like(self.mask),self.gray)
        empty.apply(dict(tool='erase',points=[[15,37]],width=3))
        with self.assertRaises(ValueError): empty.validate()


class CorrectionVersionsTests(baseline.SegmentationReviewTests):
    def test_connected_correction_round_trip_statistics_and_undo(self):
        ids=[int(r['Object_ID']) for r in self.rows[:2]]
        context=correction_context(self.dataset,self.tile,ids,self.rows)
        ends,pairs=endpoint_pairs(context['model'].mask); pair=pairs[0]
        a,b=ends[pair['first']],ends[pair['last']]
        op=context['model'].route([a['x'],a['y']],[b['x'],b['y']],3,12,'straight')
        source_hash=self.hashes(Path(self.dataset['path'])); original=self.hashes(self.old_dir)
        for row in self.rows: service.assign_object_class(self.project,'one',self.tile,int(row['Object_ID']),'fiber')
        original=self.hashes(self.old_dir)
        summary=service.execute_action(self.project,dict(action='correct_objects',dataset_id='one',tile_name=self.tile,
            object_ids=ids,expected_signature=self.old_signature,operations=[op]))
        self.assertTrue(service.results_are_current(self.dataset))
        fields,rows=service.read_results(self.dataset)
        row=next(r for r in rows if int(r['Object_ID']) == summary['object_id'])
        self.assertEqual(float(row['Euler_Number']),1)
        self.assertGreater(float(row['Area']),400)
        self.assertEqual(float(row['Area_um2']),float(row['Area'])*.25)
        self.assertEqual(len(service.get_object_labels(self.dataset)['labels']),1)
        run=json.loads((Path(self.dataset['results_dir'])/'measurement_run.json').read_text())
        self.assertTrue(run['contains_manual_mask_edits'])
        self.assertGreater(run['merge']['added_pixels'],0)
        self.assertEqual(run['merge']['strokes'],[op])
        obj=next(o for o in exact_objects(self.dataset,self.tile,rows) if int(o['row']['Object_ID']) == summary['object_id'])
        self.assertIn('manual_added_mask',obj['entry'])
        self.project.save(); reopened=Project.load(self.project.path)
        self.assertTrue(service.results_are_current(reopened.get_dataset('one')))
        self.assertEqual(self.hashes(Path(self.dataset['path'])),source_hash)
        self.assertEqual(self.hashes(self.old_dir),original)
        service.execute_action(self.project,dict(action='undo_object_merge',dataset_id='one',expected_signature=self.dataset['measurement_signature']))
        self.assertEqual(self.dataset['results_dir'],str(self.old_dir))
        self.assertEqual(service.get_object_labels(self.dataset)['assigned'],3)

    def test_deletion_all_masks_and_nested_undo_preserve_previous_versions(self):
        source_hash=self.hashes(Path(self.dataset['path'])); old_hash=self.hashes(self.old_dir)
        ids=[int(r['Object_ID']) for r in self.rows]
        first=service.execute_action(self.project,dict(action='delete_objects',dataset_id='one',tile_name=self.tile,
            object_ids=[ids[0]],expected_signature=self.old_signature))
        first_dir=self.dataset['results_dir']; first_hash=self.hashes(Path(first_dir))
        self.assertEqual(first['deleted_count'],1); self.assertEqual(len(service.read_results(self.dataset)[1]),2)
        self.project.save()
        second=service.execute_action(self.project,dict(action='delete_objects',dataset_id='one',tile_name=self.tile,
            object_ids=ids[1:],expected_signature=self.dataset['measurement_signature']))
        self.assertEqual(second['objects'],0); self.assertEqual(service.read_results(self.dataset)[1],[])
        from src.desktop.main_window import MainWindow
        self.window=MainWindow(self.project,language='en',preferences=QtCore.QSettings(str(self.root/'empty.ini'),QtCore.QSettings.Format.IniFormat))
        self.window.show();self.window.sidebar.setCurrentRow(3);self.app.processEvents()
        self.assertTrue(self.window.segmentation_review.undo_button.isEnabled())
        self.assertEqual(self.window.analytics.table.rows,[])
        service.execute_action(self.project,dict(action='undo_object_merge',dataset_id='one',expected_signature=self.dataset['measurement_signature']))
        self.assertEqual(self.dataset['results_dir'],first_dir); self.assertEqual(self.hashes(Path(first_dir)),first_hash)
        service.execute_action(self.project,dict(action='undo_object_merge',dataset_id='one',expected_signature=self.dataset['measurement_signature']))
        self.assertEqual(self.dataset['results_dir'],str(self.old_dir))
        self.assertEqual(self.hashes(self.old_dir),old_hash); self.assertEqual(self.hashes(Path(self.dataset['path'])),source_hash)

    def test_ui_preview_and_accept_and_revision_protection(self):
        ids=[int(r['Object_ID']) for r in self.rows[:2]]
        dialog=MaskCorrectionDialog(self.dataset,self.tile,ids,self.rows)
        dialog.show()
        def wait():
            until=time.monotonic()+8
            while time.monotonic()<until and (dialog._task or dialog.viewer._pixmap_item is None):
                self.app.processEvents(); time.sleep(.01)
            self.assertIsNone(dialog._task)
        wait()
        self.assertTrue(dialog.find.isEnabled())
        dialog.method.setCurrentIndex(dialog.method.findData('straight'))
        dialog.find.click(); wait()
        self.assertIsNotNone(dialog._pending)
        self.assertFalse(dialog.save.isEnabled())
        dialog.add.click(); wait()
        self.assertEqual(component_count(dialog.model.mask),1)
        self.assertTrue(dialog.save.isEnabled())
        dialog.save.click(); wait()
        self.assertEqual(dialog.result(),QtWidgets.QDialog.DialogCode.Accepted)
        self.assertTrue(dialog.operations)
        with self.assertRaises(ValueError): service.execute_action(self.project,dict(action='correct_objects',dataset_id='one',
            tile_name=self.tile,object_ids=ids,expected_signature='stale',operations=dialog.operations))
        dialog.close(); dialog.deleteLater(); self.app.processEvents()

    def test_manual_additions_survive_further_union_and_invalid_inputs_do_not_publish(self):
        from src.desktop.object_merging import merge_objects
        from src.app_settings import PipelineCancelled
        ids=[int(r['Object_ID']) for r in self.rows[:2]]
        ctx=correction_context(self.dataset,self.tile,ids,self.rows)
        ends,pairs=endpoint_pairs(ctx['model'].mask);p=pairs[0];a,b=ends[p['first']],ends[p['last']]
        op=ctx['model'].route([a['x'],a['y']],[b['x'],b['y']],3,12,'straight')
        args=dict(action='correct_objects',dataset_id='one',tile_name=self.tile,object_ids=ids,expected_signature=self.old_signature,operations=[op])
        before=dict(self.dataset)
        with self.assertRaises(PipelineCancelled): service.execute_action(self.project,args,cancelled=lambda:True)
        self.assertEqual(self.dataset,before)
        invalid=dict(op,points=[[0,-1],[30,10]])
        with self.assertRaises(ValueError): service.execute_action(self.project,dict(args,operations=[invalid]))
        self.assertEqual(self.dataset,before)
        summary=service.execute_action(self.project,args)
        _,rows=service.read_results(self.dataset)
        corrected=next(o for o in exact_objects(self.dataset,self.tile,rows) if int(o['row']['Object_ID']) == summary['object_id'])
        added=int(corrected['manual_added'].sum());self.assertGreater(added,0)
        merged=merge_objects(self.project,'one',self.tile,[int(r['Object_ID']) for r in rows],self.dataset['measurement_signature'])
        _,rows=service.read_results(self.dataset);objects=exact_objects(self.dataset,self.tile,rows)
        self.assertEqual(int(objects[0]['manual_added'].sum()),added)
        self.assertEqual(int(objects[0]['row']['Object_ID']),merged['object_id'])

    def test_worker_deletes_masks_and_saves_reopenable_project(self):
        self.project.save()
        request=self.root/'delete_request.json'
        request.write_text(json.dumps(dict(project_path=self.project.path,action='delete_objects',language='ru',
            dataset_id='one',tile_name=self.tile,object_ids=[int(self.rows[0]['Object_ID'])],expected_signature=self.old_signature)),encoding='utf8')
        process=subprocess.run([sys.executable,'-B','-m','src.desktop.worker','--request',str(request)],
            capture_output=True,text=True,encoding='utf8',timeout=40)
        self.assertEqual(process.returncode,0,process.stdout+process.stderr)
        events=[json.loads(line) for line in process.stdout.splitlines() if line.startswith('{')]
        self.assertEqual(events[-1]['status'],'completed')
        reopened=Project.load(self.project.path); ds=reopened.get_dataset('one')
        self.assertEqual(len(service.read_results(ds)[1]),2)
        self.assertTrue(service.results_are_current(ds))

    def test_separate_mask_strokes_preserve_ids_and_publish_together(self):
        for row in self.rows:
            service.assign_object_class(self.project, 'one', self.tile, int(row['Object_ID']), 'fiber')
        original = self.hashes(self.old_dir)
        tiles = self.hashes(Path(self.dataset['path']))
        ids = [int(row['Object_ID']) for row in self.rows]
        model = correction_context(self.dataset, self.tile, ids, self.rows, keep_separate=True)['model']
        brush = dict(tool='paint', points=[[9, 15]], width=1, object_id=ids[2])
        erase = dict(tool='erase', points=[[10, 10], [64, 10]], width=1)
        multi_brush = dict(erase, tool='paint_touched', width=3)
        with self.assertRaisesRegex(ValueError, 'another object'):
            model.apply(dict(multi_brush, width=17))
        self.assertFalse(model.changed_ids())
        self.assertTrue(model.apply(multi_brush))
        self.assertEqual(model.validate(), ids[1:])
        self.assertFalse(model.mask[10, 37])  # The stroke skipped the gap.
        model.undo()
        with self.assertRaisesRegex(ValueError, 'another object'):
            model.apply(dict(brush, points=[[44, 9]]))
        self.assertTrue(model.apply(brush))
        self.assertTrue(model.apply(erase))
        self.assertEqual(model.validate(), ids[1:])
        model.undo()
        self.assertEqual(model.changed_ids(), ids[2:])
        model.apply(erase)

        request = dict(action='correct_objects', dataset_id='one', tile_name=self.tile, object_ids=ids,
                       expected_signature=self.old_signature, keep_separate=True, operations=model.operations)
        result = service.execute_action(self.project, request)
        self.assertEqual(result['changed_object_ids'], ids[1:])
        _, rows = service.read_results(self.dataset)
        self.assertEqual([int(row['Object_ID']) for row in rows], ids)
        self.assertEqual([float(row['Area']) for row in rows], [200, 180, 181])
        self.assertEqual([float(row['Area_um2']) for row in rows], [50, 45, 45.25])
        labels = service.get_object_labels(self.dataset)['labels']
        self.assertEqual(set(labels), {f'{self.tile}/{ids[0]}'})
        masks = exact_objects(self.dataset, self.tile, rows)
        self.assertEqual({int(obj['row']['Object_ID']): np.count_nonzero(obj['manual_added'])
                          for obj in masks}, dict(zip(ids, (0, 0, 1))))
        self.assertEqual(self.hashes(Path(self.dataset['path'])), tiles)
        self.assertEqual(self.hashes(self.old_dir), original)
        service.execute_action(self.project, dict(action='undo_object_merge', dataset_id='one',
                                                  expected_signature=self.dataset['measurement_signature']))
        self.assertEqual(service.get_object_labels(self.dataset)['assigned'], 3)

    def test_select_all_and_group_eraser_through_editor(self):
        from src.desktop.main_window import MainWindow
        self.window = MainWindow(self.project, language='en',
            preferences=QtCore.QSettings(str(self.root/'batch.ini'), QtCore.QSettings.Format.IniFormat))
        self.window.show()
        self.window.sidebar.setCurrentRow(3)
        review = self.window.segmentation_review
        until = time.monotonic()+8
        while not review.select_all_button.isEnabled() and time.monotonic() < until:
            self.app.processEvents(); time.sleep(.01)
        review.select_all_button.click()
        self.assertEqual(len(review.selected_ids()), 3)
        self.assertTrue(review.batch_edit_button.isEnabled())
        dialog = MaskCorrectionDialog(self.dataset, self.tile, review.selected_ids(), self.rows, keep_separate=True)
        dialog.show()
        try:
            until = time.monotonic()+8
            while time.monotonic() < until and (dialog._task or dialog.viewer._pixmap_item is None):
                self.app.processEvents(); time.sleep(.01)
            self.assertIsNone(dialog._task)
            self.assertFalse(dialog.find.isVisible())
            QtTest.QTest.keyClick(dialog, QtCore.Qt.Key.Key_E)
            self.assertEqual(dialog.tool.currentData(), 'erase')
            dialog.brush.setValue(1)
            first = dialog.viewer.view.mapFromScene(QtCore.QPointF(10.1, 10.1))
            last = dialog.viewer.view.mapFromScene(QtCore.QPointF(64.1, 10.1))
            viewport = dialog.viewer.view.viewport()
            QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos=first)
            QtTest.QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.LeftButton, pos=last)
            until = time.monotonic()+8
            while dialog._task and time.monotonic() < until:
                self.app.processEvents(); time.sleep(.01)
            self.assertEqual(len(dialog.model.changed_ids()), 2)
            self.assertTrue(dialog.save.isEnabled())

            QtTest.QTest.keyClick(dialog, QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
            until = time.monotonic()+8
            while dialog._task and time.monotonic() < until:
                self.app.processEvents(); time.sleep(.01)
            self.assertEqual(dialog.model.changed_ids(), [])
            QtTest.QTest.keyClick(dialog, QtCore.Qt.Key.Key_B)
            self.assertEqual(dialog.tool.currentData(), 'paint')
            dialog.paint_target.setCurrentIndex(dialog.paint_target.findData('touched'))
            dialog.brush.setValue(3)
            QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos=first)
            QtTest.QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.LeftButton, pos=last)
            until = time.monotonic()+8
            while dialog._task and time.monotonic() < until:
                self.app.processEvents(); time.sleep(.01)
            self.assertEqual(len(dialog.model.changed_ids()), 2)
            self.assertEqual(dialog.model.operations[0]['tool'], 'paint_touched')
        finally:
            dialog.close(); dialog.deleteLater(); self.app.processEvents()

    def test_brush_mouse_coordinates_help_and_localized_controls(self):
        from src.desktop.i18n import set_language,tr
        from src.desktop.help_center import HelpCenter, TOPICS
        from src.default_settings import MASK_EDITOR_DEFAULTS
        for lang in ('en','ru','he'):
            set_language(lang)
            dialog=MaskCorrectionDialog(self.dataset,self.tile,[int(self.rows[0]['Object_ID'])],self.rows)
            dialog.show()
            until=time.monotonic()+8
            while time.monotonic()<until and (dialog._task or dialog.viewer._pixmap_item is None):
                self.app.processEvents();time.sleep(.01)
            self.assertIsNone(dialog._task)
            self.assertFalse(dialog.find.isEnabled())  # Already connected selection.
            obj=next(o for o in exact_objects(self.dataset,self.tile,self.rows) if int(o['row']['Object_ID']) == int(self.rows[0]['Object_ID']))
            ys,xs=np.nonzero(obj['mask']);x,y=obj['origin']; point=[x+int(xs[len(xs)//2]),y+int(ys[len(ys)//2])]
            dialog.brush.setValue(1);dialog.tool.setCurrentIndex(dialog.tool.findData('erase'))
            h,w=dialog.model.mask.shape;bounds=dialog.viewer._pixmap_item.boundingRect()
            screen=dialog.viewer.view.mapFromScene(QtCore.QPointF(point[0]*bounds.width()/w+.1,point[1]*bounds.height()/h+.1))
            QtTest.QTest.mouseClick(dialog.viewer.view.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=screen)
            until=time.monotonic()+8
            while time.monotonic()<until and dialog._task:self.app.processEvents();time.sleep(.01)
            self.assertEqual(len(dialog.model.operations),1)
            self.assertEqual(int(dialog.model.original.sum()-dialog.model.mask.sum()),1)
            for key in ('find','add','save','cancel','tool','brush'):
                widget=getattr(dialog,key);origin=widget.mapTo(dialog,QtCore.QPoint(0,0))
                self.assertGreaterEqual(origin.x(),0,(lang,key));self.assertLessEqual(origin.x()+widget.width(),dialog.width(),(lang,key))
            if lang != 'en': self.assertNotEqual(dialog.cancel.text(),'Cancel')
            help_center=HelpCenter(language=lang)
            for key in ('mask_correction','delete_masks'):
                html=help_center._topic_html(key);self.assertIn(tr(TOPICS[key]['title'],language=lang),html)
            html=help_center._topic_html('mask_correction')
            self.assertIn(str(MASK_EDITOR_DEFAULTS['search_margin']),html)
            self.assertNotIn('{connection_width}',html)
            help_center.close();help_center.deleteLater();dialog.close();dialog.deleteLater();self.app.processEvents()
        set_language('en')


def load_tests(loader, tests, pattern):
    suite=unittest.TestSuite([loader.loadTestsFromTestCase(RoutingTests)])
    suite.addTests(CorrectionVersionsTests(name) for name in CorrectionVersionsTests.__dict__ if name.startswith('test_'))
    return suite


if __name__ == '__main__': unittest.main()
