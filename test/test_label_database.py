"""Incremental targets preserve old projects, exact identity and crash recovery."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import importlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

from src.desktop import service
from src.desktop.project import Project, atomic_json
from src.desktop import object_labels
from src.desktop.label_database import LabelDatabase, DATABASE_FILENAME, STORAGE_FILENAME


class LabelDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.fixture = importlib.import_module('test_object_labels').ObjectLabelsTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.project, self.dataset, self.root = self.fixture.project, self.fixture.dataset, self.fixture.root
        self.output = Path(self.dataset['results_dir'])
        self.store = LabelDatabase(self.output)

    def assign(self, ident=1, key='fiber'):
        return service.assign_object_class(self.project, self.dataset['id'], 'sample_tile_0001', ident, key, compact=True)

    def legacy(self):
        identity = object_labels._measurement(self.dataset)[-1]
        document = dict(schema_version=1, class_catalog_version=1, **identity, labels={
            'sample_tile_0001/1': dict(Tile_Name='sample_tile_0001', Object_ID=1,
                Manual_Class='agglomeration', Manual_Class_ID=2, Reviewed=True, updated_at='original'),
            'sample_tile_0001/2': dict(Tile_Name='sample_tile_0001', Object_ID=2,
                Manual_Class='self_crossed_tube', Manual_Class_ID=4, Reviewed=True, updated_at='original')})
        path = self.output/object_labels.LABELS_FILENAME
        atomic_json(path, document)
        return path

    def test_legacy_import_preserves_exact_bytes_and_semantic_class_ids(self):
        legacy = self.legacy(); original = legacy.read_bytes()
        project_before = Path(self.project.path).read_bytes()
        csv = Path(self.dataset['last_csv']); csv_before = csv.read_bytes()
        self.assertFalse(self.store.present)
        self.assertEqual(service.get_object_labels(self.dataset)['assigned'], 2)
        self.assertFalse(self.store.path.exists())
        self.assign(ident=1, key='particle')
        report = service.get_object_labels(self.dataset)
        self.assertEqual(report['labels']['sample_tile_0001/1']['Manual_Class_ID'], 0)
        self.assertEqual(report['labels']['sample_tile_0001/2']['Manual_Class_ID'], 2)
        self.assertEqual(legacy.read_bytes(), original)
        self.assertEqual(csv.read_bytes(), csv_before)
        self.assertEqual(Path(self.project.path).read_bytes(), project_before)

    def test_csv_change_between_snapshot_and_transaction_cannot_rebind_labels(self):
        original = object_labels._measurement
        csv_path = Path(self.dataset['last_csv'])

        def changed_snapshot(*args, **kwargs):
            snapshot = original(*args, **kwargs)
            csv_path.write_bytes(csv_path.read_bytes() + b'\n')
            return snapshot

        with patch.object(object_labels, '_measurement', side_effect=changed_snapshot):
            with self.assertRaisesRegex(ValueError, 'CSV changed'):
                self.assign()
        self.assertFalse(self.store.path.exists())

    def test_warm_assignment_reads_no_csv_and_publishes_no_json(self):
        self.assign()
        csv = Path(self.dataset['last_csv']).resolve()
        old_open = Path.open

        def guarded(path, *args, **kwargs):
            if path.resolve() == csv:
                raise AssertionError('A warm assignment reopened the scientific CSV')
            return old_open(path, *args, **kwargs)

        with (patch.object(Path, 'open', guarded),
              patch.object(self.project, 'save', side_effect=AssertionError('JSON save')),
              patch.object(object_labels, 'atomic_json', side_effect=AssertionError('JSON publication'))):
            delta = self.assign(ident=2, key='particle')
        self.assertNotIn('labels', delta)
        self.assertEqual(delta['assigned'], 2)
        self.assertEqual(delta['label']['Manual_Class'], 'particle')
        with closing(self.store.connect(readonly=True)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM targets').fetchone()[0], 2)
            self.assertEqual(connection.execute('SELECT count(*) FROM events').fetchone()[0], 2)

    def test_csv_same_size_edit_with_restored_mtime_is_rejected(self):
        self.assign()
        source = Path(self.dataset['last_csv']); before = source.stat()
        raw = source.read_bytes(); self.assertIn(b'100', raw)
        source.write_bytes(raw.replace(b'100', b'999', 1))
        os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaises(ValueError):
            self.assign(ident=2)
        with closing(self.store.connect(readonly=True)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM targets').fetchone()[0], 1)

    def test_deleted_authority_never_falls_back_to_legacy_snapshot(self):
        legacy = self.legacy()
        self.assign(key='particle')
        self.store.path.unlink()
        self.assertTrue(self.store.marker.exists())
        self.assertTrue(legacy.exists())
        with self.assertRaises(ValueError):
            service.get_object_labels(self.dataset)
        with self.assertRaises(ValueError):
            self.assign()

    def test_external_legacy_edits_are_not_silently_overridden(self):
        legacy = self.legacy()
        self.assign(key='particle')
        legacy.write_bytes(legacy.read_bytes()+b'\n')
        with self.assertRaises(ValueError):
            self.assign(ident=2)
        with self.assertRaises(ValueError):
            service.export_training_csv(self.dataset, self.root/'rejected.csv')

    def test_target_count_and_audit_roll_back_together(self):
        self.assign()
        with closing(self.store.connect()) as connection, connection:
            connection.execute("CREATE TRIGGER stop_audit BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT,'test rollback'); END")
        history = list(self.project.history)
        with self.assertRaises(ValueError):
            self.assign(key='particle')
        report = service.get_object_labels(self.dataset)
        self.assertEqual(report['labels']['sample_tile_0001/1']['Manual_Class'], 'fiber')
        self.assertEqual(report['class_counts']['fiber'], 1)
        self.assertEqual(report['class_counts']['particle'], 0)
        self.assertEqual(len(self.store.events()), 1)
        self.assertEqual(self.project.history, history)

    def test_committed_history_recovers_without_project_json_checkpoint(self):
        before = Path(self.project.path).read_bytes()
        delta = self.assign()
        self.assertEqual(Path(self.project.path).read_bytes(), before)
        restored = Project.load(self.project.path)
        self.assertEqual(restored.history[-1]['event_id'], delta['audit_event']['event_id'])
        restored.save()
        twice = Project.load(restored.path)
        self.assertEqual(sum(e.get('event_id') == delta['audit_event']['event_id'] for e in twice.history), 1)

    def test_concurrent_updates_to_distinct_objects_are_both_kept(self):
        self.assign(key=None)  # Complete the one-time import before writers compete.
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(self.assign, ident, key) for ident,key in ((1,'fiber'),(2,'particle'))]
            for future in futures:
                future.result()
        report = service.get_object_labels(self.dataset)
        self.assertEqual(report['assigned'], 2)
        self.assertEqual(report['class_counts']['fiber'], 1)
        self.assertEqual(report['class_counts']['particle'], 1)

    def test_noop_does_not_write_target_or_another_event(self):
        self.assign()
        before = self.store.path.read_bytes()
        history = len(self.project.history)
        result = self.assign()
        self.assertFalse(result['changed'])
        self.assertEqual(before, self.store.path.read_bytes())
        self.assertEqual(len(self.project.history), history)

    def test_explicit_snapshot_contains_current_targets_and_protects_authority(self):
        self.assign(); self.assign(ident=2, key='particle')
        target = self.root/'interchange'/'manual_object_labels.json'
        object_labels.export_label_snapshot(self.dataset, target)
        self.assertEqual(len(json.loads(target.read_bytes())['labels']), 2)
        for name in (DATABASE_FILENAME, STORAGE_FILENAME, object_labels.LABELS_FILENAME):
            with self.assertRaises(ValueError):
                object_labels.export_label_snapshot(self.dataset, self.output/name)
        project_bytes=Path(self.project.path).read_bytes()
        with self.assertRaises(ValueError):
            object_labels.export_label_snapshot(self.dataset,self.project.path)
        self.assertEqual(Path(self.project.path).read_bytes(),project_bytes)

    def test_corrupt_authority_is_preserved_and_never_rebuilt_from_json(self):
        legacy = self.legacy(); original = legacy.read_bytes()
        self.assign(key='particle')
        damaged = b'broken label authority'
        self.store.path.write_bytes(damaged)
        with self.assertRaises(ValueError): service.get_object_labels(self.dataset)
        with self.assertRaises(ValueError): self.assign(ident=2)
        self.assertEqual(self.store.path.read_bytes(), damaged)
        self.assertEqual(legacy.read_bytes(), original)

    def test_failed_migration_marker_can_resume_without_losing_legacy_targets(self):
        self.legacy()
        with patch('src.desktop.label_database.atomic_json', side_effect=OSError('marker unavailable')):
            with self.assertRaises(OSError): self.assign(key='particle')
        self.assertTrue(self.store.path.exists())
        self.assertFalse(self.store.marker.exists())
        self.assertEqual(service.get_object_labels(self.dataset)['labels']['sample_tile_0001/1']['Manual_Class'], 'agglomeration')
        self.assign(key='particle')
        self.assertTrue(self.store.marker.exists())
        self.assertEqual(service.get_object_labels(self.dataset)['assigned'], 2)

    def test_unavailable_change_time_uses_safe_revalidation_not_a_broken_cache(self):
        self.assign()
        def revision(path):
            stat=Path(path).stat()
            return stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns,None
        with (patch('src.desktop.object_labels.file_revision',revision),
              patch('src.desktop.label_database.file_revision',revision)):
            delta=self.assign(ident=2,key='particle')
            self.assertEqual(delta['assigned'],2)
            self.assertEqual(service.get_object_labels(self.dataset)['class_counts']['particle'],1)

    def test_newer_database_schema_is_refused_without_creating_a_marker(self):
        self.assign()
        with closing(self.store.connect()) as connection, connection:
            connection.execute('PRAGMA user_version=999')
        self.store.marker.unlink()
        original=self.store.path.read_bytes()
        with self.assertRaises(ValueError): self.assign(ident=2)
        self.assertFalse(self.store.marker.exists())
        self.assertEqual(self.store.path.read_bytes(),original)

    def test_process_crash_with_hot_journal_recovers_last_committed_target(self):
        self.assign()
        script = """
import json,os,sqlite3,sys
connection=sqlite3.connect(sys.argv[1])
connection.execute('PRAGMA cache_size=1')
connection.execute('BEGIN IMMEDIATE')
label=dict(Tile_Name='sample_tile_0001',Object_ID=1,Manual_Class='particle',Manual_Class_ID=0,
           Reviewed=True,padding='x'*200000)
connection.execute('UPDATE targets SET payload=? WHERE object_key=?',(json.dumps(label),'sample_tile_0001/1'))
connection.execute("UPDATE class_counts SET assigned=0 WHERE class_key='fiber'")
connection.execute("UPDATE class_counts SET assigned=1 WHERE class_key='particle'")
os._exit(0)
"""
        result=subprocess.run([sys.executable,'-B','-c',script,str(self.store.path)],capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(Path(str(self.store.path)+'-journal').exists())
        report=service.get_object_labels(self.dataset)
        self.assertEqual(report['labels']['sample_tile_0001/1']['Manual_Class'],'fiber')
        self.assertEqual(report['class_counts']['fiber'],1)
        self.assertEqual(report['class_counts']['particle'],0)
        self.assertEqual(len(self.store.events()),1)


if __name__ == '__main__':
    unittest.main()
