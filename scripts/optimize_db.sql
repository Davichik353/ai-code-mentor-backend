-- Database Optimization Script for AI Code Mentor
-- Run this script to optimize SQLite performance before PostgreSQL migration

-- ============================================================================
-- 1. INDEXES ON FREQUENTLY QUERIED COLUMNS
-- ============================================================================

-- Users table: Email lookups are frequent during authentication
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Analyses table: User-scoped queries are the primary access pattern
CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id);

-- Analyses table: Timestamp ordering for history views
CREATE INDEX IF NOT EXISTS idx_analyses_timestamp ON analyses(timestamp DESC);

-- Composite index: Optimizes the most common query pattern (user history)
CREATE INDEX IF NOT EXISTS idx_analyses_user_timestamp ON analyses(user_id, timestamp DESC);

-- Feedback cache: Quick lookup by analysis ID
CREATE INDEX IF NOT EXISTS idx_feedback_cache_analysis_id ON feedback_cache(analysis_id);

-- Todos table: Filter by completion status
CREATE INDEX IF NOT EXISTS idx_todos_completed ON todos(completed);

-- ============================================================================
-- 2. QUERY PATTERN ANALYSIS
-- ============================================================================

-- Enable query planner analysis
ANALYZE;

-- View current query plans (run manually to verify index usage)
-- EXPLAIN QUERY PLAN SELECT * FROM analyses WHERE user_id = 'user_abc' ORDER BY timestamp DESC LIMIT 10;
-- EXPLAIN QUERY PLAN SELECT * FROM users WHERE email = 'user@example.com';
-- EXPLAIN QUERY PLAN SELECT * FROM todos WHERE completed = 0 ORDER BY created_at DESC;

-- ============================================================================
-- 3. QUERY OPTIMIZATION SUGGESTIONS
-- ============================================================================

/*
QUERY OPTIMIZATION GUIDELINES:

1. USE INDEXED COLUMNS IN WHERE CLAUSES
   - Always filter by user_id when fetching analyses
   - Use timestamp DESC for ordering history
   - Query todos by completed status

2. AVOID FUNCTIONS ON INDEXED COLUMNS
   BAD:  WHERE LOWER(email) = 'user@example.com'
   GOOD: WHERE email = 'user@example.com' (email stored lowercase)

3. USE LIMIT FOR PAGINATION
   - Always use LIMIT with OFFSET for pagination
   - Consider cursor-based pagination for large datasets

4. BATCH INSERTS FOR BULK OPERATIONS
   - Use transactions for multiple inserts
   - Consider prepared statements for repeated operations

5. JSON HANDLING
   - Feedback stored as JSON text - parse only when needed
   - Consider extracting frequently queried JSON fields to columns

EXAMPLE OPTIMIZED QUERIES:

-- Get user's recent analyses (uses idx_analyses_user_timestamp)
SELECT id, filename, score, timestamp
FROM analyses
WHERE user_id = ?
ORDER BY timestamp DESC
LIMIT 10;

-- Get user by email (uses idx_users_email)
SELECT id, email, display_name
FROM users
WHERE email = ?;

-- Get active todos (uses idx_todos_completed)
SELECT * FROM todos
WHERE completed = 0
ORDER BY created_at DESC;
*/

-- ============================================================================
-- 4. CONNECTION POOLING CONFIGURATION (PostgreSQL Migration)
-- ============================================================================

/*
POSTGRESQL CONNECTION POOLING (PgBouncer):

Recommended configuration for production:

[databases]
code_mentor = host=localhost port=5432 dbname=code_mentor

[pgbouncer]
# Connection pool settings
pool_mode = transaction
max_client_conn = 100
default_pool_size = 20
min_pool_size = 5
reserve_pool_size = 5
reserve_pool_timeout = 3

# Performance tuning
server_reset_query = DISCARD ALL
server_check_query = SELECT 1
server_check_delay = 30

# Timeouts
server_connect_timeout = 15
server_idle_timeout = 600
server_lifetime = 3600
client_idle_timeout = 0
client_login_timeout = 60

# Logging
log_connections = 0
log_disconnections = 0
log_pooler_errors = 1

# Admin settings
admin_users = postgres
stats_users = postgres

PYTHON APPLICATION CONFIG (SQLAlchemy):

from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    "postgresql://user:pass@localhost:5432/code_mentor",
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False
)

ASYNC SUPPORT (asyncpg):

import asyncpg

pool = await asyncpg.create_pool(
    host='localhost',
    port=5432,
    user='user',
    password='password',
    database='code_mentor',
    min_size=5,
    max_size=20,
    command_timeout=60
)
*/

-- ============================================================================
-- 5. DATABASE MAINTENANCE
-- ============================================================================

-- Rebuild database file (reclaims space, defragments)
VACUUM;

-- Update statistics for query planner
ANALYZE;

-- Check integrity
PRAGMA integrity_check;

-- ============================================================================
-- 6. PERFORMANCE MONITORING QUERIES
-- ============================================================================

/*
Run these queries periodically to monitor database health:

-- Table sizes
SELECT
    name as table_name,
    (pgsize / 1024 / 1024) as size_mb
FROM dbstat
GROUP BY name
ORDER BY pgsize DESC;

-- Index usage (SQLite)
PRAGMA index_list('analyses');
PRAGMA index_info('idx_analyses_user_timestamp');

-- Query performance (enable with PRAGMA profile = on;)
PRAGMA profile = on;

-- Lock status
PRAGMA lock_status;
*/

-- ============================================================================
-- 7. EXPECTED PERFORMANCE IMPROVEMENTS
-- ============================================================================

/*
WITH INDEXES:
- User email lookup: 50-100x faster (O(log n) vs O(n))
- Analysis history query: 10-50x faster (uses composite index)
- Todo filtering: 5-10x faster (index on completed)

WITH CONNECTION POOLING (PostgreSQL):
- Connection overhead: 90% reduction (reused connections)
- Concurrent requests: 5-10x improvement
- Memory usage: 50% reduction (shared connections)

MIGRATION TIMELINE:
1. Development: Apply indexes, test queries (1 day)
2. Staging: Run performance baseline, validate improvements (1 day)
3. Production: Schedule migration window (4-6 hours)
   - Export SQLite data
   - Set up PostgreSQL + PgBouncer
   - Import data
   - Validate counts
   - Switch application
   - Monitor performance

WHEN TO USE POSTGRESQL:
- User count > 1000
- Concurrent users > 50
- Database size > 500MB
- Need for advanced features (full-text search, JSONB, etc.)
- Multi-server deployment
*/
