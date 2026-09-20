import sqlite3
import json
import os
from datetime import datetime
from typing import List, Optional, Dict
import uuid

class Database:
    def __init__(self, db_path: str = "code_mentor.db"):
        self.db_path = db_path
        self.connection = None
    
    def init_db(self):
        """Initialize database with tables"""
        try:
            conn = sqlite3.connect(self.db_path)
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
            conn = sqlite3.connect(self.db_path)
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
            conn = sqlite3.connect(self.db_path)
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
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('SELECT id, email, display_name, email_verified, created_at FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            conn.close()

            if row:
                user_dict = dict(row)
                # Calculate level and XP from analyses count
                stats_conn = sqlite3.connect(self.db_path)
                stats_cur = stats_conn.cursor()
                stats_cur.execute('SELECT COUNT(*) as count, AVG(score) as avg_score FROM analyses WHERE user_id = ?', (user_id,))
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

    def delete_user(self, user_id: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def verify_user_email(self, token_hash: str) -> Optional[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                '''SELECT * FROM users
                   WHERE verification_token_hash = ?
                   AND verification_expires_at > ?''',
                (token_hash, datetime.now().isoformat())
            ).fetchone()
            if not row:
                return None
            conn.execute(
                '''UPDATE users SET email_verified = 1,
                   verification_token_hash = NULL, verification_expires_at = NULL
                   WHERE id = ?''', (row["id"],)
            )
            conn.commit()
            return self.get_user_by_email(row["email"])
        finally:
            conn.close()
    
    def save_analysis(self, code: str, filename: str, feedback: dict, score: int, user_id: Optional[str] = None) -> str:
        """Save code analysis to database. user_id is optional — anonymous analyses are still supported."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            analysis_id = f"analysis_{uuid.uuid4().hex[:12]}"
            feedback_json = json.dumps(feedback, ensure_ascii=False)
            timestamp = datetime.now().isoformat()
            
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
            conn = sqlite3.connect(self.db_path)
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
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if user_id:
                cursor.execute('''
                    SELECT id, filename, code, score, timestamp, feedback
                    FROM analyses
                    WHERE user_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (user_id, limit))
            else:
                cursor.execute('''
                    SELECT id, filename, code, score, timestamp, feedback
                    FROM analyses
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

    def get_todos(self, status: Optional[str] = None) -> List[Dict]:
        """Get todos, optionally filtered by active or completed status."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            query = "SELECT * FROM todos"
            params = []
            if status in ("active", "completed"):
                query += " WHERE completed = ?"
                params.append(1 if status == "completed" else 0)
            query += " ORDER BY completed ASC, created_at DESC"
            rows = conn.execute(query, params).fetchall()
            return [dict(row) | {"completed": bool(row["completed"])} for row in rows]
        finally:
            conn.close()

    def create_todo(self, title: str, description: Optional[str] = None) -> Dict:
        """Create and return a todo item."""
        todo_id = f"todo_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                '''INSERT INTO todos (id, title, description, completed, created_at, updated_at)
                   VALUES (?, ?, ?, 0, ?, ?)''',
                (todo_id, title.strip(), description.strip() if description else None, now, now)
            )
            conn.commit()
            row = conn.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
            return {
                "id": row[0], "title": row[1], "description": row[2],
                "completed": bool(row[3]), "created_at": row[4], "updated_at": row[5]
            }
        finally:
            conn.close()

    def update_todo(self, todo_id: str, title: Optional[str] = None,
                    description: Optional[str] = None,
                    completed: Optional[bool] = None) -> Optional[Dict]:
        """Update supplied todo fields and return the updated item."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            current = conn.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
            if not current:
                return None
            new_title = title.strip() if title is not None else current["title"]
            new_description = description.strip() if description is not None else current["description"]
            new_completed = int(completed) if completed is not None else current["completed"]
            now = datetime.now().isoformat()
            conn.execute(
                '''UPDATE todos
                   SET title = ?, description = ?, completed = ?, updated_at = ?
                   WHERE id = ?''',
                (new_title, new_description, new_completed, now, todo_id)
            )
            conn.commit()
            row = conn.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
            return dict(row) | {"completed": bool(row["completed"])}
        finally:
            conn.close()

    def delete_todo(self, todo_id: str) -> bool:
        """Delete a todo item."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def delete_analysis(self, analysis_id: str, user_id: Optional[str] = None) -> bool:
        """Delete analysis from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if user_id:
                cursor.execute('DELETE FROM analyses WHERE id = ? AND user_id = ?', (analysis_id, user_id))
            else:
                cursor.execute('DELETE FROM analyses WHERE id = ?', (analysis_id,))
            cursor.execute('DELETE FROM feedback_cache WHERE analysis_id = ?', (analysis_id,))
            
            conn.commit()
            success = cursor.rowcount > 0
            conn.close()
            
            return success
        except Exception as e:
            print(f"Error deleting analysis: {e}")
            return False
    
    def get_progress_stats(self) -> Dict:
        """Get progress statistics"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get all scores
            cursor.execute('SELECT score FROM analyses ORDER BY timestamp ASC')
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
    
    def get_stats(self) -> Dict:
        """Get overall statistics"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Total analyses
            cursor.execute('SELECT COUNT(*) as count FROM analyses')
            total = cursor.fetchone()[0]
            
            # Average score
            cursor.execute('SELECT AVG(score) as avg_score FROM analyses')
            avg = cursor.fetchone()[0] or 0
            
            # Best score
            cursor.execute('SELECT MAX(score) as max_score FROM analyses')
            best = cursor.fetchone()[0] or 0
            
            # Feedback counts
            cursor.execute('''
                SELECT 
                    SUM(critical_count) as total_critical,
                    SUM(improvement_count) as total_improvements,
                    SUM(learning_count) as total_learning,
                    SUM(good_count) as total_good
                FROM feedback_cache
            ''')
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
