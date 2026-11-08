"""PostgreSQL implementation of the application's small DB-API surface.

Uses a private schema so Supabase's public Data API cannot expose user records.
Only trusted application SQL enters this adapter; values stay parameterized.
"""
import re
import sqlite3
import os
from urllib.parse import urlparse, parse_qs
import psycopg
from psycopg import ClientCursor
from storage import Row

SCHEMA = 'mentor'


def translate(sql, parameters):
    sql = sql.strip().rstrip(';')
    # These are the only SQLite-specific constructs used by the application.
    sql = re.sub(r'\bDATETIME\b', 'TEXT', sql, flags=re.I)
    if re.match(r'INSERT\s+OR\s+IGNORE\s+', sql, re.I):
        sql = re.sub(r'^INSERT\s+OR\s+IGNORE\s+', 'INSERT ', sql, flags=re.I)
        sql += ' ON CONFLICT DO NOTHING'
    sql = sql.replace('MIN(revealed+1, ?)', 'LEAST(revealed+1, ?)')
    # Do not replace question marks in quoted strings/identifiers.
    pieces = re.split(r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\")", sql)
    if parameters:
        pieces = [p.replace('%', '%%') for p in pieces]
    for i in range(0, len(pieces), 2):
        pieces[i] = pieces[i].replace('?', '%s')
    return ''.join(pieces)


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.raw = connection.raw.cursor()

    @property
    def rowcount(self):
        return self.raw.rowcount

    @property
    def description(self):
        return self.raw.description

    def execute(self, sql, parameters=()):
        normalized = sql.strip().rstrip(';')
        info = re.fullmatch(r'PRAGMA\s+table_info\(\s*"?([a-z_]+)"?\s*\)', normalized, re.I)
        if info:
            sql = """SELECT ordinal_position-1, column_name, data_type,
                     CASE WHEN is_nullable='NO' THEN 1 ELSE 0 END, column_default, 0
                     FROM information_schema.columns
                     WHERE table_schema=? AND table_name=? ORDER BY ordinal_position"""
            parameters = (SCHEMA, info[1])
        elif normalized.upper() == 'PRAGMA FOREIGN_KEYS=ON':
            sql = 'SELECT 1 WHERE FALSE'  # PostgreSQL always enforces foreign keys.
        elif normalized.upper().startswith('PRAGMA'):
            raise sqlite3.OperationalError('Unsupported PostgreSQL operation')
        try:
            self.raw.execute(translate(sql, parameters), tuple(parameters) if parameters else None)
        except psycopg.IntegrityError:
            raise sqlite3.IntegrityError('Database constraint failed') from None
        except psycopg.Error:
            raise sqlite3.OperationalError('PostgreSQL operation failed') from None
        return self

    def _row(self, row):
        if row is None or self.connection.row_factory is None:
            return row
        return Row([c.name for c in self.description], row)

    def fetchone(self):
        return self._row(self.raw.fetchone())

    def fetchall(self):
        return [self._row(r) for r in self.raw.fetchall()]

    def __iter__(self):
        return self

    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row

    def close(self):
        self.raw.close()


class Connection:
    backend = 'postgresql'

    def __init__(self, url, timeout=5):
        parts = urlparse(url)
        local_test = os.getenv('PG_LOCAL_TEST') == 'true' and not parts.hostname and parse_qs(parts.query).get('host', [''])[0].startswith('/tmp/mentor-postgres-')
        try:
            self.raw = psycopg.connect(url, connect_timeout=max(1, int(timeout)),
                cursor_factory=ClientCursor, options='-c search_path=mentor',
                sslmode='disable' if local_test else 'require')
        except psycopg.Error:
            raise sqlite3.OperationalError('PostgreSQL connection failed; check protected DATABASE_URL') from None
        self.row_factory = None

    def cursor(self):
        return Cursor(self)

    def execute(self, sql, parameters=()):
        return self.cursor().execute(sql, parameters)

    def executescript(self, sql):
        # Schema scripts in this project contain no functions or string semicolons.
        for statement in sql.split(';'):
            if statement.strip():
                self.execute(statement)
        return self

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        if kind:
            self.rollback()
        else:
            self.commit()
        return False
