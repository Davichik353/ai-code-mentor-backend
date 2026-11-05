"""Conservative, lossless import of an explicitly selected SQLite snapshot.

No row data or credential hashes are written to reports. A populated target is
only accepted when the selected source records already match exactly.
"""
from collections import Counter
from contextlib import closing
from pathlib import Path
import base64
import hashlib
import json
import sqlite3

TABLES = ('users', 'analyses', 'feedback_cache', 'todos', 'learning_profiles',
          'learning_groups', 'learning_members', 'learning_assignments',
          'learning_hints', 'learning_submissions')
CORE = ('users', 'analyses', 'feedback_cache', 'todos')


class MigrationError(RuntimeError):
    pass


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def table_names(conn):
    return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]


def columns(conn, name):
    return [r[1] for r in conn.execute('PRAGMA table_info(' + quote(name) + ')').fetchall()]


def _digest_row(row):
    values = [{'blob': base64.b64encode(v).decode('ascii')} if isinstance(v, bytes) else v for v in row]
    data = json.dumps(values, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def row_digests(conn, table, names):
    query = 'SELECT ' + ','.join(quote(n) for n in names) + ' FROM ' + quote(table)
    return Counter(_digest_row(tuple(row)) for row in conn.execute(query))


def snapshot_info(path, expected_sha256=None):
    path = Path(path).resolve()
    if not path.is_file():
        raise MigrationError('Source snapshot does not exist')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected_sha256 and digest != expected_sha256:
        raise MigrationError('Snapshot SHA256 does not match its manifest')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as src:
        if src.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise MigrationError('Source snapshot integrity check failed')
        present = set(table_names(src))
        if not set(CORE).issubset(present):
            raise MigrationError('Snapshot is missing core application tables')
        if present.difference(TABLES):
            raise MigrationError('Unknown source tables require a reviewed migration')
        if src.execute('PRAGMA foreign_key_check').fetchall():
            raise MigrationError('Source snapshot contains foreign-key violations')
        counts = {name: src.execute('SELECT COUNT(*) FROM ' + quote(name)).fetchone()[0] for name in TABLES if name in present}
        unowned = counts.get('todos', 0) if 'user_id' not in columns(src, 'todos') else src.execute('SELECT COUNT(*) FROM todos WHERE user_id IS NULL').fetchone()[0]
    return {'sha256': digest, 'row_counts': counts, 'legacy_unowned_todos': unowned}


def _verify(src, dst, tables):
    target_tables = set(table_names(dst))
    for name in tables:
        if name not in target_tables:
            raise MigrationError('Target is missing a source table')
        source_columns = columns(src, name)
        if not set(source_columns).issubset(columns(dst, name)):
            raise MigrationError('Target schema is missing source columns')
        if row_digests(src, name, source_columns) != row_digests(dst, name, source_columns):
            raise MigrationError('Source and target records differ in table ' + name)


def verify_snapshot(path, target, expected_sha256=None):
    info = snapshot_info(path, expected_sha256)
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as src:
        _verify(src, target, info['row_counts'])
    return {**info, 'verified': True}


def migrate_snapshot(path, target, prepare_target, expected_sha256=None):
    info = snapshot_info(path, expected_sha256)
    path = Path(path).resolve()
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as src:
        populated = any(target.execute('SELECT COUNT(*) FROM ' + quote(n)).fetchone()[0] for n in table_names(target))
        if populated:
            # Safe repetition after a response is lost: compare exact source cells,
            # including password hashes, without printing them or rewriting anything.
            _verify(src, target, info['row_counts'])
            return {**info, 'verified': True, 'already_present': True}
        prepare_target()
        target_tables = set(table_names(target))
        for name in info['row_counts']:
            if name not in target_tables or not set(columns(src, name)).issubset(columns(target, name)):
                raise MigrationError('Target schema is incompatible with snapshot')
        with target:
            for name in TABLES:
                if name not in info['row_counts']:
                    continue
                names = columns(src, name)
                fields = ','.join(quote(n) for n in names)
                insert = 'INSERT INTO ' + quote(name) + ' (' + fields + ') VALUES (' + ','.join('?' for _ in names) + ')'
                for row in src.execute('SELECT ' + fields + ' FROM ' + quote(name)):
                    target.execute(insert, tuple(row))
            _verify(src, target, info['row_counts'])
            if target.execute('PRAGMA foreign_key_check').fetchall():
                raise MigrationError('Target foreign-key verification failed')
    return {**info, 'verified': True, 'already_present': False}
