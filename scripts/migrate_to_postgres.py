#!/usr/bin/env python3
"""Import a verified offline SQLite backup into an EMPTY PostgreSQL mentor schema.

Connection is read only from protected DATABASE_URL. Existing data is never
removed. Exact cell digests are checked before commit and on a fresh connection.
Freeze source writes before exporting the final backup and switching production.
"""
import argparse
import os
import sys
import json
from pathlib import Path
from contextlib import closing
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database import Database
from migrations import run_migrations
from storage import connect, backend_name
from snapshot_migration import migrate_snapshot, verify_snapshot


def migrate(source):
    if backend_name() != 'postgresql':
        raise RuntimeError('Configure protected DATABASE_URL first')
    def prepare():
        Database().init_db()
        if not run_migrations():
            raise RuntimeError('Target initialization failed')
    with closing(connect('unused')) as target:
        report = migrate_snapshot(source, target, prepare)
    with closing(connect('unused')) as target:
        verify_snapshot(source, target, report['sha256'])
    return {**report, 'fresh_connection_verified': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sqlite', required=True, help='Verified offline SQLite backup outside repository')
    args = parser.parse_args()
    try:
        print(json.dumps(migrate(args.sqlite)))
    except Exception:
        # Never print driver exceptions that can contain credentials or row values.
        print('Migration failed; source was not modified. Check backup, target schema and protected connection settings.', file=sys.stderr)
        sys.exit(1)
