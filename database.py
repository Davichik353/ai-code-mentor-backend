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
            
            # Analyses table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    code TEXT NOT NULL,
                    feedback TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
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
            
            conn.commit()
            conn.close()
            print("Database initialized successfully")
        except Exception as e:
            print(f"Error initializing database: {e}")
            raise
    
    def save_analysis(self, code: str, filename: str, feedback: dict, score: int) -> str:
        """Save code analysis to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            analysis_id = f"analysis_{uuid.uuid4().hex[:12]}"
            feedback_json = json.dumps(feedback, ensure_ascii=False)
            timestamp = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT INTO analyses (id, filename, code, feedback, score, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (analysis_id, filename, code, feedback_json, score, timestamp))
            
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
    
    def get_analysis(self, analysis_id: str) -> Optional[Dict]:
        """Get specific analysis by ID"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM analyses WHERE id = ?', (analysis_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    "id": row["id"],
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
    
    def get_history(self, limit: int = 10) -> List[Dict]:
        """Get analysis history"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
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
    
    def delete_analysis(self, analysis_id: str) -> bool:
        """Delete analysis from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
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
