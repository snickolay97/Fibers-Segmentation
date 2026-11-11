"""Renaming folders preserves measured objects and rolls back failed moves."""
import importlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from src.desktop import service
from src.desktop.project import Project
from src.desktop.storage_migration import migrate_storage_names


class StorageMigrationTests(unittest.TestCase):
    def setUp(self):
        fixture_module=importlib.import_module('test_project_service')
        self.fixture=fixture_module.ProjectServiceTests()
        self.fixture.setUp()
        self.project=self.fixture.project
        self.root=self.fixture.root
        self.dataset=self.fixture.prepared()
        service.extract(self.project,self.dataset['id'],labels_mode='auto')
        _fields,rows=service.read_results(self.dataset)
        self.assertTrue(rows)
        service.assign_object_class(self.project,self.dataset['id'],rows[0]['Tile_Name'],int(rows[0]['Object_ID']),'fiber')
        self.csv_bytes=Path(self.dataset['last_csv']).read_bytes()
        self.labels_bytes=(Path(self.dataset['results_dir'])/'manual_object_labels.json').read_bytes()
        # Build the exact old UUID-wrapper layout from a real, valid dataset.
        source=self.project.sources[0]
        old_source=Path(source['path'])
        new_source=self.root/'sources'/source['id']/old_source.name
        new_source.parent.mkdir()
        old_source.rename(new_source)
        source['path']=str(new_source)
        self.dataset['source_path']=str(new_source)
        self.dataset['source_signature']['path']=str(new_source)
        dataset_path=Path(self.dataset['path'])
        run=dataset_path.parent.parent
        legacy=self.root/'runs'/'20261029T225901-3e1a13bc'
        run.rename(legacy)
        wrapper=legacy/source['id'][:12]
        wrapper.mkdir()
        for path in list(legacy.iterdir()):
            if path != wrapper:
                path.rename(wrapper/path.name)
        self.dataset['path']=str(wrapper/'tiles'/dataset_path.name)
        measurement=Path(self.dataset['results_dir'])
        old_measurement=self.root/'measurements'/self.dataset['id']/('f'*32)
        old_measurement.parent.mkdir(parents=True)
        measurement.rename(old_measurement)
        self.dataset['results_dir']=str(old_measurement)
        self.dataset['last_csv']=str(old_measurement/Path(self.dataset['last_csv']).name)
        self.project._extra_fields['storage_layout_version']=1
        self.project.save()
        self.before=Path(self.project.path).read_bytes()

    def tearDown(self):
        self.fixture.tearDown()

    def test_scientific_bytes_manual_labels_and_reuse_survive_rename(self):
        result=migrate_storage_names(self.project)
        self.assertTrue(result['changed'])
        self.assertEqual((Path(result['backup'])/'project.json').read_bytes(),self.before)
        self.assertEqual(Path(self.project.sources[0]['path']).parent,self.root/'sources')
        self.assertTrue(service.results_are_current(self.dataset))
        self.assertEqual(Path(self.dataset['last_csv']).read_bytes(),self.csv_bytes)
        self.assertEqual((Path(self.dataset['results_dir'])/'manual_object_labels.json').read_bytes(),self.labels_bytes)
        self.assertEqual(service.get_object_labels(self.dataset)['assigned'],1)
        self.assertIn('Preparation_001',self.dataset['path'])
        self.assertNotIn(self.project.sources[0]['id'][:12],self.dataset['path'])
        self.assertEqual(service.prepare(self.project)['skipped'],1)
        self.assertFalse(migrate_storage_names(self.project)['changed'])
        self.assertEqual(Project.load(self.project.path).datasets[0]['id'],self.dataset['id'])

    def test_failed_move_rolls_back_without_rewriting_project(self):
        original=os.rename
        calls=[]
        def fail_second(a,b):
            calls.append((a,b))
            if len(calls)==2:raise PermissionError('simulated locked directory')
            return original(a,b)
        with patch('src.desktop.storage_migration.os.rename',side_effect=fail_second):
            with self.assertRaises(PermissionError):migrate_storage_names(self.project)
        self.assertEqual(Path(self.project.path).read_bytes(),self.before)
        self.assertTrue(Path(self.project.sources[0]['path']).is_file())
        self.assertTrue(Path(self.dataset['path']).is_dir())
        self.assertTrue(service.results_are_current(self.dataset))
