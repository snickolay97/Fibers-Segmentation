"""Bounded object review and fast-classification Qt regression tests."""
import os
from pathlib import Path
import tempfile
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from src.desktop.qt import QtCore, QtGui, QtWidgets, BINDING
if BINDING == 'PySide6':
    from PySide6 import QtTest
else:
    from PyQt6 import QtTest

from src.desktop.i18n import get_language, set_language
from src.desktop.object_classifier import ObjectClassifier
from src.desktop.object_review import ObjectReviewGallery
from src.desktop.widgets import image_pool


class ObjectReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.old_language = get_language()
        set_language('en')
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            if isinstance(window, ObjectReviewGallery):
                window.dispose()
            window.close()
        image_pool().waitForDone(5000)
        self.app.processEvents()
        self.temporary.cleanup()
        set_language(self.old_language)

    def pump_until(self, predicate, timeout=4):
        until = time.monotonic()+timeout
        while time.monotonic() < until:
            self.app.processEvents()
            if predicate():
                return
            QtTest.QTest.qWait(5)
        self.fail('Timed out waiting for a bounded thumbnail')

    def rows(self, count=3):
        return [dict(Tile_Name='sample_tile_0001' if i<2 else 'sample_tile_0002',
                     Object_ID=str(i+1), Class_Name='Unknown', Class_ID='-1',
                     Area='80', Aspect_Ratio='3', Measurement_Space='source_pixels') for i in range(count)]

    def crop(self, row, size=(80,40)):
        folder=self.root/'results/verification_masks'/row['Tile_Name']
        folder.mkdir(parents=True,exist_ok=True)
        path=folder/('obj_{:03d}_Unknown.png'.format(int(row['Object_ID'])))
        image=QtGui.QImage(*size,QtGui.QImage.Format.Format_RGB32)
        image.fill(QtGui.QColor('#dfdfdf'))
        self.assertTrue(image.save(str(path)))
        return path

    def gallery(self, **kwargs):
        gallery=ObjectReviewGallery(**kwargs)
        self.windows.append(gallery)
        return gallery

    def test_gallery_filtering_selection_and_manual_updates_are_read_only(self):
        gallery=self.gallery(); rows=self.rows()
        originals=[dict(row) for row in rows]
        gallery.set_rows(rows,dict(results_dir=str(self.root/'results')))
        self.assertEqual(len(gallery.findChildren(QtWidgets.QLabel,'helpBadge')),3)
        self.assertTrue(gallery.tile_filter.toolTip())
        self.assertTrue(gallery.search.toolTip())
        gallery.select_object('sample_tile_0001',1)
        received=[]; gallery.row_selected.connect(received.append)
        gallery.unclassified_only.setChecked(True)
        gallery.set_manual_labels({'labels':{'sample_tile_0001/1':{
            'Manual_Class_ID':0,'Manual_Class':'particle','Reviewed':True}}})
        self.assertEqual(len(gallery.visible_rows),2)
        self.assertEqual(gallery.selected_row()['Object_ID'],'2')
        self.assertEqual(received[-1]['Object_ID'],'2')
        gallery.set_manual_labels({'labels':{
            'sample_tile_0001/1':{'Manual_Class_ID':0,'Manual_Class':'particle','Reviewed':True},
            'sample_tile_0001/2':{'Manual_Class_ID':1,'Manual_Class':'fiber','Reviewed':True}}})
        self.assertEqual(gallery.selected_row()['Object_ID'],'3')
        self.assertEqual(gallery.navigate('unlabeled')['Object_ID'],'3')
        gallery.set_filter_state(dict(tile='sample_tile_0001',search='fiber',unclassified=False))
        self.assertEqual(len(gallery.visible_rows),1)
        gallery.select_object('sample_tile_0001',2)
        self.assertEqual(gallery.selected_row()['Manual_Class_ID'],1)
        self.assertEqual(rows,originals)
        state=gallery.filter_state(); gallery.retranslate('ru')
        self.assertEqual(gallery.filter_state(),state)
        self.assertEqual(gallery.unclassified_only.text(),'Только без класса')

    def test_cleared_labels_override_previous_row_overlay(self):
        gallery=self.gallery(); row=self.rows()[0]
        row.update(Manual_Class='fiber',Manual_Class_ID=1,Reviewed=True)
        gallery.set_rows([row],None)
        gallery.set_manual_labels({'labels':{}})
        gallery.unclassified_only.setChecked(True)
        self.assertEqual(len(gallery.visible_rows),1)
        gallery.select_object(row['Tile_Name'],row['Object_ID'])
        self.assertEqual(gallery.selected_row()['Manual_Class'],'')
        self.assertEqual(row['Manual_Class'],'fiber')

    def test_filtering_last_classified_object_emits_selection_cleared_once(self):
        gallery=self.gallery(); row=self.rows()[0]
        gallery.set_rows([row],None); gallery.select_object(row['Tile_Name'],row['Object_ID'])
        gallery.unclassified_only.setChecked(True)
        cleared=[]; gallery.selection_cleared.connect(lambda:cleared.append(True))
        gallery.set_manual_labels({'labels':{'sample_tile_0001/1':{
            'Manual_Class_ID':1,'Manual_Class':'fiber','Reviewed':True}}})
        self.assertEqual(cleared,[True])
        self.assertIsNone(gallery.selected_row())
        gallery.apply_filter(); self.assertEqual(cleared,[True])

    def test_real_thumbnail_is_bounded_and_source_is_unchanged(self):
        gallery=self.gallery(thumbnail_size=96); row=self.rows()[0]
        path=self.crop(row,(480,300)); before=path.read_bytes()
        gallery.set_rows([row],dict(results_dir=str(self.root/'results')))
        key='sample_tile_0001/1'
        gallery._model.data(gallery._model.index(0,0),QtCore.Qt.ItemDataRole.DecorationRole)
        self.pump_until(lambda:key in gallery._cache)
        icon,error=gallery._cache[key]
        self.assertFalse(error)
        self.assertTrue(icon.availableSizes())
        self.assertLessEqual(max(icon.availableSizes()[0].width(),icon.availableSizes()[0].height()),96)
        self.assertEqual(path.read_bytes(),before)

    def test_large_native_crop_is_not_decoded_for_contact_sheet(self):
        gallery=self.gallery(max_source_pixels=100); row=self.rows()[0]
        self.crop(row,(80,40))
        gallery.set_rows([row],dict(results_dir=str(self.root/'results')))
        gallery._model.data(gallery._model.index(0,0),QtCore.Qt.ItemDataRole.DecorationRole)
        key='sample_tile_0001/1'; self.pump_until(lambda:key in gallery._cache)
        self.assertEqual(gallery._cache[key][1],'large')
        tip=gallery._model.data(gallery._model.index(0,0),QtCore.Qt.ItemDataRole.ToolTipRole)
        self.assertIn('Large object',tip)

    def test_thousands_of_rows_use_lazy_pending_and_cache_limits(self):
        gallery=self.gallery(cache_limit=3); rows=self.rows(1000)
        for row in rows[:8]: self.crop(row)
        gallery.set_rows(rows,dict(results_dir=str(self.root/'results')))
        self.assertEqual(gallery._model.rowCount(),1000)
        self.assertFalse(gallery._cache)
        self.assertFalse(gallery._tasks)
        for i in range(20):
            gallery._model.data(gallery._model.index(i,0),QtCore.Qt.ItemDataRole.DecorationRole)
        self.assertLessEqual(len(gallery._tasks),8)
        self.pump_until(lambda:not gallery._tasks)
        self.assertLessEqual(len(gallery._cache),3)
        old=gallery._token
        gallery.dispose(); gallery.set_rows([],None)
        gallery._thumbnail_ready(old,'sample_tile_0001/1',QtGui.QImage(2,2,QtGui.QImage.Format.Format_RGB32),'')
        self.assertFalse(gallery._cache)
        self.assertEqual(gallery.visible_rows,[])

    def test_gallery_rejects_unsafe_object_identity(self):
        gallery=self.gallery()
        with self.assertRaises(ValueError):
            gallery.set_rows([dict(Tile_Name='../outside',Object_ID=1)],dict(results_dir=str(self.root)))

    def classifier_workspace(self):
        window=QtWidgets.QWidget(); self.windows.append(window)
        layout=QtWidgets.QVBoxLayout(window)
        classifier=ObjectClassifier(); layout.addWidget(classifier)
        anchor=QtWidgets.QPushButton('Review focus'); layout.addWidget(anchor)
        number=QtWidgets.QSpinBox(); layout.addWidget(number)
        search=QtWidgets.QLineEdit(); layout.addWidget(search)
        classifier.set_shortcut_scope(window)
        classifier.set_object(self.rows()[0],{'Manual_Class':'agglomeration','Manual_Class_ID':4,'Reviewed':True})
        classifier.set_progress(1,3)
        window.show(); window.activateWindow(); anchor.setFocus(); self.app.processEvents()
        return window,classifier,anchor,number,search

    def test_large_class_buttons_assign_then_next_and_highlight_saved_class(self):
        _window,classifier,_anchor,_number,_search=self.classifier_workspace()
        events=[]; classifier.apply_class.connect(lambda key,next_object:events.append((key,next_object)))
        keys=['particle','fiber','self_crossed_tube','crossed_tubes','agglomeration','adhered_objects']
        for number,key in enumerate(keys,1):
            button=classifier.class_buttons[key]
            self.assertTrue(button.text().startswith(str(number)))
            self.assertGreaterEqual(button.minimumHeight(),48)
            self.assertEqual(bool(button.property('assigned')),key=='agglomeration')
            button.click()
        self.assertEqual(events,[(key,True) for key in keys])
        classifier.set_enabled_current(False)
        self.assertFalse(classifier.class_buttons['particle'].isEnabled())

    def test_shortcuts_stay_scoped_and_preserve_number_and_search_inputs(self):
        _window,classifier,anchor,number,search=self.classifier_workspace()
        events=[]; moves=[]
        classifier.apply_class.connect(lambda key,next_object:events.append((key,next_object)))
        classifier.navigate.connect(moves.append)
        QtTest.QTest.keyClick(anchor,QtCore.Qt.Key.Key_1)
        self.assertEqual(events,[('particle',True)])
        QtTest.QTest.keyClick(anchor,QtCore.Qt.Key.Key_Right)
        QtTest.QTest.keyClick(anchor,QtCore.Qt.Key.Key_U)
        self.assertEqual(moves,['next','unlabeled'])
        search.setFocus(); self.app.processEvents(); QtTest.QTest.keyClicks(search,'26u')
        self.assertEqual(search.text(),'26u')
        number.setFocus(); number.selectAll(); self.app.processEvents(); QtTest.QTest.keyClicks(number,'3')
        self.assertEqual(number.value(),3)
        self.assertEqual(events,[('particle',True)])
        outside=QtWidgets.QPushButton('Other page'); self.windows.append(outside)
        outside.show(); outside.activateWindow(); outside.setFocus(); self.app.processEvents()
        QtTest.QTest.keyClick(outside,QtCore.Qt.Key.Key_4)
        self.assertEqual(events,[('particle',True)])

    def test_shortcuts_work_in_floating_review_dock(self):
        workspace=QtWidgets.QMainWindow(); self.windows.append(workspace)
        classifier=ObjectClassifier(); workspace.setCentralWidget(classifier)
        classifier.set_shortcut_scope(workspace); classifier.set_progress(0,1)
        classifier.set_object(self.rows()[0])
        dock=QtWidgets.QDockWidget('Object review',workspace)
        button=QtWidgets.QPushButton('Floating review'); dock.setWidget(button)
        workspace.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea,dock)
        workspace.show(); dock.setFloating(True); dock.show(); dock.activateWindow(); button.setFocus()
        self.app.processEvents(); QtTest.QTest.qWait(10); self.app.processEvents()
        events=[]; classifier.apply_class.connect(lambda key,next_object:events.append((key,next_object)))
        QtTest.QTest.keyClick(button,QtCore.Qt.Key.Key_2)
        self.assertEqual(events,[('fiber',True)])

    def test_dispose_releases_shortcuts_before_workspace_rebuild(self):
        window,classifier,anchor,_number,_search=self.classifier_workspace()
        received=[]; classifier.apply_class.connect(lambda *args:received.append(args))
        classifier.dispose(); classifier.dispose()
        self.assertFalse(classifier._shortcuts)
        anchor.setFocus(); self.app.processEvents()
        QtTest.QTest.keyClick(anchor,QtCore.Qt.Key.Key_1)
        self.assertFalse(received)
        self.windows.remove(window)
        window.deleteLater()
        self.app.sendPostedEvents(None,QtCore.QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_quick_classes_use_two_rows_at_review_panel_width(self):
        classifier=ObjectClassifier(); self.windows.append(classifier)
        classifier.resize(580,330); classifier.show(); self.app.processEvents()
        self.assertEqual(classifier._class_columns,3)
        for key,button in classifier.class_buttons.items():
            index=classifier.class_grid.indexOf(button)
            row,column,_row_span,_column_span=classifier.class_grid.getItemPosition(index)
            self.assertEqual((row,column),(list(classifier.class_buttons).index(key)//3,list(classifier.class_buttons).index(key)%3))
        self.assertLess(classifier.class_buttons['adhered_objects'].geometry().bottom(),250)
        classifier.resize(420,440); self.app.processEvents()
        self.assertEqual(classifier._class_columns,2)

    def test_contact_sheet_caption_and_selected_border_remain_visible(self):
        gallery=self.gallery(); gallery.resize(580,400)
        gallery.setStyleSheet('QAbstractItemView { background: white; color: #183336; selection-background-color: #167d70; }')
        gallery.set_rows(self.rows(),None)
        gallery.show(); gallery.select_object('sample_tile_0001',1); self.app.processEvents()
        index=gallery._model.index(0,0)
        rect=gallery.view.visualRect(index)
        self.assertIn(index,gallery.view.selectionModel().selectedIndexes())
        image=gallery.view.viewport().grab().toImage()
        card=rect.adjusted(4,4,-4,-4)
        for top,height in ((card.bottom()-43,22),(card.bottom()-20,18)):
            dark=sum(image.pixelColor(x,y).lightness()<120
                     for x in range(card.left()+12,card.right()-12)
                     for y in range(top,top+height))
            self.assertGreater(dark,15,'Object and tile captions must both be visible')
        selected=image.pixelColor(card.left(),card.top()+28)
        gallery.select_object('sample_tile_0001',2); self.app.processEvents()
        normal=gallery.view.viewport().grab().toImage().pixelColor(card.left(),card.top()+28)
        self.assertNotEqual(selected,normal,'Selected object must have a visible border')

    def test_selected_card_stays_visible_after_deferred_column_resize(self):
        gallery=self.gallery(); gallery.resize(650,360)
        rows=self.rows(48); gallery.set_rows(rows,None)
        gallery.show(); gallery.select_object(rows[17]['Tile_Name'],rows[17]['Object_ID'])
        self.app.processEvents(); QtTest.QTest.qWait(10)
        gallery.resize(1050,360)
        self.app.processEvents(); QtTest.QTest.qWait(10); self.app.processEvents()
        index=gallery._model.index(17,0)
        self.assertEqual(gallery.selected_row()['Object_ID'],'18')
        self.assertTrue(gallery.view.viewport().rect().contains(gallery.view.visualRect(index).center()))
        # Wheel/scrollbar browsing must stay free; only a new selection or
        # viewport size change schedules automatic scrolling to the card.
        gallery.view.verticalScrollBar().setValue(0)
        self.app.processEvents(); QtTest.QTest.qWait(10); self.app.processEvents()
        self.assertEqual(gallery.view.verticalScrollBar().value(),0)


if __name__=='__main__': unittest.main()
