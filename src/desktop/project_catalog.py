"""Rebuildable SQLite index of project metadata, never of scientific pixels.

project.json is the authority. JSON is published before this derived index;
every query verifies its byte digest instead of trusting a second writer.
Connections are short-lived and never shared between Qt and worker processes.
"""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import uuid

from .storage_names import new_version


SCHEMA_VERSION = 1
APPLICATION_ID = 0x534F4C4F  # SOLO; refuse unrelated or newer databases.


class CatalogError(ValueError):
    """The index is unavailable, incompatible, or out of date."""


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False)


class ProjectCatalog:
    """Query saved project sources, datasets and history without loading images."""

    def __init__(self, project_path):
        self.project_path = Path(project_path).resolve()
        self.path = self.project_path.with_name(self.project_path.stem + '.sqlite3')
        if self.path == self.project_path:
            raise CatalogError('Project JSON and catalog paths must differ')

    def _connect(self, *, readonly=False, path=None):
        target = Path(path or self.path)
        if target.is_symlink():
            raise CatalogError('The catalog must not be a symbolic link')
        uri = target.as_uri() + ('?mode=ro' if readonly else '?mode=rwc')
        connection = sqlite3.connect(uri, uri=True, timeout=2.0)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA trusted_schema=OFF')
        if not readonly:
            # One application writer already owns the project QLockFile.
            # DELETE avoids persistent WAL/SHM companions in portable projects.
            connection.execute('PRAGMA synchronous=FULL')
        return connection

    @staticmethod
    def _validate(connection, *, allow_empty=False):
        version = connection.execute('PRAGMA user_version').fetchone()[0]
        app_id = connection.execute('PRAGMA application_id').fetchone()[0]
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if allow_empty and version == 0 and app_id == 0 and not tables:
            return False
        if version != SCHEMA_VERSION or app_id != APPLICATION_ID:
            raise CatalogError('Unsupported or unrelated project catalog; file preserved')
        return True

    @staticmethod
    def _create(connection):
        # Each record retains its full JSON so optional legacy fields survive.
        # Ordinals preserve ordering and allow legacy records without UUIDs.
        statements = (
            'CREATE TABLE snapshot (singleton INTEGER PRIMARY KEY CHECK(singleton=1), '
            'json_sha256 TEXT NOT NULL, json_bytes BLOB NOT NULL, indexed_at TEXT NOT NULL)',
            'CREATE TABLE sources (position INTEGER PRIMARY KEY, source_id TEXT, name TEXT, '
            'path TEXT, payload_json TEXT NOT NULL)',
            'CREATE INDEX sources_id ON sources(source_id)',
            'CREATE TABLE datasets (position INTEGER PRIMARY KEY, dataset_id TEXT, source_id TEXT, '
            'name TEXT, status TEXT, path TEXT, payload_json TEXT NOT NULL)',
            'CREATE INDEX datasets_id ON datasets(dataset_id)',
            'CREATE INDEX datasets_status ON datasets(status)',
            'CREATE INDEX datasets_source ON datasets(source_id)',
            'CREATE TABLE history (position INTEGER PRIMARY KEY, time TEXT, action TEXT, '
            'dataset_id TEXT, payload_json TEXT NOT NULL)',
            'CREATE INDEX history_action ON history(action, position)',
            'CREATE INDEX history_dataset ON history(dataset_id, position)',
        )
        for statement in statements:
            connection.execute(statement)
        connection.execute(f'PRAGMA application_id={APPLICATION_ID}')
        connection.execute(f'PRAGMA user_version={SCHEMA_VERSION}')

    def synchronize(self):
        """Index the saved bytes in one transaction; never publish in-memory drafts."""
        raw = self.project_path.read_bytes()
        document = json.loads(raw)
        if not isinstance(document, dict) or document.get('schema_version') != 1:
            raise CatalogError('Unsupported project JSON')
        for key in ('sources', 'datasets', 'history'):
            items = document.get(key, [])
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise CatalogError('Invalid project metadata list: ' + key)
        with closing(self._connect()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            if not self._validate(connection, allow_empty=True):
                self._create(connection)
            previous = connection.execute('SELECT json_sha256, json_bytes FROM snapshot').fetchone()
            if previous and previous[0] == _digest(raw):
                return False
            previous_document = json.loads(previous[1]) if previous else {}
            encoders = {
                'sources': lambda i, item: (i, item.get('id'), item.get('name'), item.get('path'), _json(item)),
                'datasets': lambda i, item: (i, item.get('id'), item.get('source_id'), item.get('name'),
                                              item.get('status'), item.get('path'), _json(item)),
                'history': lambda i, item: (i, item.get('time'), item.get('action'), item.get('dataset_id'), _json(item)),
            }
            for table, encode in encoders.items():
                items = document.get(table, [])
                old = previous_document.get(table, [])
                # Labeling typically appends one history entry. Keep unchanged
                # SQL rows and indexes instead of rewriting the growing history.
                changed = [encode(i, item) for i, item in enumerate(items)
                           if i >= len(old) or item != old[i]]
                if changed:
                    placeholders = ','.join('?' for _ in changed[0])
                    connection.executemany('INSERT OR REPLACE INTO ' + table + ' VALUES(' + placeholders + ')', changed)
                if len(items) < len(old):
                    connection.execute('DELETE FROM ' + table + ' WHERE position >= ?', (len(items),))
            connection.execute('INSERT OR REPLACE INTO snapshot VALUES(1,?,?,?)',
                               (_digest(raw), raw, datetime.now(timezone.utc).isoformat()))
            if self.project_path.read_bytes() != raw:
                raise CatalogError('Project changed while indexing; retry after the writer finishes')
        return True

    def _fresh(self, connection):
        self._validate(connection)
        row = connection.execute('SELECT json_sha256 FROM snapshot').fetchone()
        if row is None or row[0] != _digest(self.project_path.read_bytes()):
            raise CatalogError('Project catalog is out of date; synchronize or rebuild it')

    def status(self):
        """Read-only integrity and freshness check; never creates a missing file."""
        result = dict(path=str(self.path), schema_version=SCHEMA_VERSION,
                      authoritative=False, state='missing')
        if not self.path.exists():
            return result
        try:
            with closing(self._connect(readonly=True)) as connection, connection:
                connection.execute('BEGIN')
                self._validate(connection)
                integrity = [row[0] for row in connection.execute('PRAGMA integrity_check')]
                result['integrity'] = integrity
                if integrity != ['ok']:
                    raise CatalogError('Catalog integrity check failed')
                self._fresh(connection)
                result.update(state='current', counts={
                    table: connection.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                    for table in ('sources', 'datasets', 'history')})
        except (OSError, ValueError, sqlite3.Error) as error:
            result.update(state='unavailable', error=str(error))
        return result

    def records(self, kind, *, status=None, source_id=None, action=None, dataset_id=None,
                limit=100, offset=0):
        """Return a bounded page in saved order with parameterized exact filters."""
        allowed = {'sources': {'source_id'}, 'datasets': {'status', 'source_id', 'dataset_id'},
                   'history': {'action', 'dataset_id'}}
        if kind not in allowed:
            raise ValueError('Unknown catalog record kind')
        if type(limit) is not int or not 1 <= limit <= 10000 or type(offset) is not int or offset < 0:
            raise ValueError('Limit must be 1..10000 and offset must be nonnegative')
        filters = dict(status=status, source_id=source_id, action=action, dataset_id=dataset_id)
        clauses, parameters = [], []
        for key, value in filters.items():
            if value is not None:
                if key not in allowed[kind]:
                    raise ValueError('Unsupported catalog filter: ' + key)
                clauses.append(key + ' = ?')
                parameters.append(value)
        query = 'SELECT payload_json FROM ' + kind
        if clauses:
            query += ' WHERE ' + ' AND '.join(clauses)
        query += ' ORDER BY position LIMIT ? OFFSET ?'
        with closing(self._connect(readonly=True)) as connection, connection:
            connection.execute('BEGIN')
            self._fresh(connection)
            return [json.loads(row[0]) for row in connection.execute(query, parameters + [limit, offset])]

    def backup(self, destination):
        """Create a new metadata-only backup with matching JSON and SQLite bytes.

        This is not a project backup: images, labels, masks, CSVs and models
        must be copied separately with the application closed.
        """
        destination = Path(destination).resolve()
        destination.mkdir(parents=True, exist_ok=False)
        target = destination / self.path.name
        try:
            with closing(self._connect(readonly=True)) as source:
                self._fresh(source)
                with closing(sqlite3.connect(str(target))) as output:
                    source.backup(output)
                    raw = output.execute('SELECT json_bytes FROM snapshot').fetchone()[0]
                    if raw != self.project_path.read_bytes():
                        raise CatalogError('Project changed during backup; retry after the writer finishes')
                    if output.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise CatalogError('Backup integrity check failed')
            (destination / self.project_path.name).write_bytes(raw)
            (destination / 'METADATA_ONLY.txt').write_text(
                'Metadata only. Images, masks, labels, CSVs and models are NOT included.\n', encoding='utf-8')
        except Exception:
            # Retain a failed destination for diagnosis; never present it as complete.
            (destination / 'INCOMPLETE.txt').write_text('Backup did not finish.\n', encoding='utf-8')
            raise
        return dict(path=str(destination), scope='project_metadata_only', json_sha256=_digest(raw))

    def rebuild(self):
        """Replace only the derived index, preserving exact old files first.

        The caller must hold the same project lock as the desktop. Unknown
        application IDs/schema versions are preserved for a newer application.
        """
        if self.path.is_symlink():
            raise CatalogError('The catalog must not be a symbolic link')
        if self.path.exists():
            try:
                with closing(self._connect(readonly=True)) as old:
                    self._validate(old)
            except sqlite3.DatabaseError:
                pass  # Explicit repair of a corrupt derived index is permitted.
        temporary = self.path.with_name('.catalog-' + uuid.uuid4().hex + '.sqlite3')
        staged = ProjectCatalog(self.project_path)
        staged.path = temporary
        backup = None
        try:
            staged.synchronize()
            if staged.status()['state'] != 'current':
                raise CatalogError('Project changed during rebuild; retry')
            if self.path.exists():
                backup = new_version(self.project_path.parent / 'backups', 'Database_catalog')
                for suffix in ('', '-journal', '-wal', '-shm'):
                    original = Path(str(self.path) + suffix)
                    if original.exists():
                        if original.is_symlink():
                            raise CatalogError('Catalog recovery files must not be symbolic links')
                        shutil.copy2(original, backup / original.name)
                # Companions belong to the archived generation, not its replacement.
                for suffix in ('-journal', '-wal', '-shm'):
                    Path(str(self.path) + suffix).unlink(missing_ok=True)
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        return dict(path=str(self.path), preserved_catalog=str(backup) if backup else None)
