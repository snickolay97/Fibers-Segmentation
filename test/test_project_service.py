import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import tifffile

from src.app_settings import PipelineSettings, PipelineCancelled
from src.desktop.project import Project
from src.desktop import service


class ProjectServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = Project.create(self.root / 'project.json', 'Test fibers')
        settings = PipelineSettings()
        settings.target_size = 128
        settings.overview_size = 200
        settings.tophat_radius = 8
        settings.bilateral_d = 3
        settings.bridge_kernel_size = 3
        settings.buffer_kernel_size = 3
        self.project.settings = settings.to_dict()
        self.project.save()

    def tearDown(self):
        self.temp.cleanup()

    def source(self):
        image = np.zeros((200, 240, 3), np.uint8)
        cv2.rectangle(image, (20, 20), (110, 27), (180, 0, 0), -1)
        cv2.circle(image, (170, 160), 9, (220, 0, 0), -1)
        path = self.root / 'source.tif'
        tifffile.imwrite(path, image, photometric='rgb')
        return service.add_sources(self.project, [path])[0]

    def prepared(self):
        source = self.source()
        result = service.prepare(self.project, [source['id']])
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual(result['processed'], 1)
        return self.project.get_dataset(result['datasets'][0])

    def test_project_roundtrip_and_interrupted_job(self):
        self.project.datasets.append(dict(id='one', status='running'))
        self.project.save()
        loaded = Project.load(self.project.path)
        self.assertTrue(loaded.recover_interrupted())
        self.assertEqual(Project.load(loaded.path).get_dataset('one')['status'], 'interrupted')
        self.assertEqual(loaded.name, 'Test fibers')

    def test_prepare_reuse_and_settings_new_version(self):
        dataset = self.prepared()
        second = service.prepare(self.project)
        self.assertEqual(second['skipped'], 1)
        self.assertEqual(len(self.project.datasets), 1)
        self.project.settings['gamma'] = 1.3
        third = service.prepare(self.project)
        self.assertEqual(third['processed'], 1)
        self.assertNotEqual(dataset['id'], third['datasets'][0])
        self.assertTrue(Path(dataset['path']).is_dir())

    def test_annotations_exclusion_and_fresh_empty_result(self):
        dataset = self.prepared()
        initial = service.extract(self.project, dataset['id'], labels_mode='auto')
        self.assertGreater(initial['objects'], 0)
        initial_csv = Path(dataset['last_csv'])
        labels = self.root / 'empty_labels'
        labels.mkdir()
        for rec in service.tile_records(dataset):
            (labels / (Path(rec['filename']).stem + '.txt')).write_text('')
        service.import_labels(self.project, dataset['id'], str(labels))
        self.assertIsNone(dataset['last_csv'])
        empty = service.extract(self.project, dataset['id'], labels_mode='require_annotations')
        self.assertEqual(empty['objects'], 0)
        columns, rows = service.read_results(dataset)
        self.assertIn('Aspect_Ratio', columns)
        self.assertEqual(rows, [])
        self.assertNotEqual(initial_csv, Path(dataset['last_csv']))
        self.assertTrue(initial_csv.is_file())
        rec = service.tile_records(dataset)[0]
        service.exclusion(self.project, dataset['id'], [rec['id']])
        self.assertTrue(service.tile_records(dataset)[0]['excluded'])
        self.assertFalse(dataset['results_current'])
        service.exclusion(self.project, dataset['id'], [rec['id']], excluded=False)
        self.assertFalse(service.tile_records(dataset)[0]['excluded'])

    def test_invalid_annotation_does_not_replace_import(self):
        dataset = self.prepared()
        labels = self.root / 'bad'
        labels.mkdir()
        rec = service.tile_records(dataset)[0]
        (labels / (Path(rec['filename']).stem + '.txt')).write_text('1 0.5 0.5 0.1 0.2\n')
        with self.assertRaises(ValueError):
            service.import_labels(self.project, dataset['id'], str(labels))
        self.assertIsNone(dataset['labels_dir'])

    def test_external_annotation_change_invalidates_table(self):
        dataset = self.prepared()
        labels = self.root/'valid_labels'
        labels.mkdir()
        for rec in service.tile_records(dataset):
            (labels/(Path(rec['filename']).stem+'.txt')).write_text('1 0 0 1 0 1 1 0 1\n')
        service.import_labels(self.project, dataset['id'], str(labels))
        service.extract(self.project, dataset['id'], labels_mode='require_annotations')
        self.assertTrue(service.results_are_current(dataset))
        next(Path(dataset['labels_dir']).glob('*.txt')).write_text('')
        self.assertFalse(service.results_are_current(dataset))
        self.assertEqual(service.read_results(dataset), ([], []))
        with self.assertRaises(ValueError):
            service.export_csv(dataset, self.root/'export.csv')

    def test_renamed_import_uses_manifest_filenames(self):
        original = self.prepared()
        renamed = Path(original['path']).with_name('renamed_folder')
        Path(original['path']).rename(renamed)
        connected = service.connect_dataset(self.project, renamed)['dataset']
        rec = service.tile_records(connected)[0]
        self.assertEqual(service.exclusion(self.project, connected['id'], [rec['id']])['count'], 1)
        self.assertTrue((renamed/'excluded_tiles'/rec['filename']).is_file())
        self.assertEqual(service.exclusion(self.project, connected['id'], [rec['id']], excluded=False)['count'], 1)
        self.assertTrue((renamed/rec['filename']).is_file())

    def test_cancel_does_not_create_published_dataset(self):
        self.source()
        with self.assertRaises(PipelineCancelled):
            service.prepare(self.project, cancelled=lambda: True)
        self.assertEqual(self.project.datasets, [])


if __name__ == '__main__':
    unittest.main()
