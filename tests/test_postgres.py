"""Run real learning/auth workflows on an isolated local PostgreSQL test server.

TEST_POSTGRES_URL must point to a disposable local Unix-socket database. Tests
reset only its mentor schema. Never set this to a hosted database.
"""
import os
import unittest
from urllib.parse import urlparse, parse_qs
from unittest.mock import patch
import psycopg
import test_learning


@unittest.skipUnless(os.getenv('TEST_POSTGRES_URL'), 'Local PostgreSQL test URL not set')
class PostgreSQLWorkflowTests(test_learning.LearningWorkflowTests):
    def setUp(self):
        url = os.environ['TEST_POSTGRES_URL']
        parsed = urlparse(url)
        socket = parse_qs(parsed.query).get('host', [''])[0]
        if parsed.hostname or not socket.startswith('/tmp/mentor-postgres-'):
            raise RuntimeError('Tests require disposable local PostgreSQL socket')
        with psycopg.connect(url) as conn:
            conn.execute('DROP SCHEMA IF EXISTS mentor CASCADE')
        self.pg_env = patch.dict(os.environ, {'DATABASE_URL':url, 'PG_LOCAL_TEST':'true'})
        self.pg_env.start()
        self.addCleanup(self.pg_env.stop)
        super().setUp()

    def test_stats_quotas_and_verified_backup_migration(self):
        from cryptography.fernet import Fernet
        from scripts.backup_database import backup, restore
        from scripts.migrate_to_postgres import migrate
        from storage import connect
        from contextlib import closing
        from snapshot_migration import MigrationError
        from pathlib import Path
        user = self.db.get_user_by_email('student@example.com')['id']
        self.assertTrue(self.db.reserve_analysis_quota(user, 1, 20))
        self.assertFalse(self.db.reserve_analysis_quota(user, 1, 20))
        self.db.record_ai_usage(user, [dict(model='test',input_tokens=1,output_tokens=2,total_tokens=3,outcome='ok')])
        self.db.save_analysis('print(5)', 'main.py', {'good':['test']}, 80, user)
        self.assertEqual(self.db.get_stats(user)['total_analyses'], 1)
        self.assertEqual(self.db.get_progress_stats(user)['average_score'], 80)
        self.db.create_todo(user, 'Проверка')
        self.submit()
        self.call('POST', f"/groups/{self.group['id']}/archive", self.teacher, {})
        key = Fernet.generate_key()
        encrypted = Path(self.tmp.name)/'backup.fernet'
        snapshot = Path(self.tmp.name)/'snapshot.sqlite3'
        backup(encrypted, key)
        restore(encrypted, snapshot, key)
        with psycopg.connect(os.environ['TEST_POSTGRES_URL']) as conn:
            conn.execute('DROP SCHEMA mentor CASCADE')
        report = migrate(snapshot)
        self.assertTrue(report['fresh_connection_verified'])
        self.assertTrue(migrate(snapshot)['already_present'])
        self.assertEqual(self.db.get_user_by_email('student@example.com')['id'], user)
        self.assertEqual(self.db.get_stats(user)['total_analyses'], 1)
        self.assertEqual(len(self.db.get_todos(user)), 1)
        self.assertTrue(self.call('GET', f"/groups/{self.group['id']}", self.teacher)['archived'])
        self.db.update_display_name(user, 'changed after snapshot')
        with self.assertRaises(MigrationError):
            migrate(snapshot)
