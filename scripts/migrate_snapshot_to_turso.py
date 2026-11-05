#!/usr/bin/env python3
"""Read-only preflight by default; --apply requires an explicitly configured Turso target."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from snapshot_migration import snapshot_info, migrate_snapshot, verify_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, help='Explicit SQLite backup path, never the live Render file')
    parser.add_argument('--expected-sha256', help='SHA256 from the backup manifest')
    parser.add_argument('--report', help='Create a new private JSON verification report; never overwrite an existing file')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--apply', action='store_true', help='Import only into an empty or exactly matching target')
    action.add_argument('--verify', action='store_true', help='Compare source data against the target without writes')
    args = parser.parse_args()
    report = snapshot_info(args.source, args.expected_sha256)
    if not (args.apply or args.verify):
        print(json.dumps({**report, 'mode': 'source-preflight-only'}, indent=2))
        return 0
    from storage import connect, remote_enabled
    if not remote_enabled() or not os.getenv('TURSO_AUTH_TOKEN'):
        raise RuntimeError('Configure TURSO_DATABASE_URL and TURSO_AUTH_TOKEN securely first')
    from database import Database
    from migrations import run_migrations
    def prepare():
        db = Database()
        db.init_db()
        if not run_migrations(db.db_path):
            raise RuntimeError('Target schema preparation failed')
    target = connect('unused-in-remote-mode')
    try:
        fn = verify_snapshot if args.verify else migrate_snapshot
        if args.verify:
            report = fn(args.source, target, args.expected_sha256)
        else:
            report = fn(args.source, target, prepare, args.expected_sha256)
    finally:
        target.close()
    # Reopen over a fresh remote connection after commit, verifying durability.
    reopened = connect('unused-in-remote-mode')
    try:
        verify_snapshot(args.source, reopened, args.expected_sha256)
    finally:
        reopened.close()
    report = {**report, 'fresh_connection_verified': True, 'target_host': urlparse(os.environ['TURSO_DATABASE_URL']).hostname}
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(report_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump(report, handle, indent=2)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        # No raw driver errors, data or credentials in deployment logs.
        print('Migration stopped safely:', type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
