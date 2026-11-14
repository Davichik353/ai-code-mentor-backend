"""Explicit operator-only reset of account data; never called by application startup."""
import argparse
import json
import os
import psycopg
from psycopg import sql

TABLES = (
    'users', 'analyses', 'feedback_cache', 'todos', 'analysis_quotas', 'ai_usage',
    'learning_profiles', 'learning_groups', 'learning_group_archives', 'learning_group_settings',
    'learning_members', 'learning_assignments', 'learning_hints', 'learning_submissions',
    'learning_submission_input_reports', 'learning_assignment_settings', 'learning_grades',
    'learning_drafts', 'learning_removed_members', 'learning_schools', 'learning_school_staff',
    'learning_school_groups', 'learning_school_invites', 'learning_school_library', 'support_tickets',
)

def reset(url):
    # Explicit table allowlist; no CASCADE into other schemas or unrelated tables.
    tables=sql.SQL(', ').join(sql.Identifier('mentor',t) for t in TABLES)
    with psycopg.connect(url,sslmode='require',connect_timeout=20) as c:
        c.execute("SET LOCAL lock_timeout='20s'")
        c.execute("SET LOCAL statement_timeout='60s'")
        c.execute(sql.SQL('LOCK TABLE {} IN ACCESS EXCLUSIVE MODE').format(tables))
        before={t:c.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier('mentor',t))).fetchone()[0] for t in TABLES}
        c.execute(sql.SQL('TRUNCATE TABLE {} RESTRICT').format(tables))
        after={t:c.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier('mentor',t))).fetchone()[0] for t in TABLES}
        if any(after.values()):raise RuntimeError('Reset verification failed; rolling back')
    # A separate connection verifies persistence, without repeating a deletion if new users registered.
    with psycopg.connect(url,sslmode='require',connect_timeout=20) as c:
        remaining=c.execute('SELECT COUNT(*) FROM mentor.users').fetchone()[0]
    return {'deleted_counts':before,'counts_at_commit':after,'users_after_commit':remaining}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm',required=True,choices=['DELETE_ALL_USERS'])
    parser.parse_args()
    url=os.getenv('DATABASE_URL','').strip()
    if not url:raise SystemExit('Database connection secret is missing; nothing deleted')
    try:
        print(json.dumps(reset(url)))
    except Exception as exc:
        # Do not log connection strings or driver messages containing credentials.
        raise SystemExit('Reset did not complete: '+type(exc).__name__) from None
