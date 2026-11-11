"""XP and levels follow one consistent progression, independent of code scores."""
import sqlite3
import tempfile
import unittest
from database import Database

class ExperienceTests(unittest.TestCase):
    def test_level_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(directory + '/xp.sqlite')
            db.init_db()
            user_id = db.create_user('xp@example.com', 'test-only')
            with sqlite3.connect(db.db_path) as conn:
                for count in range(202):
                    if count:
                        conn.execute('INSERT INTO analyses (id,user_id,filename,code,feedback,score,timestamp) VALUES (?,?,?,?,?,?,?)',
                                     (str(count), user_id, 'main.py', 'print(1)', '{}', count % 101, '2026-11-11T12:00:00Z'))
                        conn.commit()
                    if count in (0, 99, 100, 101, 199, 200, 201):
                        profile = db.get_user_by_id(user_id)
                        self.assertEqual(profile['level'], 1 + count // 100)
                        self.assertEqual(profile['xp_current'], count * 10 % 1000)
                        self.assertEqual(profile['xp_needed'], 1000)
                        self.assertEqual(profile['xp_total'], count * 10)
