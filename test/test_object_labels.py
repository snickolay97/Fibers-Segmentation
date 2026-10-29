import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src.desktop.project import Project, atomic_json
from src.desktop import service
from src.desktop.object_labels import (CANONICAL_MANUAL_CLASSES, LABELS_FILENAME,
                                       object_key, validate_export_destination)


class ObjectLabelsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.project = Project.create(self.root/'project.json')
        self.base = self.root/'tiles'/'sample'
        (self.base/'overview').mkdir(parents=True)
        self.manifest = dict(schema_version=3,source_name='sample',image_shape=[4,4],
            tiles=[dict(id=1,filename='sample_tile_0001.png'),dict(id=2,filename='sample_tile_0002.png')])
        atomic_json(self.base/'overview/sample_tiles_coords.json',self.manifest)
        for record in self.manifest['tiles']:
            (self.base/record['filename']).write_bytes(b'fixture model file')
        self.dataset = dict(id='dataset-one',name='sample',path=str(self.base),labels_dir=None,
                            status='completed',results_current=True)
        self.project.datasets.append(self.dataset)
        self.fields = ['Large_Image','Tile_Name','Object_ID','Class_ID','Class_Name','Measurement_Space',
                       'Source_Pixels_Per_Output_Pixel','Area','Aspect_Ratio','Solidity','Euler_Number',
                       'Endpoints','Branch_Points','Area_um2']
        self.rows = []
        for tile, ident in [('sample_tile_0001',1),('sample_tile_0001',2),('sample_tile_0002',1)]:
            self.rows.append(dict(Large_Image='sample',Tile_Name=tile,Object_ID=ident,Class_ID=0,
                Class_Name='Sphere',Measurement_Space='source_pixels',Source_Pixels_Per_Output_Pixel=2,
                Area=100,Aspect_Ratio=3.5,Solidity=.9,Euler_Number=1,Endpoints=2,Branch_Points=0,Area_um2=16))
        self.new_measurement('first')

    def tearDown(self):
        self.temporary.cleanup()

    def new_measurement(self, version):
        output = self.root/'measurements'/self.dataset['id']/version
        output.mkdir(parents=True)
        path = output/'sample_features.csv'
        with path.open('w',newline='',encoding='utf-8') as handle:
            writer = csv.DictWriter(handle,fieldnames=self.fields)
            writer.writeheader(); writer.writerows(self.rows)
        provenance = dict(manifest_signature=service.fingerprint(self.manifest),
                          annotation_signature=service.content_signature(None),active_tile_ids=[1,2],version=version)
        atomic_json(output/'measurement_run.json',provenance)
        self.dataset.update(results_dir=str(output),last_csv=str(path),results_current=True,
                            measurement_signature=service.fingerprint(provenance))
        self.project.save()
        return output

    def assign(self, tile='sample_tile_0001', ident=1, key='fiber'):
        return service.assign_object_class(self.project,self.dataset['id'],tile,ident,key)

    def csv_rows(self, path):
        with Path(path).open(newline='',encoding='utf-8') as handle:
            reader=csv.DictReader(handle)
            return list(reader.fieldnames),list(reader)

    def test_canonical_classes_have_stable_ids_and_localization(self):
        self.assertEqual([(c['id'],c['key']) for c in CANONICAL_MANUAL_CLASSES],
                         [(0,'particle'),(1,'fiber'),(2,'self_crossed_tube'),(3,'crossed_tubes'),
                          (4,'agglomeration'),(5,'adhered_objects')])
        self.assertTrue(all(c['label_en'] and c['label_ru'] for c in CANONICAL_MANUAL_CLASSES))

    def test_assignment_survives_project_reload_and_preserves_measurements(self):
        source=Path(self.dataset['last_csv']); before=source.read_bytes()
        provenance=Path(self.dataset['results_dir'])/'measurement_run.json'
        provenance_before=provenance.read_bytes()
        report=self.assign(key='particle')
        self.assertEqual(report['assigned'],1)
        self.assertEqual(report['total'],3)
        restored=Project.load(self.project.path).get_dataset(self.dataset['id'])
        loaded=service.get_object_labels(restored)
        label=loaded['labels'][object_key('sample_tile_0001',1)]
        self.assertEqual(label['Manual_Class_ID'],0)
        self.assertEqual(label['Manual_Class'],'particle')
        self.assertIs(label['Reviewed'],True)
        self.assertEqual(loaded['class_counts']['particle'],1)
        self.assertEqual(source.read_bytes(),before)
        self.assertEqual(provenance.read_bytes(),provenance_before)

    def test_partial_training_export_contains_only_reviewed_targets(self):
        self.assign()
        destination=self.root/'training.csv'
        report=service.export_training_csv(self.dataset,destination)
        fields,rows=self.csv_rows(destination)
        self.assertEqual(report['rows'],1)
        self.assertEqual(rows[0]['Manual_Class_ID'],'1')
        self.assertEqual(rows[0]['Manual_Class'],'fiber')
        self.assertEqual(rows[0]['Reviewed'],'True')
        self.assertEqual(rows[0]['Dataset_ID'],'dataset-one')
        self.assertEqual(rows[0]['Measurement_Reference'],service.get_object_labels(self.dataset)['measurement_reference'])
        self.assertIn('Area_um2',report['predictors'])
        self.assertIn('Class_ID',fields)
        self.assertIn('Class_Name',fields)
        self.assertEqual(rows[0]['Class_ID'],'0')
        self.assertEqual(rows[0]['Class_Name'],'Sphere')
        self.assertNotIn('Class_ID',report['predictors'])
        self.assertNotIn('Class_Name',report['predictors'])
        self.assertEqual(rows[0]['Class_Catalog_Version'],'2')
        self.assertEqual(report['class_catalog_version'],2)
        self.assertNotIn('Object_ID',report['predictors'])
        self.assertNotIn('Source_Pixels_Per_Output_Pixel',report['predictors'])
        self.assertIn('Tile_Name',fields)
        self.assertEqual(report['target'],'Manual_Class_ID')

    def test_all_rows_export_marks_unassigned_without_invented_targets(self):
        self.assign()
        destination=self.root/'all.csv'
        report=service.export_training_csv(self.dataset,destination,only_labeled=False)
        fields,rows=self.csv_rows(destination)
        self.assertEqual(report['rows'],3)
        self.assertEqual([row['Reviewed'] for row in rows],['True','False','False'])
        self.assertEqual([row['Manual_Class_ID'] for row in rows],['1','',''])

    def test_change_and_remove_label_update_counts(self):
        self.assign()
        report=self.assign(key='agglomeration')
        self.assertEqual(report['previous_class'],'fiber')
        self.assertEqual(report['assigned'],1)
        self.assertEqual(report['class_counts']['agglomeration'],1)
        self.assertEqual(report['class_counts']['fiber'],0)
        report=self.assign(key=None)
        self.assertEqual(report['assigned'],0)
        self.assertEqual(report['labels'],{})
        destination=self.root/'empty.csv'
        exported=service.export_training_csv(self.dataset,destination)
        fields,rows=self.csv_rows(destination)
        self.assertEqual(exported['rows'],0)
        self.assertEqual(rows,[])
        self.assertIn('Manual_Class_ID',fields)

    def test_unknown_class_and_object_do_not_mutate_labels(self):
        report=self.assign()
        path=Path(report['path']); before=path.read_bytes()
        for tile,ident,key in [('sample_tile_0001',1,'agglomerate'),('sample_tile_0001',99,'fiber'),
                               ('../sample',1,'fiber'),('sample_tile_0001',True,'fiber')]:
            with self.assertRaises(ValueError):self.assign(tile,ident,key)
            self.assertEqual(path.read_bytes(),before)

    def test_stale_annotations_block_assign_and_export(self):
        self.assign()
        labels=self.root/'labels'; labels.mkdir()
        (labels/'sample_tile_0001.txt').write_text('new external annotation')
        self.dataset['labels_dir']=str(labels)
        self.assertFalse(service.get_object_labels(self.dataset)['current'])
        with self.assertRaises(ValueError):self.assign(key='particle')
        destination=self.root/'stale.csv'
        with self.assertRaises(ValueError):service.export_training_csv(self.dataset,destination)
        self.assertFalse(destination.exists())

    def test_external_tile_exclusion_blocks_assign_and_export(self):
        self.assign()
        (self.base/'excluded_tiles').mkdir()
        (self.base/'sample_tile_0001.png').rename(self.base/'excluded_tiles/sample_tile_0001.png')
        with self.assertRaises(ValueError):self.assign()
        with self.assertRaises(ValueError):service.export_training_csv(self.dataset,self.root/'stale.csv')

    def test_rerun_does_not_retarget_old_labels(self):
        old_report=self.assign(); old_path=Path(old_report['path']); before=old_path.read_bytes()
        self.new_measurement('second')
        new_report=service.get_object_labels(self.dataset)
        self.assertEqual(new_report['assigned'],0)
        self.assertNotEqual(new_report['measurement_reference'],old_report['measurement_reference'])
        self.assign(key='adhered_objects')
        self.assertEqual(old_path.read_bytes(),before)
        self.assertNotEqual(service.get_object_labels(self.dataset)['path'],str(old_path))

    def test_copied_labels_or_changed_feature_csv_are_not_retargeted(self):
        old_report=self.assign(); old_path=Path(old_report['path'])
        output=self.new_measurement('second')
        shutil.copy2(old_path,output/LABELS_FILENAME)
        with self.assertRaises(ValueError):service.get_object_labels(self.dataset)
        (output/LABELS_FILENAME).unlink()
        self.assign()
        source=Path(self.dataset['last_csv'])
        source.write_text(source.read_text().replace('100','999'))
        with self.assertRaises(ValueError):self.assign(key='particle')
        with self.assertRaises(ValueError):service.export_training_csv(self.dataset,self.root/'changed.csv')

    def test_training_export_cannot_overwrite_scientific_csv(self):
        self.assign()
        path=Path(self.dataset['last_csv']); before=path.read_bytes()
        with self.assertRaises(ValueError):service.export_training_csv(self.dataset,path)
        self.assertEqual(path.read_bytes(),before)
        self.new_measurement('second')
        self.assign()
        with self.assertRaises(ValueError):service.export_training_csv(self.dataset,path)
        self.assertEqual(path.read_bytes(),before)

    def test_no_measurement_report_is_empty_without_side_effects(self):
        report=service.get_object_labels(dict(id='new',path=str(self.base)))
        self.assertEqual(report['assigned'],0)
        self.assertEqual(report['labels'],{})
        self.assertEqual(len(report['classes']),6)
        self.assertIsNone(report['path'])

    def test_training_rejects_invalid_numeric_values_before_first_label(self):
        destination=self.root/'training.csv'
        destination.write_bytes(b'previous reviewed training data')
        original=destination.read_bytes()
        for index,value in enumerate(('nan','inf','not-a-number','')):
            self.new_measurement('invalid-numeric-'+str(index))
            source=Path(self.dataset['last_csv'])
            fields,rows=self.csv_rows(source)
            rows[0]['Area']=value
            with source.open('w',newline='',encoding='utf-8') as handle:
                writer=csv.DictWriter(handle,fieldnames=fields)
                writer.writeheader();writer.writerows(rows)
            self.assign()
            self.assertTrue(service.results_are_current(self.dataset))
            with self.assertRaises(ValueError):service.export_training_csv(self.dataset,destination)
            self.assertEqual(destination.read_bytes(),original)

    def test_training_requires_all_six_predictor_columns(self):
        self.fields.remove('Branch_Points')
        for row in self.rows:row.pop('Branch_Points')
        self.new_measurement('missing-predictor')
        self.assign()
        destination=self.root/'incomplete.csv'
        with self.assertRaises(ValueError):service.export_training_csv(self.dataset,destination)
        self.assertFalse(destination.exists())

    def test_optional_physical_area_must_be_finite(self):
        self.rows[0]['Area_um2']='nan'
        self.new_measurement('invalid-physical-area')
        self.assign()
        with self.assertRaises(ValueError):service.export_training_csv(self.dataset,self.root/'physical.csv')

    def test_numeric_validation_applies_to_selected_training_rows(self):
        self.rows[1]['Area']='nan'
        self.new_measurement('unreviewed-invalid-row')
        self.assign()
        report=service.export_training_csv(self.dataset,self.root/'reviewed.csv')
        self.assertEqual(report['rows'],1)
        with self.assertRaises(ValueError):
            service.export_training_csv(self.dataset,self.root/'all-invalid.csv',only_labeled=False)

    def test_full_export_preserves_old_measurement_artifacts_and_source_noop(self):
        report=self.assign()
        prior_csv=Path(self.dataset['last_csv']); prior=prior_csv.read_bytes()
        prior_labels=Path(report['path']); labels_before=prior_labels.read_bytes()
        prior_run=prior_csv.parent/'measurement_run.json'; run_before=prior_run.read_bytes()
        self.new_measurement('second')
        for destination,before in [(prior_csv,prior),(prior_labels,labels_before),(prior_run,run_before)]:
            with self.assertRaises(ValueError):service.export_csv(self.dataset,destination)
            self.assertEqual(destination.read_bytes(),before)
        source=Path(self.dataset['last_csv']); source_before=source.read_bytes()
        self.assertEqual(service.export_csv(self.dataset,source),str(source))
        self.assertEqual(source.read_bytes(),source_before)
        exported=self.root/'full-export.csv'
        self.assertEqual(service.export_csv(self.dataset,exported),str(exported))
        self.assertEqual(exported.read_bytes(),source_before)

    def test_shared_export_guard_supports_csv_widget_and_protects_masks(self):
        source=Path(self.dataset['last_csv'])
        minimal=dict(last_csv=str(source),results_dir=str(source.parent))
        with self.assertRaises(ValueError):validate_export_destination(minimal,source)
        old_masks=source.parent.parent/'old-version'/'verification_masks'/'tile'/'obj.png'
        with self.assertRaises(ValueError):validate_export_destination(minimal,old_masks)
        destination=self.root/'visible.csv'
        self.assertEqual(validate_export_destination(minimal,destination),destination)

    def test_legacy_catalog_migrates_by_semantic_key_without_readonly_write(self):
        report=self.assign(key='agglomeration')
        self.assign(ident=2,key='self_crossed_tube')
        path=Path(report['path'])
        legacy=json.loads(path.read_text())
        legacy['class_catalog_version']=1
        legacy['labels'][object_key('sample_tile_0001',1)]['Manual_Class_ID']=2
        legacy['labels'][object_key('sample_tile_0001',2)]['Manual_Class_ID']=4
        atomic_json(path,legacy)
        prior=path.read_bytes()
        loaded=service.get_object_labels(self.dataset)
        self.assertEqual(loaded['class_catalog_version'],2)
        self.assertEqual(loaded['labels'][object_key('sample_tile_0001',1)]['Manual_Class_ID'],4)
        self.assertEqual(loaded['labels'][object_key('sample_tile_0001',2)]['Manual_Class_ID'],2)
        self.assertEqual(path.read_bytes(),prior)
        destination=self.root/'legacy_training.csv'
        exported=service.export_training_csv(self.dataset,destination)
        fields,rows=self.csv_rows(destination)
        self.assertEqual([(r['Tile_Name'],r['Object_ID'],r['Manual_Class'],r['Manual_Class_ID']) for r in rows],
                         [('sample_tile_0001','1','agglomeration','4'),
                          ('sample_tile_0001','2','self_crossed_tube','2')])
        self.assertEqual([r['Class_Catalog_Version'] for r in rows],['2','2'])
        self.assertEqual(exported['class_catalog_version'],2)
        self.assertEqual(path.read_bytes(),prior)
        self.assign(tile='sample_tile_0002',ident=1,key='fiber')
        saved=json.loads(path.read_text())
        self.assertEqual(saved['class_catalog_version'],2)
        self.assertEqual(saved['labels'][object_key('sample_tile_0001',1)]['Manual_Class_ID'],4)
        self.assertEqual(saved['labels'][object_key('sample_tile_0001',2)]['Manual_Class_ID'],2)
        self.assertEqual(saved['migrated_from_class_catalog_version'],1)

    def test_legacy_catalog_rejects_mismatched_key_id_and_object_version(self):
        report=self.assign(key='agglomeration')
        path=Path(report['path'])
        legacy=json.loads(path.read_text()); legacy['class_catalog_version']=1
        # The old agglomeration ID was 2, not the new 4.
        atomic_json(path,legacy)
        with self.assertRaises(ValueError):service.get_object_labels(self.dataset)
        legacy['labels'][object_key('sample_tile_0001',1)]['Manual_Class_ID']=2
        atomic_json(path,legacy)
        self.new_measurement('legacy-wrong-version')
        copied=Path(self.dataset['results_dir'])/LABELS_FILENAME
        shutil.copy2(path,copied)
        before=copied.read_bytes()
        with self.assertRaises(ValueError):service.get_object_labels(self.dataset)
        with self.assertRaises(ValueError):service.export_training_csv(self.dataset,self.root/'wrong-version.csv')
        self.assertEqual(copied.read_bytes(),before)


if __name__=='__main__':unittest.main()
