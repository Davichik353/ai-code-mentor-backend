#!/usr/bin/env python3
"""
PostgreSQL Migration Script for AI Code Mentor
Migrates data from SQLite to PostgreSQL with validation.

Usage:
    python scripts/migrate_to_postgres.py --sqlite code_mentor.db --postgres postgresql://user:pass@localhost:5432/code_mentor
    python scripts/migrate_to_postgres.py --validate-only  # Check row counts without migrating
"""

import sqlite3
import sys
import argparse
from datetime import datetime
from typing import Dict, List, Tuple
import os

try:
    import psycopg2
    from psycopg2.extras import execute_batch
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


class PostgreSQLMigration:
    """Handles migration from SQLite to PostgreSQL."""

    def __init__(self, sqlite_path: str, postgres_uri: str):
        self.sqlite_path = sqlite_path
        self.postgres_uri = postgres_uri
        self.sqlite_conn = None
        self.pg_conn = None

    def connect(self):
        """Establish connections to both databases."""
        print("[1/7] Connecting to databases...")

        try:
            self.sqlite_conn = sqlite3.connect(self.sqlite_path)
            self.sqlite_conn.row_factory = sqlite3.Row
            print(f"  ✓ Connected to SQLite: {self.sqlite_path}")
        except Exception as e:
            print(f"  ✗ SQLite connection failed: {e}")
            sys.exit(1)

        try:
            self.pg_conn = psycopg2.connect(self.postgres_uri)
            self.pg_conn.autocommit = False
            print(f"  ✓ Connected to PostgreSQL")
        except Exception as e:
            print(f"  ✗ PostgreSQL connection failed: {e}")
            sys.exit(1)

    def export_data(self) -> Dict[str, List[tuple]]:
        """Export all data from SQLite."""
        print("[2/7] Exporting data from SQLite...")

        data = {}
        tables = ["users", "analyses", "feedback_cache", "todos"]

        cursor = self.sqlite_conn.cursor()

        for table in tables:
            try:
                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                # Convert Row objects to tuples
                data[table] = [tuple(row) for row in rows]
                print(f"  ✓ Exported {len(rows)} rows from {table}")
            except sqlite3.OperationalError as e:
                print(f"  ⚠ Table {table} doesn't exist or error: {e}")
                data[table] = []

        return data

    def create_schema(self):
        """Create PostgreSQL schema."""
        print("[3/7] Creating PostgreSQL schema...")

        cursor = self.pg_conn.cursor()

        schema_sql = """
        -- Drop existing tables if they exist
        DROP TABLE IF EXISTS feedback_cache CASCADE;
        DROP TABLE IF EXISTS analyses CASCADE;
        DROP TABLE IF EXISTS todos CASCADE;
        DROP TABLE IF EXISTS users CASCADE;

        -- Users table
        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            email_verified INTEGER NOT NULL DEFAULT 0,
            verification_token_hash TEXT,
            verification_expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Create index on email for fast lookups
        CREATE INDEX idx_users_email ON users(email);

        -- Analyses table
        CREATE TABLE analyses (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            filename TEXT NOT NULL,
            code TEXT NOT NULL,
            feedback TEXT NOT NULL,
            score INTEGER NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        -- Create indexes on analyses
        CREATE INDEX idx_analyses_user_id ON analyses(user_id);
        CREATE INDEX idx_analyses_timestamp ON analyses(timestamp DESC);
        CREATE INDEX idx_analyses_user_timestamp ON analyses(user_id, timestamp DESC);

        -- Feedback cache table
        CREATE TABLE feedback_cache (
            id TEXT PRIMARY KEY,
            analysis_id TEXT NOT NULL,
            critical_count INTEGER DEFAULT 0,
            improvement_count INTEGER DEFAULT 0,
            learning_count INTEGER DEFAULT 0,
            good_count INTEGER DEFAULT 0,
            FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
        );

        -- Create index on feedback_cache
        CREATE INDEX idx_feedback_cache_analysis_id ON feedback_cache(analysis_id);

        -- Todos table
        CREATE TABLE todos (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Create index on todos
        CREATE INDEX idx_todos_completed ON todos(completed);
        """

        try:
            cursor.execute(schema_sql)
            self.pg_conn.commit()
            print("  ✓ PostgreSQL schema created successfully")
        except Exception as e:
            self.pg_conn.rollback()
            print(f"  ✗ Schema creation failed: {e}")
            sys.exit(1)

    def import_data(self, data: Dict[str, List[tuple]]):
        """Import data into PostgreSQL."""
        print("[4/7] Importing data into PostgreSQL...")

        cursor = self.pg_conn.cursor()

        # Import order matters due to foreign keys
        import_order = ["users", "analyses", "feedback_cache", "todos"]

        for table in import_order:
            rows = data.get(table, [])
            if not rows:
                print(f"  ⚠ No data to import for {table}")
                continue

            try:
                # Get column count from first row
                placeholders = ", ".join(["%s"] * len(rows[0]))
                columns = self._get_column_names(table)

                insert_sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

                # Batch insert for performance
                execute_batch(cursor, insert_sql, rows, page_size=100)
                self.pg_conn.commit()

                print(f"  ✓ Imported {len(rows)} rows into {table}")
            except Exception as e:
                self.pg_conn.rollback()
                print(f"  ✗ Import failed for {table}: {e}")
                sys.exit(1)

    def _get_column_names(self, table: str) -> str:
        """Get column names for a table."""
        column_map = {
            "users": "id, email, password_hash, display_name, email_verified, verification_token_hash, verification_expires_at, created_at, updated_at",
            "analyses": "id, user_id, filename, code, feedback, score, timestamp",
            "feedback_cache": "id, analysis_id, critical_count, improvement_count, learning_count, good_count",
            "todos": "id, title, description, completed, created_at, updated_at"
        }
        return column_map.get(table, "*")

    def validate_counts(self, data: Dict[str, List[tuple]]) -> bool:
        """Validate row counts match between SQLite export and PostgreSQL."""
        print("[5/7] Validating row counts...")

        cursor = self.pg_conn.cursor()
        all_valid = True

        for table in ["users", "analyses", "feedback_cache", "todos"]:
            sqlite_count = len(data.get(table, []))

            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                pg_count = cursor.fetchone()[0]

                if sqlite_count == pg_count:
                    print(f"  ✓ {table}: {sqlite_count} rows (matched)")
                else:
                    print(f"  ✗ {table}: SQLite={sqlite_count}, PostgreSQL={pg_count} (MISMATCH)")
                    all_valid = False
            except Exception as e:
                print(f"  ✗ Validation failed for {table}: {e}")
                all_valid = False

        return all_valid

    def create_sequences(self):
        """Create sequences for auto-incrementing IDs if needed."""
        print("[6/7] Setting up sequences and constraints...")

        cursor = self.pg_conn.cursor()

        try:
            # Add any additional constraints or sequences here
            # Currently using TEXT IDs generated by application

            # Update statistics for query planner
            cursor.execute("ANALYZE")
            self.pg_conn.commit()

            print("  ✓ Database optimized")
        except Exception as e:
            self.pg_conn.rollback()
            print(f"  ⚠ Optimization warning: {e}")

    def close(self):
        """Close database connections."""
        if self.sqlite_conn:
            self.sqlite_conn.close()
        if self.pg_conn:
            self.pg_conn.close()

    def run_migration(self):
        """Execute the full migration process."""
        print(f"\n{'='*70}")
        print("SQLite to PostgreSQL Migration")
        print(f"{'='*70}\n")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        try:
            self.connect()
            data = self.export_data()
            self.create_schema()
            self.import_data(data)

            is_valid = self.validate_counts(data)
            self.create_sequences()

            print("\n[7/7] Migration summary:")
            print(f"  Total tables migrated: 4")
            print(f"  Total rows migrated: {sum(len(rows) for rows in data.values())}")
            print(f"  Validation: {'PASSED ✓' if is_valid else 'FAILED ✗'}")

            if is_valid:
                print(f"\n{'='*70}")
                print("✓ Migration completed successfully!")
                print(f"{'='*70}\n")
                print("Next steps:")
                print("1. Update your application's DATABASE_URL to point to PostgreSQL")
                print("2. Test application functionality thoroughly")
                print("3. Monitor performance and query execution")
                print("4. Keep SQLite backup until PostgreSQL is fully validated")
                return True
            else:
                print(f"\n{'='*70}")
                print("✗ Migration completed with validation errors")
                print(f"{'='*70}\n")
                print("Action required:")
                print("1. Review validation errors above")
                print("2. Check data integrity")
                print("3. Do NOT switch to PostgreSQL until validation passes")
                return False

        except Exception as e:
            print(f"\n✗ Migration failed: {e}")
            return False
        finally:
            self.close()


def validate_only(sqlite_path: str):
    """Print row counts from SQLite without migrating."""
    print(f"\n{'='*70}")
    print("SQLite Database Validation (No Migration)")
    print(f"{'='*70}\n")

    try:
        conn = sqlite3.connect(sqlite_path)
        cursor = conn.cursor()

        tables = ["users", "analyses", "feedback_cache", "todos"]
        print("Current row counts:\n")

        total_rows = 0
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  {table:20} {count:>8} rows")
                total_rows += count
            except sqlite3.OperationalError:
                print(f"  {table:20} (table not found)")

        print(f"\n  {'Total':20} {total_rows:>8} rows")

        conn.close()

        print(f"\n{'='*70}\n")

    except Exception as e:
        print(f"✗ Validation failed: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate AI Code Mentor database from SQLite to PostgreSQL"
    )
    parser.add_argument(
        "--sqlite",
        default="code_mentor.db",
        help="Path to SQLite database file (default: code_mentor.db)"
    )
    parser.add_argument(
        "--postgres",
        help="PostgreSQL connection URI (postgresql://user:pass@host:port/database)"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate SQLite data without migrating"
    )

    args = parser.parse_args()

    # Validate-only mode
    if args.validate_only:
        validate_only(args.sqlite)
        return

    # Full migration mode
    if not args.postgres:
        print("ERROR: --postgres argument is required for migration")
        print("\nExample:")
        print("  python migrate_to_postgres.py --sqlite code_mentor.db --postgres postgresql://user:pass@localhost:5432/code_mentor")
        sys.exit(1)

    if not os.path.exists(args.sqlite):
        print(f"ERROR: SQLite database not found: {args.sqlite}")
        sys.exit(1)

    # Confirm migration
    print(f"\nWARNING: This will DROP all existing PostgreSQL tables and recreate them!")
    print(f"SQLite source: {args.sqlite}")
    print(f"PostgreSQL target: {args.postgres.split('@')[1] if '@' in args.postgres else args.postgres}")

    response = input("\nProceed with migration? (yes/no): ").strip().lower()
    if response != "yes":
        print("Migration cancelled.")
        sys.exit(0)

    # Run migration
    migration = PostgreSQLMigration(args.sqlite, args.postgres)
    success = migration.run_migration()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
