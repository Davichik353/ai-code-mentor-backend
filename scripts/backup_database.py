"""Consistent encrypted SQLite/Turso backup. Never place output in the checkout."""
import argparse
from contextlib import closing
from pathlib import Path
import os
import sqlite3
import sys
import tempfile
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.fernet import Fernet
from storage import connect
from database import Database
from snapshot_migration import quote, row_digests, table_names, columns


def outside_repository(path):
    path = Path(path).resolve()
    if path.is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError('Backup output must be outside the repository')
    if path.exists():
        raise ValueError('Output already exists; refusing to overwrite')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def backup(output, key, db_path=None):
    cipher = Fernet(key)
    output = outside_repository(output)
    with tempfile.TemporaryDirectory() as work:
        local = Path(work) / 'snapshot.sqlite3'
        with closing(connect(db_path or Database().db_path)) as src, closing(sqlite3.connect(local)) as dst:
            if getattr(src, 'backend', '') == 'postgresql':
                src.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                # Build the current SQLite backup schema in an isolated subprocess.
                env = {k:v for k,v in os.environ.items() if k not in ('DATABASE_URL','TURSO_DATABASE_URL','TURSO_AUTH_TOKEN')}
                env['REQUIRE_REMOTE_DATABASE'] = 'false'
                subprocess.run([sys.executable, '-c',
                    'from database import Database; from migrations import run_migrations; import sys; Database(sys.argv[1]).init_db(); assert run_migrations(sys.argv[1])',
                    str(local)], cwd=str(Path(__file__).resolve().parents[1]), env=env,
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    tables = table_names(src)
                    if set(tables) != set(table_names(dst)):
                        raise RuntimeError('Backup schema requires review')
                    for name in tables:
                        names = columns(src, name)
                        if set(names) != set(columns(dst, name)):
                            raise RuntimeError('Backup columns require review')
                        fields = ','.join(quote(n) for n in names)
                        rows = src.execute('SELECT '+fields+' FROM '+quote(name)).fetchall()
                        dst.executemany('INSERT INTO '+quote(name)+' ('+fields+') VALUES('+','.join('?' for _ in names)+')', rows)
                        if row_digests(src, name, names) != row_digests(dst, name, names):
                            raise RuntimeError('Backup verification failed')
                    dst.commit()
                    if dst.execute('PRAGMA foreign_key_check').fetchall():
                        raise RuntimeError('Backup foreign keys invalid')
                finally:
                    src.rollback()
            else:
                src.execute('BEGIN')
                try:
                    schema = src.execute("""SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL
                        AND name NOT LIKE 'sqlite_%' AND name NOT GLOB '__turso_internal_*'
                        ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END""").fetchall()
                    tables = []
                    for kind, name, sql in schema:
                        if kind == 'table':
                            dst.execute(sql)
                            rows = src.execute('SELECT * FROM '+quote(name)).fetchall()
                            if rows:
                                dst.executemany('INSERT INTO '+quote(name)+' VALUES('+','.join('?' for _ in rows[0])+')', rows)
                            field_names = [r[1] for r in src.execute('PRAGMA table_info('+quote(name)+')').fetchall()]
                            if row_digests(src, name, field_names) != row_digests(dst, name, field_names):
                                raise RuntimeError('Backup row verification failed')
                            tables.append(name)
                    for kind, name, sql in schema:
                        if kind != 'table':
                            dst.execute(sql)
                    dst.commit()
                    if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise RuntimeError('Backup integrity check failed')
                finally:
                    src.rollback()
        encrypted = cipher.encrypt(local.read_bytes())
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encrypted)
    return len(tables)


def restore(source, output, key):
    """Restore into a NEW offline file; never modifies a live database."""
    output = outside_repository(output)
    raw = Fernet(key).decrypt(Path(source).read_bytes())
    with tempfile.TemporaryDirectory() as work:
        check = Path(work) / 'restore.sqlite3'
        check.write_bytes(raw)
        with closing(sqlite3.connect(check)) as conn:
            if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Restore integrity check failed')
            if conn.execute('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('Restore foreign keys invalid')
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['backup', 'restore'])
    parser.add_argument('--output', required=True)
    parser.add_argument('--source', help='Encrypted snapshot for restore')
    args = parser.parse_args()
    key = os.environ.get('BACKUP_ENCRYPTION_KEY')
    if not key:
        parser.error('BACKUP_ENCRYPTION_KEY is required')
    if args.operation == 'backup':
        print('Verified encrypted backup created; tables:', backup(args.output, key.encode()))
    else:
        if not args.source:
            parser.error('--source is required for restore')
        restore(args.source, args.output, key.encode())
        print('Restored into a new offline file; integrity verified')
