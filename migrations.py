"""
Database migration script for production optimization.
Adds indexes on frequently queried columns and optimizes schema.
"""
import sqlite3
from datetime import datetime
import sys


def run_migrations(db_path: str = "code_mentor.db"):
    """Run all database migrations for production optimization."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print("[Migration] Starting database optimizations...")

        # 1. Add indexes on frequently queried columns
        print("[Migration] Adding indexes on users.email...")
        try:
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)'
            )
        except sqlite3.OperationalError as e:
            print(f"[Migration] Index on users.email already exists or error: {e}")

        print("[Migration] Adding indexes on analyses.user_id...")
        try:
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id)'
            )
        except sqlite3.OperationalError as e:
            print(f"[Migration] Index on analyses.user_id already exists: {e}")

        print("[Migration] Adding indexes on analyses.timestamp...")
        try:
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_analyses_timestamp ON analyses(timestamp)'
            )
        except sqlite3.OperationalError as e:
            print(f"[Migration] Index on analyses.timestamp already exists: {e}")

        # Composite index for user history queries
        print("[Migration] Adding composite index on analyses(user_id, timestamp)...")
        try:
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_analyses_user_timestamp '
                'ON analyses(user_id, timestamp)'
            )
        except sqlite3.OperationalError as e:
            print(f"[Migration] Composite index already exists: {e}")

        # Index for feedback cache lookups
        print("[Migration] Adding index on feedback_cache.analysis_id...")
        try:
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_feedback_cache_analysis_id '
                'ON feedback_cache(analysis_id)'
            )
        except sqlite3.OperationalError as e:
            print(f"[Migration] Index on feedback_cache.analysis_id already exists: {e}")

        # Index for todo queries
        print("[Migration] Adding index on todos.completed...")
        try:
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_todos_completed ON todos(completed)'
            )
        except sqlite3.OperationalError as e:
            print(f"[Migration] Index on todos.completed already exists: {e}")

        # 2. Add timestamp columns for better tracking if missing
        print("[Migration] Checking for missing timestamp columns...")
        cursor.execute("PRAGMA table_info(users)")
        user_cols = {row[1] for row in cursor.fetchall()}
        if "updated_at" not in user_cols:
            print("[Migration] Adding updated_at to users table...")
            cursor.execute(
                "ALTER TABLE users ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"
            )

        # 3. Vacuum to optimize database file
        print("[Migration] Running VACUUM to optimize database...")
        cursor.execute("VACUUM")

        # 4. Analyze for query planner
        print("[Migration] Running ANALYZE for query optimization...")
        cursor.execute("ANALYZE")

        conn.commit()
        print("[Migration] ✓ All migrations completed successfully!")
        return True

    except Exception as e:
        print(f"[Migration] ✗ Error during migration: {e}", file=sys.stderr)
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    success = run_migrations()
    sys.exit(0 if success else 1)
