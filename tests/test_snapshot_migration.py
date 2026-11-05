import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from database import Database
from snapshot_migration import migrate_snapshot, verify_snapshot, snapshot_info, MigrationError
from storage import Connection
try:
    import turso
except ImportError:
    turso = None


class SnapshotMigrationTests(unittest.TestCase):
    def connect(self, path):
        return sqlite3.connect(str(path))

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.source=Path(self.tmp.name)/'source.sqlite'
        self.target_path=Path(self.tmp.name)/'target.sqlite'
        with sqlite3.connect(self.source) as c:
            c.executescript('''
                CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
                    display_name TEXT, created_at TEXT, email_verified INTEGER DEFAULT 1);
                CREATE TABLE analyses (id TEXT PRIMARY KEY, filename TEXT NOT NULL, code TEXT NOT NULL,
                    feedback TEXT NOT NULL, score INTEGER NOT NULL, timestamp TEXT, user_id TEXT REFERENCES users(id));
                CREATE TABLE feedback_cache (id TEXT PRIMARY KEY, analysis_id TEXT REFERENCES analyses(id),
                    critical_count INTEGER DEFAULT 0, improvement_count INTEGER DEFAULT 0, learning_count INTEGER DEFAULT 0, good_count INTEGER DEFAULT 0);
                CREATE TABLE todos (id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT, completed INTEGER,
                    created_at TEXT, updated_at TEXT);
            ''')
            c.execute('INSERT INTO users VALUES (?,?,?,?,?,?)',('u','learner@example.com','unchanged-fixture-password-hash','Learner','2026-09-20',1))
            c.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',('a','example.py','print(42)','{}',90,'2026-09-20','u'))
            c.execute('INSERT INTO feedback_cache VALUES (?,?,?,?,?,?)',('f','a',0,0,0,1))
            c.execute('INSERT INTO todos VALUES (?,?,?,?,?,?)',('t','Legacy task','Keep private',0,'2026-09-20','2026-09-20'))
        self.target=self.connect(self.target_path);self.addCleanup(self.target.close)

    def prepare(self):
        with patch('database.connect',lambda path,timeout=5:self.connect(path)):
            Database(str(self.target_path)).init_db()

    def migrate(self):
        return migrate_snapshot(self.source,self.target,self.prepare)

    def test_copy_preserves_named_columns_hashes_and_legacy_tasks(self):
        result=self.migrate()
        self.assertTrue(result['verified']);self.assertEqual(result['legacy_unowned_todos'],1)
        self.assertEqual(self.target.execute('SELECT password_hash, created_at, email_verified FROM users').fetchone(),('unchanged-fixture-password-hash','2026-09-20',1))
        self.assertEqual(self.target.execute('SELECT title, user_id FROM todos').fetchone(),('Legacy task',None))
        self.assertEqual(self.target.execute('SELECT COUNT(*) FROM analyses').fetchone()[0],1)
        reopened=self.connect(self.target_path)
        try:self.assertTrue(verify_snapshot(self.source,reopened)['verified'])
        finally:reopened.close()

    def test_repeat_of_identical_copy_is_read_only(self):
        self.assertFalse(self.migrate()['already_present'])
        self.assertTrue(self.migrate()['already_present'])
        self.assertEqual(self.target.execute('SELECT COUNT(*) FROM users').fetchone()[0],1)

    def test_populated_different_target_is_not_overwritten(self):
        self.prepare()
        self.target.execute('INSERT INTO users(id,email,password_hash) VALUES (?,?,?)',('other','other@example.com','other-hash'));self.target.commit()
        with self.assertRaises(MigrationError):self.migrate()
        self.assertEqual(self.target.execute('SELECT id FROM users').fetchone()[0],'other')
        self.assertEqual(self.target.execute('SELECT COUNT(*) FROM analyses').fetchone()[0],0)

    def test_failure_during_copy_rolls_back_all_rows(self):
        self.prepare();actual=self.target.execute
        def fail(sql,params=()):
            if sql.startswith('INSERT INTO "analyses"'):raise sqlite3.OperationalError('Simulated insertion failure')
            return actual(sql,params)
        class FailingConnection:
            def __enter__(wrapper):self.target.__enter__();return wrapper
            def __exit__(wrapper,*args):return self.target.__exit__(*args)
            def execute(wrapper,sql,params=()):return fail(sql,params)
        with self.assertRaises(sqlite3.OperationalError):
            migrate_snapshot(self.source,FailingConnection(),lambda:None)
        self.assertEqual(self.target.execute('SELECT COUNT(*) FROM users').fetchone()[0],0)

    def test_invalid_backup_digest_stops_before_any_write(self):
        with self.assertRaises(MigrationError):
            migrate_snapshot(self.source,self.target,self.prepare,expected_sha256='0'*64)
        self.assertEqual(self.target.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0],0)

    def test_verification_detects_modified_target_cells(self):
        self.migrate()
        self.target.execute('UPDATE users SET password_hash=? WHERE id=?',('changed','u'));self.target.commit()
        with self.assertRaises(MigrationError):verify_snapshot(self.source,self.target)

    def test_unknown_source_tables_are_not_silently_skipped(self):
        with sqlite3.connect(self.source) as c:c.execute('CREATE TABLE unknown_private_data(id TEXT)')
        with self.assertRaises(MigrationError):self.migrate()


@unittest.skipUnless(turso is not None,'Optional new Turso engine: install requirements-dev.txt')
class TursoSnapshotMigrationTests(SnapshotMigrationTests):
    def connect(self,path):
        return Connection(turso.connect(str(path)))
