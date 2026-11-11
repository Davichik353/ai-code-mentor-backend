from pathlib import Path
import sqlite3
from storage import connect
from contextlib import closing
import json
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict
import uuid
from learning import init_learning_schema

class Database:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("DATABASE_PATH") or str(Path.home() / ".local/share/ai-code-mentor/code_mentor.db")
        parent = os.path.dirname(os.path.abspath(self.db_path))
        os.makedirs(parent, exist_ok=True)
        self.connection = None
    
    def init_db(self):
        """Initialize database with tables"""
        try:
            conn = connect(self.db_path)
            if getattr(conn, 'backend', '') == 'postgresql':
                conn.execute('CREATE SCHEMA IF NOT EXISTS mentor')
                conn.execute('REVOKE ALL ON SCHEMA mentor FROM PUBLIC')
            cursor = conn.cursor()
            
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    display_name TEXT,
                    email_verified INTEGER NOT NULL DEFAULT 0,
                    verification_token_hash TEXT,
                    verification_expires_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Analyses table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    filename TEXT NOT NULL,
                    code TEXT NOT NULL,
                    feedback TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Lightweight migration: if analyses table exists from before auth was
            # added, it won't have user_id yet. Add it if missing (SQLite-safe check).
            cursor.execute("PRAGMA table_info(analyses)")
            columns = [row[1] for row in cursor.fetchall()]
            if "user_id" not in columns:
                cursor.execute("ALTER TABLE analyses ADD COLUMN user_id TEXT")

            cursor.execute("PRAGMA table_info(users)")
            user_columns = [row[1] for row in cursor.fetchall()]
            if "email_verified" not in user_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
            if "verification_token_hash" not in user_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN verification_token_hash TEXT")
            if "verification_expires_at" not in user_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN verification_expires_at DATETIME")
            
            for column, definition in {
                "token_version": "INTEGER NOT NULL DEFAULT 0",
                "reset_token_hash": "TEXT", "reset_expires_at": "TEXT",
            }.items():
                if column not in user_columns:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_reset_hash ON users(reset_token_hash)")
            cursor.execute("CREATE TABLE IF NOT EXISTS analysis_quotas (scope TEXT NOT NULL, day TEXT NOT NULL, count INTEGER NOT NULL, PRIMARY KEY(scope, day))")
            cursor.execute("""CREATE TABLE IF NOT EXISTS ai_usage (
                id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                model TEXT NOT NULL, input_tokens INTEGER, output_tokens INTEGER,
                total_tokens INTEGER, outcome TEXT NOT NULL, created_at TEXT NOT NULL)""")

            # Feedback cache for quick lookup
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS feedback_cache (
                    id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL,
                    critical_count INTEGER DEFAULT 0,
                    improvement_count INTEGER DEFAULT 0,
                    learning_count INTEGER DEFAULT 0,
                    good_count INTEGER DEFAULT 0,
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS todos (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    completed INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute("PRAGMA table_info(todos)")
            if "user_id" not in {row[1] for row in cursor.fetchall()}:
                # Legacy tasks have no provable owner and remain inaccessible.
                cursor.execute("ALTER TABLE todos ADD COLUMN user_id TEXT REFERENCES users(id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_todos_user_id ON todos(user_id)")
            init_learning_schema(conn)
            conn.commit()
            conn.close()
            print("Database initialized successfully")
        except Exception as e:
            print(f"Error initializing database: {e}")
            raise
    
    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    def create_user(self, email: str, password_hash: str, display_name: Optional[str] = None,
                    verification_token_hash: Optional[str] = None,
                    verification_expires_at: Optional[str] = None,
                    email_verified: int = 0) -> Optional[str]:
        """Create a new user. Returns the new user's id, or None if email already exists."""
        try:
            conn = connect(self.db_path)
            cursor = conn.cursor()
            
            user_id = f"user_{uuid.uuid4().hex[:12]}"
            try:
                cursor.execute('''
                    INSERT INTO users
                    (id, email, password_hash, display_name, email_verified,
                     verification_token_hash, verification_expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, email.lower().strip(), password_hash, display_name, email_verified,
                      verification_token_hash, verification_expires_at))
                conn.commit()
                return user_id
            except sqlite3.IntegrityError:
                # UNIQUE constraint on email
                return None
            finally:
                conn.close()
        except Exception as e:
            print(f"Error creating user: {e}")
            return None
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Look up a user by email. Returns dict with id/email/password_hash/display_name, or None."""
        try:
            conn = connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM users WHERE email = ?', (email.lower().strip(),))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(row)
            return None
        except Exception as e:
            print(f"Error looking up user: {e}")
            return None
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """Look up a user by id. Returns dict without password_hash, or None."""
        try:
            conn = connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('SELECT id, email, display_name, email_verified, created_at, token_version FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            conn.close()

            if row:
                user_dict = dict(row)
                # Calculate level and XP from analyses count
                stats_conn = connect(self.db_path)
                stats_cur = stats_conn.cursor()
                stats_cur.execute('''
                    SELECT COUNT(*) as count, AVG(score) as avg_score
                    FROM analyses
                    WHERE user_id = ? AND feedback NOT LIKE '%AI analysis unavailable%'
                ''', (user_id,))
                stats = stats_cur.fetchone()
                analysis_count = stats[0] or 0
                avg_score = stats[1] or 0
                stats_conn.close()

                # Level formula: 1 + (analyses / 10), XP: analyses * 10 + avg_score
                user_dict['level'] = 1 + (analysis_count // 10)
                user_dict['xp_current'] = analysis_count * 10 + int(avg_score)
                user_dict['xp_needed'] = (user_dict['level'] + 1) * 1000

                return user_dict
            return None
        except Exception as e:
            print(f"Error looking up user: {e}")
            return None

    def update_display_name(self, user_id, display_name):
        conn = connect(self.db_path)
        try:
            conn.execute("UPDATE users SET display_name=? WHERE id=?", (display_name, user_id))
            conn.commit()
        finally:
            conn.close()

    def delete_user(self, user_id: str) -> bool:
        conn = connect(self.db_path)
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute('''
                DELETE FROM feedback_cache
                WHERE analysis_id IN (SELECT id FROM analyses WHERE user_id = ?)
            ''', (user_id,))
            conn.execute("DELETE FROM ai_usage WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM todos WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM analyses WHERE user_id = ?", (user_id,))
            cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def verify_user_email(self, token_hash: str, email: str) -> Optional[Dict]:
        conn = connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                '''SELECT * FROM users
                   WHERE verification_token_hash = ? AND email = ?
                   AND verification_expires_at > ?''',
                (token_hash, email, datetime.now().isoformat())
            ).fetchone()
            if not row:
                return None
            updated = conn.execute(
                '''UPDATE users SET email_verified = 1,
                   verification_token_hash = NULL, verification_expires_at = NULL
                   WHERE id = ? AND verification_token_hash = ?''', (row["id"], token_hash)
            )
            conn.commit()
            return self.get_user_by_email(row["email"]) if updated.rowcount == 1 else None
        finally:
            conn.close()
    
    def issue_password_reset(self, user_id, token_hash, expires):
        conn = connect(self.db_path)
        try:
            conn.execute("UPDATE users SET reset_token_hash=?, reset_expires_at=? WHERE id=?", (token_hash, expires, user_id))
            conn.commit()
        finally:
            conn.close()

    def reset_password(self, token_hash, password_hash):
        conn = connect(self.db_path)
        try:
            cursor = conn.execute("""UPDATE users SET password_hash=?, token_version=token_version+1,
                reset_token_hash=NULL, reset_expires_at=NULL
                WHERE reset_token_hash=? AND reset_expires_at>?""",
                (password_hash, token_hash, datetime.utcnow().isoformat()))
            conn.commit()
            return cursor.rowcount == 1
        finally:
            conn.close()

    def reserve_analysis_quota(self, user_id, user_limit, global_limit):
        """Atomic daily quotas persist across restarts and concurrent API workers."""
        import hashlib
        day = datetime.utcnow().date().isoformat()
        conn = connect(self.db_path)
        try:
            for scope, limit in [("all", global_limit), (hashlib.sha256(user_id.encode()).hexdigest(), user_limit)]:
                cursor = conn.execute("""INSERT INTO analysis_quotas(scope,day,count) VALUES(?,?,1)
                    ON CONFLICT(scope,day) DO UPDATE SET count=analysis_quotas.count+1 WHERE analysis_quotas.count<?""", (scope, day, limit))
                if cursor.rowcount != 1:
                    conn.rollback()
                    return False
            conn.execute("DELETE FROM analysis_quotas WHERE day < ?", ((datetime.utcnow().date() - timedelta(days=2)).isoformat(),))
            conn.commit()
            return True
        finally:
            conn.close()

    def record_ai_usage(self, user_id, usage):
        conn = connect(self.db_path)
        try:
            for row in usage:
                conn.execute("""INSERT INTO ai_usage(id,user_id,model,input_tokens,output_tokens,total_tokens,outcome,created_at)
                    VALUES(?,?,?,?,?,?,?,?)""", (uuid.uuid4().hex, user_id, row['model'], row['input_tokens'],
                    row['output_tokens'], row['total_tokens'], row['outcome'], datetime.utcnow().isoformat()))
            conn.commit()
        finally:
            conn.close()

    def save_analysis(self, code: str, filename: str, feedback: dict, score: int, user_id: Optional[str] = None) -> str:
        """Save code analysis to database. user_id is optional — anonymous analyses are still supported."""
        try:
            conn = connect(self.db_path)
            cursor = conn.cursor()
            
            analysis_id = f"analysis_{uuid.uuid4().hex[:12]}"
            feedback_json = json.dumps(feedback, ensure_ascii=False)
            timestamp = datetime.now(timezone.utc).isoformat()
            
            cursor.execute('''
                INSERT INTO analyses (id, user_id, filename, code, feedback, score, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (analysis_id, user_id, filename, code, feedback_json, score, timestamp))
            
            # Save feedback counts
            critical_count = len(feedback.get("critical", []))
            improvement_count = len(feedback.get("improvements", []))
            learning_count = len(feedback.get("learning", []))
            good_count = len(feedback.get("good", []))
            
            cursor.execute('''
                INSERT INTO feedback_cache (id, analysis_id, critical_count, improvement_count, learning_count, good_count)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (f"cache_{uuid.uuid4().hex[:12]}", analysis_id, critical_count, improvement_count, learning_count, good_count))
            
            conn.commit()
            conn.close()
            
            return analysis_id
        except Exception as e:
            print(f"Error saving analysis: {e}")
            raise
    
    def get_analysis(self, analysis_id: str, user_id: Optional[str] = None) -> Optional[Dict]:
        """Get specific analysis by ID"""
        try:
            conn = connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if user_id:
                cursor.execute('SELECT * FROM analyses WHERE id = ? AND user_id = ?', (analysis_id, user_id))
            else:
                cursor.execute('SELECT * FROM analyses WHERE id = ?', (analysis_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "filename": row["filename"],
                    "code": row["code"],
                    "feedback": json.loads(row["feedback"]),
                    "score": row["score"],
                    "timestamp": row["timestamp"]
                }
            return None
        except Exception as e:
            print(f"Error getting analysis: {e}")
            return None
    
    def get_history(self, limit: int = 10, user_id: Optional[str] = None) -> List[Dict]:
        """Get analysis history. If user_id is given, only that user's analyses are returned;
        otherwise all analyses (anonymous + everyone's) are returned, as before."""
        try:
            conn = connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if user_id:
                cursor.execute('''
                    SELECT id, filename, code, score, timestamp, feedback
                    FROM analyses
                    WHERE user_id = ? AND feedback NOT LIKE '%AI analysis unavailable%'
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (user_id, limit))
            else:
                cursor.execute('''
                    SELECT id, filename, code, score, timestamp, feedback
                    FROM analyses
                    WHERE feedback NOT LIKE '%AI analysis unavailable%'
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            history = []
            for row in rows:
                feedback = json.loads(row["feedback"])
                code_preview = row["code"][:50] + "..." if len(row["code"]) > 50 else row["code"]
                
                history.append({
                    "id": row["id"],
                    "filename": row["filename"],
                    "code_preview": code_preview,
                    "score": row["score"],
                    "timestamp": row["timestamp"],
                    "feedback_summary": feedback.get("summary", "No summary")
                })
            
            return history
        except Exception as e:
            print(f"Error getting history: {e}")
            return []

    def get_todos(self, user_id: str, status: Optional[str] = None) -> List[Dict]:
        with closing(connect(self.db_path)) as conn, conn:
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM todos WHERE user_id = ?"
            params = [user_id]
            if status in ("active", "completed"):
                query += " AND completed = ?"
                params.append(int(status == "completed"))
            rows = conn.execute(query + " ORDER BY completed ASC, created_at DESC", params)
            return [dict(row) | {"completed": bool(row["completed"])} for row in rows]

    def create_todo(self, user_id: str, title: str, description: Optional[str] = None) -> Dict:
        todo_id = f"todo_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        with closing(connect(self.db_path)) as conn, conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                """INSERT INTO todos (id, user_id, title, description, completed, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 0, ?, ?)""",
                (todo_id, user_id, title.strip(), description.strip() if description else None, now, now),
            )
            row = conn.execute("SELECT * FROM todos WHERE id = ? AND user_id = ?", (todo_id, user_id)).fetchone()
            return dict(row) | {"completed": bool(row["completed"])}

    def update_todo(self, user_id: str, todo_id: str, title: Optional[str] = None,
                    description: Optional[str] = None, completed: Optional[bool] = None) -> Optional[Dict]:
        with closing(connect(self.db_path)) as conn, conn:
            conn.row_factory = sqlite3.Row
            current = conn.execute("SELECT * FROM todos WHERE id = ? AND user_id = ?", (todo_id, user_id)).fetchone()
            if not current:
                return None
            conn.execute(
                """UPDATE todos SET title = ?, description = ?, completed = ?, updated_at = ?
                   WHERE id = ? AND user_id = ?""",
                (title.strip() if title is not None else current["title"],
                 description.strip() if description is not None else current["description"],
                 int(completed) if completed is not None else current["completed"],
                 datetime.now().isoformat(), todo_id, user_id),
            )
            row = conn.execute("SELECT * FROM todos WHERE id = ? AND user_id = ?", (todo_id, user_id)).fetchone()
            return dict(row) | {"completed": bool(row["completed"])}

    def delete_todo(self, user_id: str, todo_id: str) -> bool:
        with closing(connect(self.db_path)) as conn, conn:
            return conn.execute("DELETE FROM todos WHERE id = ? AND user_id = ?", (todo_id, user_id)).rowcount > 0

    def delete_analysis(self, analysis_id: str, user_id: Optional[str] = None) -> bool:
        """Delete analysis from database"""
        try:
            conn = connect(self.db_path)
            cursor = conn.cursor()
            
            if user_id:
                cursor.execute('SELECT 1 FROM analyses WHERE id = ? AND user_id = ?', (analysis_id, user_id))
            else:
                cursor.execute('SELECT 1 FROM analyses WHERE id = ?', (analysis_id,))
            if cursor.fetchone() is None:
                conn.close()
                return False
            cursor.execute('DELETE FROM feedback_cache WHERE analysis_id = ?', (analysis_id,))
            if user_id:
                cursor.execute('DELETE FROM analyses WHERE id = ? AND user_id = ?', (analysis_id, user_id))
            else:
                cursor.execute('DELETE FROM analyses WHERE id = ?', (analysis_id,))
            success = cursor.rowcount > 0
            conn.commit()
            conn.close()
            
            return success
        except Exception as e:
            print(f"Error deleting analysis: {e}")
            return False
    
    def get_progress_stats(self, user_id: Optional[str] = None) -> Dict:
        """Get progress statistics for one user, or all analyses when anonymous."""
        try:
            conn = connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get all scores
            if user_id:
                cursor.execute('''
                    SELECT score FROM analyses
                    WHERE user_id = ? AND feedback NOT LIKE '%AI analysis unavailable%'
                    ORDER BY timestamp ASC
                ''', (user_id,))
            else:
                cursor.execute('''
                    SELECT score FROM analyses
                    WHERE feedback NOT LIKE '%AI analysis unavailable%'
                    ORDER BY timestamp ASC
                ''')
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                return {
                    "total_analyses": 0,
                    "average_score": 0,
                    "best_score": 0,
                    "worst_score": 0,
                    "score_trend": [],
                    "improvements_by_category": {}
                }
            
            scores = [row["score"] for row in rows]
            
            return {
                "total_analyses": len(scores),
                "average_score": round(sum(scores) / len(scores), 1),
                "best_score": max(scores),
                "worst_score": min(scores),
                "score_trend": scores[-20:],  # Last 20
                "improvements_by_category": {
                    "consistency": "improving" if len(scores) > 1 and scores[-1] >= scores[-2] else "needs work"
                }
            }
        except Exception as e:
            print(f"Error getting progress stats: {e}")
            return {}
    
    def get_stats(self, user_id: str) -> Dict:
        """Get overall statistics"""
        try:
            conn = connect(self.db_path)
            cursor = conn.cursor()
            
            # Total analyses
            cursor.execute("SELECT COUNT(*) FROM analyses WHERE user_id = ? AND feedback NOT LIKE '%AI analysis unavailable%'", (user_id,))
            total = cursor.fetchone()[0]
            
            # Average score
            cursor.execute("SELECT AVG(score) FROM analyses WHERE user_id = ? AND feedback NOT LIKE '%AI analysis unavailable%'", (user_id,))
            avg = cursor.fetchone()[0] or 0
            
            # Best score
            cursor.execute("SELECT MAX(score) FROM analyses WHERE user_id = ? AND feedback NOT LIKE '%AI analysis unavailable%'", (user_id,))
            best = cursor.fetchone()[0] or 0
            
            # Feedback counts
            cursor.execute('''
                SELECT 
                    SUM(critical_count) as total_critical,
                    SUM(improvement_count) as total_improvements,
                    SUM(learning_count) as total_learning,
                    SUM(good_count) as total_good
                FROM feedback_cache
                JOIN analyses ON analyses.id = feedback_cache.analysis_id
                WHERE analyses.user_id = ? AND analyses.feedback NOT LIKE '%AI analysis unavailable%'
            ''', (user_id,))
            feedback_row = cursor.fetchone()
            
            conn.close()
            
            return {
                "total_analyses": total,
                "average_score": round(avg, 1),
                "best_score": best,
                "categories": {
                    "critical_issues": feedback_row[0] or 0,
                    "improvements": feedback_row[1] or 0,
                    "learning_topics": feedback_row[2] or 0,
                    "good_practices": feedback_row[3] or 0
                }
            }
        except Exception as e:
            print(f"Error getting stats: {e}")
            return {}
