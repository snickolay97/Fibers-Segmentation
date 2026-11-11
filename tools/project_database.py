"""Inspect or maintain the derived metadata database of one closed project."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.desktop.project_catalog import ProjectCatalog


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, help='Existing project.json')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status', help='Read-only integrity, freshness and record counts')
    sub.add_parser('sync', help='Create or refresh the catalog from saved project JSON')
    sub.add_parser('rebuild', help='Rebuild the index and preserve any old catalog in backups')
    listing = sub.add_parser('list', help='Read a bounded page from a current catalog')
    listing.add_argument('kind', choices=('sources', 'datasets', 'history'))
    listing.add_argument('--status')
    listing.add_argument('--source-id')
    listing.add_argument('--dataset-id')
    listing.add_argument('--action')
    listing.add_argument('--limit', type=int, default=100)
    listing.add_argument('--offset', type=int, default=0)
    backup = sub.add_parser('backup', help='Metadata only: NOT images, labels, masks, CSVs or models')
    backup.add_argument('destination', help='New directory; existing directories are refused')
    args = parser.parse_args(argv)
    lock = None
    try:
        project_path = Path(args.project).resolve(strict=True)
        catalog = ProjectCatalog(project_path)
        if args.command in ('sync', 'rebuild', 'backup'):
            # Use the desktop's exact lock protocol; never repair beside a live worker.
            from src.desktop.qt import QtCore
            lock = QtCore.QLockFile(str(project_path) + '.lock')
            if not lock.tryLock(0):
                raise ValueError('Close this project in SoLoData before catalog maintenance')
        if args.command == 'status':
            result = catalog.status()
        elif args.command == 'sync':
            result = dict(changed=catalog.synchronize(), **catalog.status())
        elif args.command == 'rebuild':
            result = catalog.rebuild()
        elif args.command == 'backup':
            result = catalog.backup(args.destination)
        else:
            result = catalog.records(args.kind, status=args.status, source_id=args.source_id,
                                     action=args.action, dataset_id=args.dataset_id,
                                     limit=args.limit, offset=args.offset)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if isinstance(result, dict) and result.get('state') in ('missing', 'unavailable') else 0
    except (OSError, ValueError, sqlite3.Error) as error:
        print(json.dumps(dict(error=str(error)), ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        if lock is not None:
            lock.unlock()


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
