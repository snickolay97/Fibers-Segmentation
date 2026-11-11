import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import tifffile

from src.app_settings import PipelineSettings, PipelineCancelled
from src.default_settings import STRAIGHT_SHIFT_FIELDS
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
        for key in ('search_window_end', *STRAIGHT_SHIFT_FIELDS):
            dataset['settings'].pop(key)
        dataset['preparation_key'] = service.fingerprint(dict(
            source=dataset['source_signature'], settings=dataset['settings']))
        second = service.prepare(self.project)
        self.assertEqual(second['skipped'], 1)
        self.assertEqual(len(self.project.datasets), 1)
        self.project.settings.update(search_window_end=115, straight_shift_left=13, straight_shift_right=13)
        third = service.prepare(self.project)
        self.assertEqual(third['processed'], 1)
        self.assertNotEqual(dataset['id'], third['datasets'][0])
        self.assertTrue(Path(dataset['path']).is_dir())
        changed = self.project.get_dataset(third['datasets'][0])
        manifest = service.dataset_manifest(changed)
        self.assertEqual(manifest['parameters']['straight_shift_left'], 13)
        self.assertFalse(manifest['parameters']['straight_shift_left_automatic'])
        self.assertEqual(manifest['parameters']['straight_shift_right'], 13)
        self.assertEqual(manifest['parameters']['margin_end'], 115)
        self.assertEqual(manifest['run_info']['settings']['search_window_end'], 115)

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
        owned = Path(connected['path'])
        self.assertNotEqual(owned, renamed)
        rec = service.tile_records(connected)[0]
        self.assertEqual(service.exclusion(self.project, connected['id'], [rec['id']])['count'], 1)
        self.assertTrue((owned/'excluded_tiles'/rec['filename']).is_file())
        self.assertTrue((renamed/rec['filename']).is_file())
        self.assertEqual(service.exclusion(self.project, connected['id'], [rec['id']], excluded=False)['count'], 1)
        self.assertTrue((owned/rec['filename']).is_file())

    def test_new_projects_have_distinct_owned_directories(self):
        one = Project.create(self.root / 'experiment_one.json')
        two = Project.create(self.root / 'experiment_two.json')
        self.assertEqual(Path(one.path), self.root / 'experiment_one' / 'project.json')
        self.assertEqual(Path(two.path), self.root / 'experiment_two' / 'project.json')
        self.assertNotEqual(one.workspace, two.workspace)
        self.assertEqual(Project.load(one.path).workspace, one.workspace)
        with self.assertRaises(FileExistsError):
            Project.create(self.root / 'experiment_one.json')

    def test_source_is_an_exact_owned_copy_and_duplicate_import_is_skipped(self):
        source = self.source()
        original = Path(source['original_path'])
        owned = Path(source['path'])
        self.assertEqual(owned.read_bytes(), original.read_bytes())
        self.assertIn(Path(self.project.workspace) / 'sources', owned.parents)
        self.assertEqual(service.add_sources(self.project, [original, owned]), [])
        before = owned.read_bytes()
        original.write_bytes(b'changed original')
        self.assertEqual(owned.read_bytes(), before)

    def test_imported_dataset_isolated_from_another_project_and_reused(self):
        original = self.prepared()
        other = Project.create(self.root / 'second.json')
        connected = service.connect_dataset(other, original['path'])['dataset']
        self.assertIn(Path(other.workspace), Path(connected['path']).parents)
        rec = service.tile_records(connected)[0]
        service.exclusion(other, connected['id'], [rec['id']])
        self.assertTrue((Path(original['path']) / rec['filename']).is_file())
        again = service.connect_dataset(other, original['path'])
        self.assertTrue(again['reused'])
        self.assertEqual(len(other.datasets), 1)

    def test_cancelled_source_copy_does_not_publish_partial_file(self):
        image = np.zeros((30, 40), np.uint8)
        source = self.root / 'cancelled.tif'
        tifffile.imwrite(source, image)
        calls = 0

        def cancelled():
            nonlocal calls
            calls += 1
            return calls >= 2

        with self.assertRaises(PipelineCancelled):
            service.add_sources(self.project, [source], cancelled=cancelled)
        self.assertEqual(self.project.sources, [])
        self.assertEqual(Project.load(self.project.path).sources, [])
        self.assertEqual(list((Path(self.project.workspace) / 'sources').iterdir()), [])

    def test_cancelled_dataset_import_keeps_external_data_and_project_unchanged(self):
        original = self.prepared()
        other = Project.create(self.root / 'cancelled_project.json')
        calls = 0

        def cancelled():
            nonlocal calls
            calls += 1
            return calls >= 3

        with self.assertRaises(PipelineCancelled):
            service.connect_dataset(other, original['path'], cancelled=cancelled)
        self.assertEqual(other.datasets, [])
        self.assertEqual(Project.load(other.path).datasets, [])
        self.assertEqual(list((Path(other.workspace) / 'datasets').iterdir()), [])
        self.assertTrue(Path(original['path']).is_dir())

    def test_full_resolution_overview_reconstructs_source_dimensions(self):
        dataset = self.prepared()
        result = service.overview(self.project, dataset['id'], full_resolution=True)
        height, width = service.dataset_manifest(dataset)['image_shape']
        self.assertEqual(cv2.imread(result['path']).shape[:2], (height, width))
        self.assertTrue(result['full_resolution'])

    def test_cancel_does_not_create_published_dataset(self):
        self.source()
        with self.assertRaises(PipelineCancelled):
            service.prepare(self.project, cancelled=lambda: True)
        self.assertEqual(self.project.datasets, [])


if __name__ == '__main__':
    unittest.main()
