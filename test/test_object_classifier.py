"""Actual Qt controls keep manual targets separate from scientific source data."""
import csv
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

try:
    from src.desktop.qt import QtCore, QtWidgets
    from src.desktop.i18n import set_language, get_language
    from src.desktop.object_classifier import ObjectClassifier
    from src.desktop.widgets import CsvTable, ImageViewer
    from src.desktop.object_labels import CANONICAL_MANUAL_CLASSES
    QT_AVAILABLE=True
except ImportError:
    QT_AVAILABLE=False


@unittest.skipUnless(QT_AVAILABLE, 'Qt binding is not installed')
class ClassifierWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.original_language=get_language()
        set_language('en')
        self.temporary=tempfile.TemporaryDirectory()
        self.folder=Path(self.temporary.name)
        self.widgets=[]

    def tearDown(self):
        for widget in self.widgets: widget.close()
        self.app.processEvents()
        self.temporary.cleanup()
        set_language(self.original_language)

    def widget(self,cls):
        widget=cls(); self.widgets.append(widget); return widget

    def csv_table(self):
        path=self.folder/'features.csv'
        fields=['Large_Image','Tile_Name','Object_ID','Class_ID','Class_Name',
                'Measurement_Space','Source_Pixels_Per_Output_Pixel','Area','Aspect_Ratio',
                'Solidity','Euler_Number','Endpoints','Branch_Points']
        rows=[dict(Tile_Name='sample_tile_0001',Object_ID=1,Class_ID=-1,Class_Name='Unknown',Area=80,Aspect_Ratio=3),
              dict(Tile_Name='sample_tile_0001',Object_ID=2,Class_ID=-1,Class_Name='Unknown',Area=50,Aspect_Ratio=1),
              dict(Tile_Name='sample_tile_0002',Object_ID=1,Class_ID=1,Class_Name='Curve',Area=110,Aspect_Ratio=4)]
        rows=[dict(Large_Image='sample',Measurement_Space='source_pixels',
                   Source_Pixels_Per_Output_Pixel=2,Solidity=.9,Euler_Number=1,
                   Endpoints=2,Branch_Points=0,**row) for row in rows]
        with path.open('w',encoding='utf-8-sig',newline='') as file:
            writer=csv.DictWriter(file,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
        table=self.widget(CsvTable); table.load_csv(path)
        return table,path

    def test_six_canonical_class_ids_survive_language_change(self):
        widget=self.widget(ObjectClassifier)
        self.assertEqual(widget.class_combo.count(),7)
        self.assertIsNone(widget.class_combo.itemData(0))
        expected={'particle':0,'fiber':1,'self_crossed_tube':2,'crossed_tubes':3,
                  'agglomeration':4,'adhered_objects':5}
        self.assertEqual([widget.class_combo.itemData(i) for i in range(1,7)],list(expected))
        for index,entry in enumerate(CANONICAL_MANUAL_CLASSES,1):
            self.assertEqual(entry['id'],expected[entry['key']])
            self.assertEqual(widget.class_combo.itemData(index,QtCore.Qt.ItemDataRole.UserRole+1),expected[entry['key']])
        widget.set_object({'Tile_Name':'tile','Object_ID':'1'},{'Manual_Class':'fiber','Manual_Class_ID':1,'Reviewed':True})
        widget.retranslate('ru')
        self.assertEqual(widget.class_combo.currentData(),'fiber')
        self.assertEqual(widget.class_combo.currentText(),'Волокно')
        self.assertEqual(widget.save_button.text(),'Сохранить класс')
        widget.retranslate('en')
        self.assertEqual(widget.class_combo.currentText(),'Fiber')

    def test_apply_save_next_clear_and_export_signals(self):
        widget=self.widget(ObjectClassifier); received=[]; exports=[]; navigation=[]
        widget.apply_class.connect(lambda key,next_object:received.append((key,next_object)))
        widget.export_requested.connect(lambda:exports.append(True))
        widget.navigate.connect(navigation.append)
        widget.set_progress(1,3)
        self.assertFalse(widget.save_button.isEnabled())
        widget.set_object({'Tile_Name':'tile','Object_ID':'2'})
        widget.class_combo.setCurrentIndex(widget.class_combo.findData('particle'))
        widget.save_button.click(); widget.save_next_button.click()
        widget.class_combo.setCurrentIndex(0); widget.save_button.click()
        self.assertEqual(received,[('particle',False),('particle',True),(None,False)])
        widget.export_button.click(); self.assertEqual(exports,[True])
        widget.previous_button.click(); widget.next_button.click(); widget.unlabeled_button.click()
        self.assertEqual(navigation,['previous','next','unlabeled'])

    def test_stale_results_disable_assignment_and_export(self):
        widget=self.widget(ObjectClassifier); received=[]
        widget.apply_class.connect(lambda *args:received.append(args))
        widget.set_object({'Tile_Name':'tile','Object_ID':'2'}); widget.set_progress(2,5)
        widget.set_enabled_current(False)
        self.assertFalse(widget.class_combo.isEnabled())
        self.assertFalse(widget.save_next_button.isEnabled())
        self.assertFalse(widget.export_button.isEnabled())
        widget.save_next_button.click()
        self.assertEqual(received,[])
        widget.set_enabled_current(True)
        self.assertTrue(widget.save_button.isEnabled())

    def test_manual_overlay_filter_and_navigation_preserve_source_csv(self):
        table,path=self.csv_table(); before=path.read_bytes()
        table.set_manual_labels({'labels':{
            'sample_tile_0001/1':{'Manual_Class_ID':1,'Manual_Class':'fiber','Reviewed':True},
            'sample_tile_0002/1':{'Manual_Class_ID':3,'Manual_Class':'crossed_tubes','Reviewed':True}}})
        position=table.headers.index('Object_ID')+1
        self.assertEqual(table.headers[position:position+3],['Manual_Class','Manual_Class_ID','Reviewed'])
        self.assertEqual([name for name in table.headers if name not in table.MANUAL_HEADERS],table._source_headers)
        self.assertTrue(table.select_object('sample_tile_0001','1'))
        self.assertEqual(table.navigate('unlabeled')['Object_ID'],'2')
        fiber=table.class_filter.findData(('manual','fiber'))
        self.assertGreaterEqual(fiber,0)
        table.class_filter.setCurrentIndex(fiber)
        self.assertEqual(len(table.visible_rows),1)
        self.assertEqual(table.visible_rows[0]['Class_Name'],'Unknown')
        self.assertEqual(table.visible_rows[0]['Class_ID'],'-1')
        table.class_filter.setCurrentIndex(table.class_filter.findData(('manual',None)))
        self.assertEqual([row['Object_ID'] for row in table.visible_rows],['2'])
        table.class_filter.setCurrentIndex(0); table.search.setText('sample_tile_0002')
        self.assertEqual(len(table.visible_rows),1)
        self.assertEqual(table.visible_rows[0]['Manual_Class'],'crossed_tubes')
        self.assertEqual(path.read_bytes(),before)

    def test_manual_change_keeps_selected_object_and_localized_search(self):
        table,_=self.csv_table()
        table.select_object('sample_tile_0001','1')
        table.set_manual_labels({'sample_tile_0001/1':{'Manual_Class_ID':0,'Manual_Class':'particle','Reviewed':True}})
        self.assertEqual(table.selected_row()['Object_ID'],'1')
        table.retranslate('ru'); table.search.setText('Частица')
        self.assertEqual(len(table.visible_rows),1)
        self.assertEqual(table.visible_rows[0]['Manual_Class_ID'],0)
        manual_column=table.headers.index('Manual_Class')
        self.assertEqual(table.table.item(0,manual_column).text(),'Частица')

    def test_visible_help_badges_and_translated_image_controls(self):
        classifier=self.widget(ObjectClassifier); table=self.widget(CsvTable); viewer=self.widget(ImageViewer)
        self.assertTrue(classifier.findChildren(QtWidgets.QLabel,'helpBadge'))
        self.assertEqual(len(table.findChildren(QtWidgets.QLabel,'helpBadge')),2)
        self.assertTrue(table.search.toolTip())
        self.assertTrue(table.class_filter.toolTip())
        viewer.retranslate('ru')
        self.assertEqual(viewer.fit_button.text(),'По размеру окна')
        self.assertEqual(viewer.caption.text(),'Выберите изображение для просмотра')
        viewer.retranslate('en')
        self.assertEqual(viewer.fit_button.text(),'Fit to window')

    def test_filtered_export_cannot_replace_scientific_source(self):
        table,path=self.csv_table(); before=path.read_bytes()
        table.set_manual_labels({'sample_tile_0001/1':{
            'Manual_Class_ID':1,'Manual_Class':'fiber','Reviewed':True}})
        table.search.setText('sample_tile_0001')
        with self.assertRaises(ValueError): table.export_filtered(path)
        self.assertEqual(path.read_bytes(),before)
        destination=self.folder/'filtered.csv'
        self.assertEqual(table.export_filtered(destination),2)
        with destination.open(encoding='utf-8-sig',newline='') as file:
            reader=csv.DictReader(file); rows=list(reader)
        self.assertEqual(rows[0]['Manual_Class'],'fiber')
        self.assertEqual(rows[0]['Class_Name'],'Unknown')
        self.assertEqual(rows[0]['Class_ID'],'-1')
        self.assertEqual(rows[0]['Manual_Class_ID'],'1')
        self.assertEqual(rows[0]['Measurement_Space'],'source_pixels')
        self.assertEqual(rows[0]['Source_Pixels_Per_Output_Pixel'],'2')
        self.assertEqual(path.read_bytes(),before)

    def test_failed_export_preserves_previous_destination(self):
        table,_=self.csv_table()
        destination=self.folder/'filtered.csv'; destination.write_bytes(b'previous export')
        with patch('src.desktop.widgets.csv.DictWriter',side_effect=OSError('Injected disk failure')):
            with self.assertRaises(OSError): table.export_filtered(destination)
        self.assertEqual(destination.read_bytes(),b'previous export')
        self.assertFalse(list(self.folder.glob('.csv_export_*')))


if __name__=='__main__': unittest.main()
