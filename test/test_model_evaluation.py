import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.desktop import service
from src.desktop.i18n import get_language, set_language
from src.desktop.model_evaluation import plan_split
from src.desktop.model_training_input import read_training_rows
from src.desktop.object_labels import RF_PREDICTORS
from src.desktop.project import Project, atomic_json


class ModelEvaluationTests(unittest.TestCase):
    def setUp(self):
        # These tests match English error text. UI tests may leave Hebrew active.
        self.addCleanup(set_language, get_language())
        set_language('en')
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = Project.create(self.root / 'project.json')
        self.request = dict(action='model_evaluation', dataset_ids=[], groups={}, area='Area',
                            seed=42, folds=2, forest_tree_count=11, preview=True)

    def add_dataset(self, number, *, tiff_bytes=None, empty_tile=False, calibrated=False):
        ident = f'dataset-{number}'
        source = self.root / f'source-{number}.tif'
        source.write_bytes(tiff_bytes if tiff_bytes is not None else ident.encode())
        tiles = self.root / ident
        output = self.root / 'measurements' / ident
        output.mkdir(parents=True)
        manifest = dict(schema_version=3, source_name=ident, image_shape=[4, 4],
                        tiles=[dict(id=1, filename='tile.png')])
        if empty_tile:
            manifest['tiles'].append(dict(id=2, filename='empty.png'))
        atomic_json(tiles / 'overview' / f'{ident}_tiles_coords.json', manifest)
        for tile in manifest['tiles']:
            (tiles / tile['filename']).touch()
        provenance = dict(manifest_signature=service.fingerprint(manifest),
                          annotation_signature=service.content_signature(None),
                          active_tile_ids=[tile['id'] for tile in manifest['tiles']])
        atomic_json(output / 'measurement_run.json', provenance)
        table = output / 'features.csv'
        with table.open('w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(('Tile_Name', 'Object_ID', *RF_PREDICTORS, *(['Area_um2'] if calibrated else [])))
            for obj in range(1, 5):
                area_um2 = [(8 + obj) * .25**2] if calibrated else []
                writer.writerow(('tile', obj, 8 + obj, 1 + 3 * (obj % 2), .9, 1, 2, 0, *area_um2))
        dataset = dict(id=ident, name=ident, path=str(tiles), source_id=f'source-{number}',
                       source_path=str(source), status='completed', results_dir=str(output),
                       last_csv=str(table), results_current=True,
                       measurement_signature=service.fingerprint(provenance))
        self.project.datasets.append(dataset)
        self.request['dataset_ids'].append(ident)
        for obj in range(1, 5):
            service.assign_object_class(self.project, ident, 'tile', obj, 'fiber' if obj % 2 else 'particle')
        self.project.save()
        return ident

    def test_grouped_holdout_and_cv_are_disjoint_and_worker_saves_snapshot(self):
        for i in range(5):
            self.add_dataset(i)
        preview = service.execute_action(self.project, self.request)
        plan_file = json.loads(Path(preview['path']).read_text(encoding='utf-8'))
        self.assertEqual(plan_file['plan_error'], '')
        with self.assertRaisesRegex(ValueError, 'changed'):
            service.execute_action(self.project, dict(self.request, preview=False, forest_tree_count=12,
                                                     planned_signature=plan_file['signature']))
        plan = plan_file['plan']
        self.assertEqual(plan['test_fraction'], .2)
        self.assertTrue(set(plan['train_groups']).isdisjoint(plan['test_groups']))
        for fold in plan['folds']:
            self.assertEqual(set(fold['train'] + fold['test']), set(plan['train']))
            rows = plan_file['snapshot']['rows']
            self.assertTrue({rows[i]['group'] for i in fold['train']}.isdisjoint(
                rows[i]['group'] for i in fold['test']))
        request_path = self.root / 'request.json'
        atomic_json(request_path, dict(self.request, project_path=self.project.path, preview=False,
                                       planned_signature=plan_file['signature']))
        command = [sys.executable, '-B', '-m', 'src.desktop.worker', '--request', str(request_path)]
        run = subprocess.run(command, capture_output=True, encoding='utf-8', timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        event = json.loads(run.stdout.splitlines()[-1])
        path = Path(event['summary']['path'])
        saved = json.loads(path.read_text(encoding='utf-8'))
        report = saved['report']
        self.assertEqual(set(report['models']), {'dummy', 'tree', 'forest'})
        self.assertEqual(len(report['predictions']), len(plan['test']))
        self.assertEqual(saved['snapshot'], plan_file['snapshot'])
        self.assertTrue(report['models']['tree']['tuning'])
        self.assertTrue(all(len(trial['fold_macro_f1']) == len(plan['folds'])
                            for trial in report['models']['tree']['tuning']))
        nodes = report['tree_nodes']
        self.assertEqual(max(node['depth'] for node in nodes), report['models']['tree']['fit_info']['depth'])
        for node in nodes:
            if node['feature'] is not None:
                for branch in ('left', 'right'):
                    self.assertEqual(nodes[node[branch]]['depth'], node['depth'] + 1)
        self.assertIn('tree_path', report['predictions'][0])
        self.assertEqual(report['models']['forest']['parameters']['n_estimators'], 11)
        self.assertEqual({candidate['parameters']['n_estimators']
                          for candidate in report['models']['forest']['tuning']}, {11})
        from joblib import load
        for key in ('tree', 'forest'):
            result = report['models'][key]
            self.assertEqual({candidate['parameters']['criterion'] for candidate in result['tuning']},
                             {'gini', 'entropy'})
            artifact = load(path.with_name(result['artifact']))
            self.assertEqual(artifact['features'], saved['snapshot']['features'])
            self.assertEqual(artifact['signature'], saved['signature'])
            estimator = artifact['estimator']
            self.assertEqual(estimator.predict([row['values'] for row in report['predictions']]).tolist(),
                             [row['predicted'][key] for row in report['predictions']])
            info = result['fit_info']
            self.assertEqual(info['cv_fit_count'], len(plan['folds']) * len(result['tuning']))
            self.assertGreaterEqual(info['final_fit_seconds'], 0)
            self.assertGreaterEqual(info['cv_fit_seconds'], 0)
            if key == 'tree':
                self.assertEqual(info['depth'], estimator.get_depth())
            else:
                self.assertEqual(info['tree_count'], len(estimator.estimators_))
                depths = [tree.get_depth() for tree in estimator.estimators_]
                self.assertEqual((info['min_depth'], info['max_depth']), (min(depths), max(depths)))
        service.assign_object_class(self.project, 'dataset-0', 'tile', 1, 'particle')
        with self.assertRaisesRegex(ValueError, 'changed'):
            service.execute_action(self.project, dict(self.request, preview=False,
                                                     planned_signature=plan_file['signature']))
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), saved)

    def test_unlabelled_object_prediction_and_review_keep_frozen_measurement_separate(self):
        from src.desktop.object_prediction import load_prediction, load_review, save_review

        trained_on = self.add_dataset(0, calibrated=True)
        inference_id = self.add_dataset(1, empty_tile=True, calibrated=True)
        request = dict(self.request, dataset_ids=[trained_on], area='Area_um2', folds=0)
        preview = service.execute_action(self.project, request)
        plan = json.loads(Path(preview['path']).read_text(encoding='utf-8'))
        evaluation = service.execute_action(self.project, dict(
            request, preview=False, planned_signature=plan['signature']))
        evaluation_path = Path(evaluation['path'])
        outcome = json.loads(evaluation_path.read_text(encoding='utf-8'))
        for obj in (2, 3, 4):
            service.assign_object_class(self.project, inference_id, 'tile', obj, None)
        dataset = self.project.get_dataset(inference_id)
        output = Path(dataset['results_dir'])
        verification = output / 'verification_masks'
        mask = verification / 'object_locations' / 'tile' / 'obj_002.png'
        crop = verification / 'tile' / 'obj_002_Unknown.png'
        for path in (mask, crop):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        atomic_json(verification / 'object_locations.json', dict(schema_version=1, objects=[
            dict(tile_name='tile', object_id=2, mask=mask.relative_to(verification).as_posix())]))
        labels_path = output / 'manual_object_labels.json'
        labels = labels_path.read_bytes()
        request = dict(action='object_prediction', evaluation_path=str(evaluation_path),
                       model_key='forest', dataset_id=inference_id, tile_names=['tile', 'empty'])
        result = service.execute_action(self.project, request)
        path = Path(result['path'])
        report = load_prediction(self.project, path)
        rows = report['snapshot']['rows']
        self.assertEqual(report['model']['source_overlap'], 'different_source')
        self.assertEqual(report['model']['classes'], [0, 1])
        self.assertEqual(report['model']['sha256'], outcome['report']['models']['forest']['artifact_sha256'])
        self.assertEqual(report['snapshot']['features'][0], 'Area_um2')
        self.assertEqual(rows[0]['values'][0], .625)
        self.assertEqual([row['object_id'] for row in rows], [2, 3, 4])
        self.assertTrue(all('target' not in row and 0 <= row['confidence'] <= 1 for row in rows))
        self.assertEqual(rows[0]['mask_path'], mask.relative_to(self.root).as_posix())
        self.assertEqual(rows[0]['crop_path'], crop.relative_to(self.root).as_posix())
        with self.assertRaisesRegex(ValueError, 'no objects without a manual class'):
            service.execute_action(self.project, dict(request, tile_names=['empty']))
        before = path.read_bytes()
        self.assertEqual(load_review(self.project, path), {})
        save_review(self.project, path, 'tile', 2, 'correct')
        for invalid in (None, True, rows[1]['predicted'], 99):
            with self.assertRaisesRegex(ValueError, 'valid review decision'):
                save_review(self.project, path, 'tile', 3, 'incorrect', actual_class=invalid)
        # The manual reference can be a catalog class that the model cannot predict.
        save_review(self.project, path, 'tile', 3, 'incorrect', actual_class=4)
        decisions = load_review(self.project, path)
        self.assertEqual({key: row['decision'] for key, row in decisions.items()},
                         {'tile/2': 'correct', 'tile/3': 'incorrect'})
        self.assertEqual(decisions['tile/3']['actual_class'], 4)
        with patch('src.desktop.object_prediction.atomic_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                save_review(self.project, path, 'tile', 4, 'incorrect', actual_class=4)
        self.assertEqual(load_review(self.project, path), decisions)
        # Existing reviews remain readable and keep their error count until the
        # operator fills in the previously unknown reference class.
        review_path = path.with_name('review.json')
        legacy = json.loads(review_path.read_text(encoding='utf-8'))
        legacy['decisions']['tile/3'].pop('actual_class')
        atomic_json(review_path, legacy)
        decisions = load_review(self.project, path)
        self.assertNotIn('actual_class', decisions['tile/3'])
        self.assertEqual(save_review(self.project, path, 'tile', 2, None), {'tile/3': decisions['tile/3']})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(labels_path.read_bytes(), labels)
        with self.assertRaisesRegex(ValueError, 'valid review decision'):
            save_review(self.project, path, 'tile', 1, 'correct')

        # Existing reports predate the artifact checksum and still work with
        # their own trusted in-project model and validated runtime metadata.
        outcome['report']['models']['tree'].pop('artifact_sha256')
        atomic_json(evaluation_path, outcome)
        service.assign_object_class(self.project, trained_on, 'tile', 2, None)
        same = service.execute_action(self.project, dict(request, model_key='tree', dataset_id=trained_on,
                                                        tile_names=['tile']))
        same_report = load_prediction(self.project, same['path'])
        self.assertEqual(same_report['model']['source_overlap'], 'same_source')
        self.assertEqual(same_report['snapshot']['rows'][0]['evaluation_overlap'], 'train')

        uncalibrated = self.add_dataset(2)
        service.assign_object_class(self.project, uncalibrated, 'tile', 2, None)
        with self.assertRaisesRegex(ValueError, 'Check area units and calibration'):
            service.execute_action(self.project, dict(request, dataset_id=uncalibrated, tile_names=['tile']))

        with evaluation_path.with_name('forest.joblib').open('ab') as artifact:
            artifact.write(b'changed')
        with patch('joblib.load', side_effect=AssertionError('must verify before loading')):
            with self.assertRaisesRegex(ValueError, 'damaged or incompatible'):
                service.execute_action(self.project, request)
        self.assertEqual(len(list(path.parent.parent.glob('Prediction_*'))), 2)

    def test_duplicate_tiff_copies_cannot_be_evaluated_as_separate_datasets(self):
        self.add_dataset(0, tiff_bytes=b'same')
        self.add_dataset(1, tiff_bytes=b'same')
        with self.assertRaisesRegex(ValueError, 'including copies'):
            service.execute_action(self.project, self.request)

    def test_single_source_is_demonstration(self):
        rows = [dict(group='one', target=i) for i in range(2)]
        self.assertTrue(plan_split(rows)['demo'])
        self.assertEqual(plan_split(rows)['test'], [])

    def test_same_source_object_split_reserves_rare_classes_and_uses_only_train_for_cv(self):
        rows = self._grouped_rows([(102, 131, 12, 3, 14, 4)])
        plan = plan_split(rows, folds=2, split_mode='object')
        self.assertFalse(plan['demo'])
        self.assertEqual(plan['train_groups'], plan['test_groups'])
        self.assertEqual(plan['train_counts'], dict(zip(map(str, range(6)), [82, 105, 10, 2, 11, 3])))
        self.assertEqual(plan['test_counts'], dict(zip(map(str, range(6)), [20, 26, 2, 1, 3, 1])))
        self.assertTrue(set(plan['train']).isdisjoint(plan['test']))
        self.assertEqual(sorted(plan['train'] + plan['test']), list(range(len(rows))))
        self.assertEqual(sorted(i for fold in plan['folds'] for i in fold['test']), plan['train'])
        for fold in plan['folds']:
            self.assertTrue(set(fold['train']).isdisjoint(fold['test']))
            self.assertEqual(sorted(fold['train'] + fold['test']), plan['train'])
            self.assertTrue(all(fold['train_counts'].values()))
        self.assertEqual(plan, plan_split(rows, folds=2, split_mode='object'))
        with self.assertRaisesRegex(ValueError, 'K training objects'):
            plan_split(rows, folds=4, split_mode='object')

        singleton = plan_split(self._grouped_rows([(10, 1)]), split_mode='object')
        self.assertEqual(singleton['train_counts']['1'], 1)
        self.assertEqual(singleton['test_counts']['1'], 0)

    @staticmethod
    def _grouped_rows(counts):
        return [dict(group=str(group), target=label) for group, count in enumerate(counts)
                for label, size in enumerate(count) for _ in range(size)]

    def test_cv_keeps_rare_class_in_training_when_a_different_holdout_is_needed(self):
        rows = self._grouped_rows([(3, 1), (7, 1), (10, 0), (10, 0)])
        self.assertEqual(plan_split(rows)['test_counts']['1'], 1)
        plan = plan_split(rows, folds=2)
        self.assertEqual(plan['test_counts']['1'], 0)
        self.assertEqual([fold['train_counts']['1'] for fold in plan['folds']], [1, 1])
        self.assertEqual(sorted(i for fold in plan['folds'] for i in fold['test']), sorted(plan['train']))

    def test_cv_stratification_uses_actual_group_histograms(self):
        # In sklearn 1.7.2 the shuffled splitter left one validation fold
        # without the minority class on these same training groups.
        rows = self._grouped_rows([(2, 0), (11, 1), (11, 2), (9, 2), (5, 0), (2, 2), (1, 0)])
        plan = plan_split(rows, folds=3)
        self.assertEqual(plan, plan_split(rows, folds=3))
        self.assertEqual(sorted(fold['test_counts']['1'] for fold in plan['folds']), [1, 2, 2])

    def test_xlsx_reader_uses_manual_labels_and_groups_related_tiffs(self):
        from openpyxl import Workbook
        workbook = Workbook()
        workbook.active.title = 'Notes'
        sheet = workbook.create_sheet('Training')
        sheet.append(('Large_Image', 'Experiment_Group', 'Manual_Class_ID', 'Class_ID', 'Reviewed', *RF_PREDICTORS))
        sheet.append(('a.tif', 'Experiment X', 0, 5, True, 5, 2, .9, 1, 2, 0))
        sheet.append(('b.tif', 'experiment x', 1, 0, True, 5, 2, .9, 1, 2, 0))
        sheet.append(('b.tif', '', None, 5, False, 'ignored'))
        path = self.root / 'training.xlsx'
        workbook.save(path)
        features, rows, audits = read_training_rows(path, 'Area', lambda: None)
        self.assertEqual(features, list(RF_PREDICTORS))
        self.assertEqual([row['target'] for row in rows], [0, 1])
        self.assertEqual({row['group'] for row in rows}, {'group:experiment x'})
        self.assertEqual(len(audits), 2)

    def test_xlsx_worker_filters_both_partitions_and_saves_noncontiguous_classes(self):
        from joblib import load
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.append(('Large_Image', 'Manual_Class_ID', *RF_PREDICTORS))
        for label in (0, 1, 5):
            for i in range(10):
                predictors = [i + label + 1, 2, .9, 1, 2, 0] if label != 1 else ['ignored']
                sheet.append(['a.tif', label, *predictors])
        path = self.root / 'training.xlsx'
        workbook.save(path)
        request = dict(self.request, training_file=str(path), split_mode='object', class_ids=[0, 5])
        preview = service.execute_action(self.project, request)
        plan = json.loads(Path(preview['path']).read_text(encoding='utf-8'))
        self.assertEqual({row['target'] for row in plan['snapshot']['rows']}, {0, 5})
        self.assertEqual(len(plan['plan']['test']), 4)
        outcome = service.execute_action(self.project, dict(request, preview=False, planned_signature=plan['signature']))
        report_path = Path(outcome['path'])
        report = json.loads(report_path.read_text(encoding='utf-8'))['report']
        self.assertEqual(report['classes'], [0, 5])
        self.assertEqual(report['split_mode'], 'object')
        self.assertEqual(len(report['models']['forest']['confusion']), 2)
        self.assertEqual({row['target'] for row in report['predictions']}, {0, 5})
        forest = load(report_path.with_name('forest.joblib'))
        self.assertEqual(forest['classes'], [0, 5])
        self.assertEqual(forest['split_mode'], 'object')
        self.assertEqual(len(forest['estimator'].estimators_), 11)
