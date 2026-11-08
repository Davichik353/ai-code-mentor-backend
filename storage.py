"""Connection factory: PostgreSQL, Turso/libSQL, or local SQLite.

Remote mode uses the primary database directly; no disposable local replica is
used on Render. Keep tokens in environment settings, never in the database URL.
"""
import os
import sqlite3
from urllib.parse import urlparse


def remote_enabled():
    return bool(os.getenv('DATABASE_URL', '').strip() or os.getenv('TURSO_DATABASE_URL', '').strip())


def _call(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except sqlite3.Error:
        raise
    except Exception as error:
        # The Rust driver uses ValueError for SQL errors. Preserve the error
        # categories our application handles, without logging URLs or tokens.
        detail = str(error).lower()
        if type(error).__name__ == 'IntegrityError' or any(term in detail for term in ('constraint failed', 'constraint violation', 'sqlite_constraint')):
            raise sqlite3.IntegrityError('Database constraint failed') from None
        raise sqlite3.OperationalError('Remote database operation failed') from None


class Row:
    """SQLite Row-compatible access by index or column name, including dict(row)."""
    def __init__(self, columns, values):
        self._columns = tuple(columns)
        self._values = tuple(values)

    def keys(self):
        return list(self._columns)

    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                key = self._columns.index(key)
            except ValueError:
                raise IndexError('No item with that key') from None
        return self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)


class Cursor:
    def __init__(self, connection, cursor):
        self.connection = connection
        self._cursor = cursor

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def execute(self, sql, parameters=()):
        _call(self._cursor.execute, sql, parameters)
        return self

    def _row(self, values):
        if values is None or self.connection.row_factory is None:
            return values
        return Row([c[0] for c in self.description], values)

    def fetchone(self):
        return self._row(_call(self._cursor.fetchone))

    def fetchall(self):
        return [self._row(row) for row in _call(self._cursor.fetchall)]

    def __iter__(self):
        return self

    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row

    def close(self):
        if hasattr(self._cursor, 'close'):
            _call(self._cursor.close)


class Connection:
    def __init__(self, connection):
        self._connection = connection
        self.row_factory = None

    def cursor(self):
        return Cursor(self, _call(self._connection.cursor))

    def execute(self, sql, parameters=()):
        return self.cursor().execute(sql, parameters)

    def executescript(self, sql):
        _call(self._connection.executescript, sql)
        return self

    def commit(self):
        _call(self._connection.commit)

    def rollback(self):
        _call(self._connection.rollback)

    def close(self):
        _call(self._connection.close)

    def __enter__(self):
        _call(self._connection.__enter__)
        return self

    def __exit__(self, exception_type, exception, traceback):
        return _call(self._connection.__exit__, exception_type, exception, traceback)


def backend_name():
    if os.getenv('DATABASE_URL', '').strip():
        return 'postgresql'
    return 'turso' if remote_enabled() else 'sqlite'


def connect(path, timeout=5.0):
    postgres = os.getenv('DATABASE_URL', '').strip()
    if postgres:
        if urlparse(postgres).scheme not in ('postgresql', 'postgres'):
            raise RuntimeError('DATABASE_URL must use postgresql:// or postgres://')
        from postgres_storage import Connection as PostgresConnection
        return PostgresConnection(postgres, timeout)

    url = os.getenv('TURSO_DATABASE_URL', '').strip()
    required = os.getenv('REQUIRE_REMOTE_DATABASE', '').lower() in ('true', '1', 'yes')
    if not url:
        if required:
            raise RuntimeError('TURSO_DATABASE_URL is required for persistent hosting')
        return sqlite3.connect(path, timeout=timeout)
    token = os.getenv('TURSO_AUTH_TOKEN', '').strip()
    if not token:
        raise RuntimeError('TURSO_AUTH_TOKEN is required when TURSO_DATABASE_URL is configured')
    parts = urlparse(url)
    if parts.scheme not in ('libsql', 'https', 'turso') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise RuntimeError('Use a turso://, libsql:// or https:// database URL without embedded credentials')
    if parts.scheme == 'turso':
        import turso_serverless
        raw = _call(turso_serverless.connect, url, auth_token=token)
    else:
        import libsql
        raw = _call(libsql.connect, database=url, auth_token=token, timeout=timeout)
    return Connection(raw)
