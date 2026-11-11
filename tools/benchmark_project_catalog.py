"""Reproducible synthetic metadata benchmark; never opens scientific datasets."""
import argparse
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.desktop.project import atomic_json
from src.desktop.project_catalog import ProjectCatalog


def timed(operation, repeats=7):
    values = []
    for _ in range(repeats):
        started = time.perf_counter()
        operation()
        values.append((time.perf_counter() - started) * 1000)
    return round(statistics.median(values), 3)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='New output directory, never an existing project')
    args = parser.parse_args(argv)
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    results = []
    for count, events in ((10, 100), (100, 10000), (1000, 50000)):
        folder = root / str(count)
        folder.mkdir()
        path = folder / 'project.json'
        document = dict(schema_version=1, name='SIMULATED metadata benchmark', settings={},
            sources=[dict(id='source-' + str(i), name='simulated.tif', path='sources/simulated.tif')
                     for i in range(count)],
            datasets=[dict(id='dataset-' + str(i), source_id='source-' + str(i),
                           name='simulated_' + str(i), status='ready' if i % 2 else 'running')
                      for i in range(count)],
            history=[dict(time='2026-11-11T00:00:00+00:00', action='SIMULATED_label',
                          dataset_id='dataset-' + str(i % count), object_id=i)
                     for i in range(events)])
        atomic_json(path, document)
        catalog = ProjectCatalog(path)
        started = time.perf_counter()
        catalog.synchronize()
        first_index = (time.perf_counter() - started) * 1000

        def from_json():
            saved = json.loads(path.read_bytes())
            return [item for item in saved['datasets'] if item['status'] == 'ready'][:100]

        def from_sql():
            return catalog.records('datasets', status='ready', limit=100)

        assert from_json() == from_sql()

        def save_both():
            document['history'].append(dict(time='2026-11-11T00:00:00+00:00', action='SIMULATED_append'))
            atomic_json(path, document)
            catalog.synchronize()

        item = dict(datasets=count, initial_history_events=events,
                    json_query_ms=timed(from_json), sql_query_ms=timed(from_sql),
                    json_only_save_ms=timed(lambda: atomic_json(path, document)),
                    json_plus_catalog_save_ms=timed(save_both),
                    first_index_ms=round(first_index, 3))
        item.update(json_bytes=path.stat().st_size, sqlite_bytes=catalog.path.stat().st_size)
        results.append(item)
    report = dict(synthetic=True, repetitions=7, statistic='median except first_index_ms (one run)',
                  python=sys.version, sqlite=sqlite3.sqlite_version, platform=platform.platform(),
                  results=results)
    (root / 'benchmark.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
