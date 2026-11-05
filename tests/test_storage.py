"""Storage compatibility and fail-closed configuration checks.

The real libsql driver is exercised against temporary local files. Remote Turso
HTTP/auth readiness is a separate deployment check and is not implied by these tests.
"""
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import libsql
import storage
import test_learning
import test_release


class StorageConfigurationTests(unittest.TestCase):
    def test_remote_configuration_never_silently_falls_back(self):
        with patch.dict(os.environ, {'REQUIRE_REMOTE_DATABASE':'true','TURSO_DATABASE_URL':'','TURSO_AUTH_TOKEN':''}):
            with self.assertRaisesRegex(RuntimeError,'TURSO_DATABASE_URL'):
                storage.connect(':memory:')
        with patch.dict(os.environ, {'TURSO_DATABASE_URL':'libsql://example.turso.io','TURSO_AUTH_TOKEN':''}):
            with self.assertRaisesRegex(RuntimeError,'TURSO_AUTH_TOKEN'):
                storage.connect(':memory:')

    def test_remote_url_rejects_embedded_credentials_and_plain_http(self):
        for url in ('http://example.turso.io','https://user:secret@example.turso.io','https://example.turso.io?token=secret'):
            with self.subTest(url=url), patch.dict(os.environ,{'TURSO_DATABASE_URL':url,'TURSO_AUTH_TOKEN':'test-token'}):
                with self.assertRaises(RuntimeError): storage.connect(':memory:')

    def test_remote_driver_receives_url_and_token_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            native=libsql.connect(tmp+'/db.sqlite')
            with patch.dict(os.environ,{'TURSO_DATABASE_URL':'libsql://example.turso.io','TURSO_AUTH_TOKEN':'test-token'}), patch('libsql.connect',return_value=native) as factory:
                conn=storage.connect('unused.sqlite')
                factory.assert_called_once_with(database='libsql://example.turso.io',auth_token='test-token',timeout=5.0)
                self.assertIsInstance(conn,storage.Connection)
                conn.close()

    def test_host_health_probe_returns_failure_status_when_database_is_down(self):
        from fastapi.testclient import TestClient
        from types import SimpleNamespace
        import main
        for state, expected in [('healthy', 200), ('down', 503)]:
            checker=SimpleNamespace(get_health_status=lambda: {'status':state})
            with patch.object(main, 'get_health_checker', return_value=checker):
                response=TestClient(main.app).get('/health')
            self.assertEqual(response.status_code, expected)
            self.assertEqual(response.json()['status'], state)

    def test_new_turso_url_selects_the_official_serverless_sdk(self):
        import turso_serverless
        with tempfile.TemporaryDirectory() as tmp:
            native=libsql.connect(tmp+'/new-engine-contract.sqlite')
            with patch.dict(os.environ,{'TURSO_DATABASE_URL':'turso://example.turso.io','TURSO_AUTH_TOKEN':'test-token'}), patch.object(turso_serverless,'connect',return_value=native) as factory:
                conn=storage.connect('unused.sqlite')
                factory.assert_called_once_with('turso://example.turso.io',auth_token='test-token')
                conn.close()

    def test_driver_adapter_preserves_rows_transactions_and_constraint_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn=storage.Connection(libsql.connect(tmp+'/db.sqlite'))
            conn.execute('CREATE TABLE items (id TEXT PRIMARY KEY, title TEXT)');conn.commit()
            with conn:
                conn.execute('INSERT INTO items VALUES (?, ?)',('a','Saved'))
            conn.row_factory=sqlite3.Row
            row=conn.execute('SELECT * FROM items').fetchone()
            self.assertEqual(dict(row),{'id':'a','title':'Saved'});self.assertEqual(row[0],'a')
            with self.assertRaises(sqlite3.IntegrityError):
                with conn:conn.execute('INSERT INTO items VALUES (?, ?)',('a','Duplicate'))
            try:
                with conn:
                    conn.execute('INSERT INTO items VALUES (?, ?)',('b','Rollback'))
                    raise RuntimeError('cancel')
            except RuntimeError:pass
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM items').fetchone()[0],1)
            conn.close()
            reopened=storage.Connection(libsql.connect(tmp+'/db.sqlite'))
            self.assertEqual(reopened.execute('SELECT title FROM items').fetchone()[0],'Saved')
            reopened.close()


class LibsqlDriverMixin:
    def setUp(self):
        def connect(path,timeout=5.0):
            return storage.Connection(libsql.connect(path,timeout=timeout))
        for target in ('database.connect','learning.connect','migrations.connect','health.connect'):
            replacement=patch(target,connect);replacement.start();self.addCleanup(replacement.stop)
        super().setUp()


class LibsqlLearningTests(LibsqlDriverMixin,test_learning.LearningWorkflowTests):
    pass


class LibsqlReleaseTests(LibsqlDriverMixin,test_release.ReleaseTests):
    pass


try:
    import turso
except ImportError:
    turso = None


class TursoDriverMixin:
    def setUp(self):
        def connect(path,timeout=5.0):
            return storage.Connection(turso.connect(path))
        for target in ('database.connect','learning.connect','migrations.connect','health.connect'):
            replacement=patch(target,connect);replacement.start();self.addCleanup(replacement.stop)
        # Remote maintenance must not run VACUUM against the new engine.
        remote=patch('migrations.remote_enabled',return_value=True);remote.start();self.addCleanup(remote.stop)
        super().setUp()


@unittest.skipUnless(turso is not None, 'Optional pyturso engine: install requirements-dev.txt')
class TursoLearningTests(TursoDriverMixin,test_learning.LearningWorkflowTests):
    pass


@unittest.skipUnless(turso is not None, 'Optional pyturso engine: install requirements-dev.txt')
class TursoReleaseTests(TursoDriverMixin,test_release.ReleaseTests):
    pass
