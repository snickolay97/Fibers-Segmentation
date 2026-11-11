"""Authoritative per-measurement targets and transactional, append-only audit.

Legacy JSON is preserved as an import source. A storage marker makes a missing
database an error instead of silently reverting to an outdated JSON snapshot.
This database is scientific user data, unlike the rebuildable project catalog.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from .file_revision import file_revision
from .i18n import tr
from .project import atomic_json, timestamp
from src.object_classes import OBJECT_CLASS_CATALOG, CLASS_CATALOG_VERSION


DATABASE_FILENAME = 'manual_object_labels.sqlite3'
STORAGE_FILENAME = 'manual_object_labels_storage.json'
APPLICATION_ID = 0x534C4C42
SCHEMA_VERSION = 1
_HASHES = {}
_CLASS_IDS = {item['key']: item['id'] for item in OBJECT_CLASS_CATALOG}


def _json(value):
    return json.dumps(value, ensure_ascii=False)


def _sha(path):
    path = Path(path)
    if not path.exists():
        return None
    revision = file_revision(path)
    key = (str(path.resolve()), revision)
    cached = _HASHES.get(key) if revision[-1] is not None else None
    if cached is not None:
        return cached
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if file_revision(path) != revision:
        raise ValueError(tr('Manual labels changed while being read. Reload the measurement.'))
    if len(_HASHES) >= 8:
        _HASHES.clear()
    if revision[-1] is not None:
        _HASHES[key] = digest
    return digest


class LabelDatabase:
    def __init__(self, output):
        self.output = Path(output)
        self.path = self.output / DATABASE_FILENAME
        self.marker = self.output / STORAGE_FILENAME

    @property
    def present(self):
        if self.path.is_symlink() or self.marker.is_symlink():
            raise ValueError(tr('Manual label output must not be a symlink'))
        if self.marker.exists() and not self.path.exists():
            raise ValueError(tr('The manual-label database is missing. Restore it from a full project backup.'))
        return self.path.exists()

    def connect(self, *, readonly=False, path=None):
        target = Path(path or self.path)
        if target.is_symlink():
            raise ValueError(tr('Manual label output must not be a symlink'))
        mode = 'ro' if readonly else 'rw'
        if readonly and self.marker.exists() and Path(str(target)+'-journal').is_file():
            # SQLite needs write access to roll back a hot journal after a crash.
            # Restrict recovery to our known header; never recreate the database.
            with target.open('rb') as handle:
                header = handle.read(100)
            if (header[:16] == b'SQLite format 3\x00'
                    and int.from_bytes(header[68:72], 'big') == APPLICATION_ID
                    and int.from_bytes(header[60:64], 'big') == SCHEMA_VERSION):
                mode = 'rw'
        connection = sqlite3.connect(target.resolve().as_uri() + '?mode='+mode,
                                     uri=True, timeout=2)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA trusted_schema=OFF')
        if not readonly:
            connection.execute('PRAGMA synchronous=FULL')
        return connection

    def validate(self, connection, identity=None):
        if (connection.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID
                or connection.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION):
            raise ValueError(tr('Unsupported manual object labels format'))
        meta = json.loads(connection.execute('SELECT document FROM metadata WHERE singleton=1').fetchone()[0])
        if (not isinstance(meta, dict) or type(meta.get('schema_version')) is not int
                or meta['schema_version'] != 1 or meta.get('class_catalog_version') != CLASS_CATALOG_VERSION
                or type(meta.get('object_count')) is not int or meta['object_count'] < 0):
            raise ValueError(tr('Unsupported manual object labels format'))
        if identity and any(meta.get(key) != value for key, value in identity.items()):
            raise ValueError(tr('Manual labels belong to a different measurement version or CSV'))
        if _sha(self.output / 'manual_object_labels.json') != meta.get('legacy_json_sha256'):
            raise ValueError(tr('The legacy label JSON changed after conversion. Resolve the two copies before editing.'))
        return meta

    def initialize(self, document, indexed, *, legacy_revision):
        """Publish a complete validated import without rewriting the legacy file."""
        if self.present:
            return
        raw_path = self.output / 'manual_object_labels.json'
        if raw_path.is_symlink():
            raise ValueError(tr('Manual label output must not be a symlink'))
        if (file_revision(raw_path) if raw_path.exists() else None) != legacy_revision:
            raise ValueError(tr('Manual labels changed while being read. Reload the measurement.'))
        legacy_sha = _sha(raw_path)
        meta = {key: value for key, value in document.items() if key != 'labels'}
        meta.update(legacy_json_sha256=legacy_sha, object_count=len(indexed),
                    class_catalog_version=CLASS_CATALOG_VERSION)
        handle, name = tempfile.mkstemp(prefix='.Label_database_', suffix='.sqlite3', dir=self.output)
        os.close(handle)
        staged = Path(name)
        try:
            with closing(sqlite3.connect(staged)) as connection, connection:
                connection.execute('PRAGMA foreign_keys=ON')
                connection.execute('PRAGMA synchronous=FULL')
                connection.execute('BEGIN IMMEDIATE')
                connection.execute('CREATE TABLE metadata(singleton INTEGER PRIMARY KEY CHECK(singleton=1), document TEXT NOT NULL)')
                connection.execute('CREATE TABLE objects(object_key TEXT PRIMARY KEY)')
                connection.execute('CREATE TABLE targets(object_key TEXT PRIMARY KEY REFERENCES objects(object_key), payload TEXT NOT NULL)')
                connection.execute('CREATE TABLE class_counts(class_key TEXT PRIMARY KEY, assigned INTEGER NOT NULL CHECK(assigned>=0))')
                connection.execute('CREATE TABLE events(sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_json TEXT NOT NULL)')
                connection.execute('INSERT INTO metadata VALUES(1,?)', (_json(meta),))
                connection.executemany('INSERT INTO objects VALUES(?)', ((key,) for key in indexed))
                connection.executemany('INSERT INTO targets VALUES(?,?)',
                                       ((key, _json(label)) for key, label in document['labels'].items()))
                counts = {item['key']: 0 for item in OBJECT_CLASS_CATALOG}
                for label in document['labels'].values():
                    counts[label['Manual_Class']] += 1
                connection.executemany('INSERT INTO class_counts VALUES(?,?)', counts.items())
                connection.execute(f'PRAGMA application_id={APPLICATION_ID}')
                connection.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            if _sha(raw_path) != legacy_sha:
                raise ValueError(tr('Manual labels changed while being read. Reload the measurement.'))
            # Writers use the project lock. Never replace an existing authority.
            staged.rename(self.path)
            self.ensure_marker()
        finally:
            staged.unlink(missing_ok=True)

    def ensure_marker(self):
        if not self.marker.exists():
            atomic_json(self.marker, dict(schema_version=1, database=DATABASE_FILENAME,
                                         purpose='authoritative_manual_targets'))

    def document(self, identity):
        with closing(self.connect(readonly=True)) as connection, connection:
            connection.execute('BEGIN')
            document = self.validate(connection, identity)
            document.pop('legacy_json_sha256', None)
            document['labels'] = {row[0]: json.loads(row[1]) for row in
                                  connection.execute('SELECT object_key,payload FROM targets')}
            counts = dict(connection.execute('SELECT class_key,assigned FROM class_counts'))
            document['assigned_count'] = sum(counts.values())
            recent = connection.execute('SELECT event_json FROM events ORDER BY sequence DESC LIMIT 1').fetchone()
            if recent:
                document['updated_at'] = json.loads(recent[0])['time']
            return document

    def assign(self, identity, key, label, *, csv_path, csv_revision):
        """One target and its audit are committed together; JSON is never rewritten."""
        event = None
        with closing(self.connect()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            meta = self.validate(connection, identity)
            self.ensure_marker()
            if not connection.execute('SELECT 1 FROM objects WHERE object_key=?', (key,)).fetchone():
                raise ValueError(tr('The selected object does not exist in this measurement version'))
            row = connection.execute('SELECT payload FROM targets WHERE object_key=?', (key,)).fetchone()
            previous = json.loads(row[0]) if row else None
            if previous is not None:
                previous_key = previous.get('Manual_Class') if isinstance(previous, dict) else None
                if (previous_key not in _CLASS_IDS or type(previous.get('Manual_Class_ID')) is not int
                        or previous['Manual_Class_ID'] != _CLASS_IDS[previous_key]
                        or previous.get('Reviewed') is not True):
                    raise ValueError(tr('Invalid manual class or review state'))
            previous_class = previous['Manual_Class'] if previous else None
            next_class = label['Manual_Class'] if label else None
            if previous_class != next_class:
                if previous_class:
                    connection.execute('UPDATE class_counts SET assigned=assigned-1 WHERE class_key=?', (previous_class,))
                if next_class:
                    connection.execute('UPDATE class_counts SET assigned=assigned+1 WHERE class_key=?', (next_class,))
                    connection.execute('INSERT INTO targets VALUES(?,?) ON CONFLICT(object_key) DO UPDATE SET payload=excluded.payload',
                                       (key, _json(label)))
                else:
                    connection.execute('DELETE FROM targets WHERE object_key=?', (key,))
                event = dict(time=timestamp(), action='assign_object_class', dataset_id=identity['dataset_id'],
                    measurement_reference=identity['measurement_reference'], tile_name=key.rsplit('/',1)[0],
                    object_id=int(key.rsplit('/',1)[1]), class_key=next_class, previous_class=previous_class)
                cursor = connection.execute('INSERT INTO events(event_json) VALUES(?)', (_json(event),))
                event['event_id'] = identity['measurement_reference'] + ':label:' + str(cursor.lastrowid)
                connection.execute('UPDATE events SET event_json=? WHERE sequence=?', (_json(event), cursor.lastrowid))
            counts = dict(connection.execute('SELECT class_key,assigned FROM class_counts'))
            if set(counts) != set(_CLASS_IDS) or sum(counts.values()) > meta['object_count']:
                raise ValueError(tr('Invalid manual object labels'))
            if file_revision(csv_path) != csv_revision:
                raise ValueError(tr('Measurement CSV changed while being read. Reload measurements.'))
            if csv_revision[-1] is None and hashlib.sha256(Path(csv_path).read_bytes()).hexdigest() != identity['csv_sha256']:
                raise ValueError(tr('Measurement CSV changed while being read. Reload measurements.'))
        return dict(object_key=key, label=label if previous_class != next_class else previous,
                    previous_class=previous_class, manual_class=next_class, audit_event=event,
                    changed=previous_class != next_class, class_counts=counts,
                    assigned=sum(counts.values()), total=meta['object_count'])

    def events(self):
        with closing(self.connect(readonly=True)) as connection, connection:
            connection.execute('BEGIN')
            self.validate(connection)
            return [json.loads(row[0]) for row in connection.execute('SELECT event_json FROM events ORDER BY sequence')]


def recover_project_label_history(project):
    """Recover committed audit events missing from the last JSON checkpoint."""
    if not isinstance(project.history, list):
        return
    root = Path(project.workspace) / 'measurements'
    paths = set(root.glob('*/*/' + DATABASE_FILENAME))
    paths.update(Path(d['results_dir']) / DATABASE_FILENAME for d in project.datasets if d.get('results_dir'))
    known = {item.get('event_id') for item in project.history if isinstance(item, dict)}
    dataset_ids = {item.get('id') for item in project.datasets}
    recovered = []
    for path in sorted(paths):
        if path.exists():
            for event in LabelDatabase(path.parent).events():
                if event.get('dataset_id') in dataset_ids and event.get('event_id') not in known:
                    known.add(event.get('event_id'))
                    recovered.append(event)
    project.history.extend(sorted(recovered, key=lambda event: event['time']))
