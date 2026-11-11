"""Derived SQL metadata never replaces or damages authoritative project files."""
from contextlib import closing, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from src.desktop.project import Project, atomic_json
from src.desktop.project_catalog import CatalogError, ProjectCatalog, APPLICATION_ID


class ProjectCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='project_catalog_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = Project.create(self.root / 'project.json', 'Исследование א')
        self.catalog = self.project.catalog()

    def populated(self):
        self.project.sources = [dict(id='source', name='Источник א', path='sources/image.tif')]
        self.project.datasets = [dict(id='a', source_id='source', name='One', status='ready'),
                                 dict(id='b', source_id='source', name='Two', status='running')]
        self.project._extra_fields['future_extension'] = {'list': [1, 'א']}
        self.project.add_history('review', dataset_id='a', custom={'test': True})

    def test_save_queries_order_filters_and_exact_snapshot(self):
        self.populated()
        self.assertEqual(self.catalog.status()['state'], 'current')
        self.assertEqual(self.catalog.records('sources'), self.project.sources)
        self.assertEqual(self.catalog.records('datasets', status='running'), [self.project.datasets[1]])
        self.assertEqual(self.catalog.records('datasets', source_id='source', limit=1, offset=1),
                         [self.project.datasets[1]])
        self.assertEqual(self.catalog.records('history', action='review', dataset_id='a'), self.project.history)
        with closing(sqlite3.connect(self.catalog.path)) as connection:
            raw = connection.execute('SELECT json_bytes FROM snapshot').fetchone()[0]
            self.assertEqual(raw, Path(self.project.path).read_bytes())
            self.assertEqual(json.loads(raw)['future_extension'], {'list': [1, 'א']})
        self.assertFalse(self.catalog.synchronize())

    def test_missing_database_and_read_only_legacy_load(self):
        self.catalog.path.unlink()
        original = Path(self.project.path).read_bytes()
        loaded = Project.load(self.project.path)
        self.assertEqual(loaded.catalog().status()['state'], 'missing')
        self.assertFalse(self.catalog.path.exists())
        self.assertEqual(Path(loaded.path).read_bytes(), original)
        loaded.save()
        self.assertEqual(self.catalog.status()['state'], 'current')

    def test_external_change_refuses_stale_queries_and_updates_deletions(self):
        self.populated()
        document = self.project.to_dict()
        document['datasets'] = []
        atomic_json(self.project.path, document)
        self.assertEqual(self.catalog.status()['state'], 'unavailable')
        with self.assertRaises(CatalogError):
            self.catalog.records('datasets')
        self.catalog.synchronize()
        self.assertEqual(self.catalog.records('datasets'), [])

    def test_index_failure_does_not_fail_json_commit(self):
        self.project.name = 'Saved even without a database'
        with patch.object(ProjectCatalog, 'synchronize', side_effect=sqlite3.OperationalError('locked')):
            with self.assertLogs('src.desktop.project', level='WARNING'):
                self.project.save()
        self.assertEqual(Project.load(self.project.path).name, self.project.name)
        self.assertEqual(self.project._catalog_error, 'locked')
        self.assertEqual(self.catalog.status()['state'], 'unavailable')

    def test_failed_index_transaction_rolls_back_all_tables(self):
        self.populated()
        before = self.catalog.path.read_bytes()
        original = Path.read_bytes
        reads = 0

        def changed(path):
            nonlocal reads
            value = original(path)
            if path == Path(self.project.path):
                reads += 1
                if reads == 2:
                    return value + b' '
            return value

        self.project.name = 'New name'
        atomic_json(self.project.path, self.project.to_dict())
        with patch.object(Path, 'read_bytes', changed):
            with self.assertRaises(CatalogError):
                self.catalog.synchronize()
        self.assertEqual(self.catalog.path.read_bytes(), before)

    def test_future_schema_and_unrelated_database_are_preserved(self):
        for pragma, value in (('user_version', 999), ('application_id', APPLICATION_ID + 1)):
            with closing(sqlite3.connect(self.catalog.path)) as connection:
                connection.execute(f'PRAGMA {pragma}={value}')
                connection.commit()
            before = self.catalog.path.read_bytes()
            with self.assertRaises(CatalogError):
                self.catalog.synchronize()
            with self.assertRaises(CatalogError):
                self.catalog.rebuild()
            self.assertEqual(self.catalog.path.read_bytes(), before)
            self.catalog.path.unlink()
            self.catalog.synchronize()

    def test_corrupt_catalog_explicit_rebuild_preserves_exact_old_bytes(self):
        self.populated()
        artifacts = self.root / 'measurements'
        artifacts.mkdir()
        scientific = artifacts / 'example.csv'
        scientific.write_bytes(b'Area\n42\n')
        raw_project = Path(self.project.path).read_bytes()
        damaged = b'not a SQLite database'
        self.catalog.path.write_bytes(damaged)
        self.assertEqual(self.catalog.status()['state'], 'unavailable')
        report = self.catalog.rebuild()
        self.assertEqual((Path(report['preserved_catalog']) / self.catalog.path.name).read_bytes(), damaged)
        self.assertEqual(self.catalog.status()['state'], 'current')
        self.assertEqual(Path(self.project.path).read_bytes(), raw_project)
        self.assertEqual(scientific.read_bytes(), b'Area\n42\n')

    def test_metadata_backup_is_matching_verified_and_never_overwrites(self):
        self.populated()
        target = self.root / 'backup'
        report = self.catalog.backup(target)
        self.assertEqual(report['scope'], 'project_metadata_only')
        self.assertEqual((target / 'project.json').read_bytes(), Path(self.project.path).read_bytes())
        self.assertEqual(ProjectCatalog(target / 'project.json').status()['state'], 'current')
        self.assertTrue((target / 'METADATA_ONLY.txt').is_file())
        with self.assertRaises(FileExistsError):
            self.catalog.backup(target)

    def test_sql_filters_do_not_execute_input_and_pages_are_bounded(self):
        self.populated()
        self.assertEqual(self.catalog.records('datasets', status="ready' OR 1=1 --"), [])
        for arguments in (dict(limit=0), dict(limit=10001), dict(offset=-1), dict(limit=True)):
            with self.assertRaises(ValueError):
                self.catalog.records('datasets', **arguments)
        with self.assertRaises(ValueError):
            self.catalog.records('snapshot')
        with self.assertRaises(ValueError):
            self.catalog.records('sources', action='review')

    def test_unsaved_drafts_are_never_indexed(self):
        self.populated()
        self.project.datasets[0]['status'] = 'unsaved'
        self.catalog.synchronize()
        self.assertEqual(self.catalog.records('datasets', dataset_id='a')[0]['status'], 'ready')

    def test_stale_metadata_backup_is_explicitly_incomplete(self):
        self.project.name = 'Changed outside the catalog'
        atomic_json(self.project.path, self.project.to_dict())
        target = self.root / 'failed_backup'
        with self.assertRaises(CatalogError):
            self.catalog.backup(target)
        self.assertTrue((target / 'INCOMPLETE.txt').is_file())
        self.assertFalse((target / 'METADATA_ONLY.txt').exists())

    def test_cli_maintenance_respects_the_desktop_project_lock(self):
        from src.desktop.qt import QtCore
        from tools.project_database import main
        lock = QtCore.QLockFile(self.project.path + '.lock')
        self.assertTrue(lock.tryLock(0))
        before = self.catalog.path.read_bytes()
        try:
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(['--project', self.project.path, 'sync'])
            self.assertEqual(code, 1)
            self.assertIn('Close this project', stderr.getvalue())
            self.assertEqual(self.catalog.path.read_bytes(), before)
        finally:
            lock.unlock()


if __name__ == '__main__':
    unittest.main()
