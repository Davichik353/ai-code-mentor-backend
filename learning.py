"""SQLite learning domain. Browser reports are evidence to review, not trusted grades."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import secrets
import sqlite3
from storage import connect
from fastapi import HTTPException
from learning_content import TEMPLATES


def now():
    return datetime.now(timezone.utc).isoformat()


def init_learning_schema(conn):
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS learning_profiles (
            user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'learner', locale TEXT NOT NULL DEFAULT 'ru',
            bio TEXT NOT NULL DEFAULT '', public INTEGER NOT NULL DEFAULT 0,
            slug TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS learning_groups (
            id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL, description TEXT NOT NULL, join_code TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS learning_group_archives (
            group_id TEXT PRIMARY KEY REFERENCES learning_groups(id) ON DELETE CASCADE,
            archived_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS learning_members (
            group_id TEXT NOT NULL REFERENCES learning_groups(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            joined_at TEXT NOT NULL, PRIMARY KEY(group_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS learning_assignments (
            id TEXT PRIMARY KEY, group_id TEXT NOT NULL REFERENCES learning_groups(id) ON DELETE CASCADE,
            content TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS learning_hints (
            assignment_id TEXT NOT NULL REFERENCES learning_assignments(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            revealed INTEGER NOT NULL DEFAULT 0, reflection TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(assignment_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS learning_submissions (
            id TEXT PRIMARY KEY, assignment_id TEXT NOT NULL REFERENCES learning_assignments(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code TEXT NOT NULL, code_hash TEXT NOT NULL, results TEXT NOT NULL,
            tests_passed INTEGER NOT NULL, explanation TEXT NOT NULL,
            changed_code TEXT NOT NULL, change_explanation TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending_review', feedback TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, reviewed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_learning_groups_owner ON learning_groups(owner_id);
        CREATE INDEX IF NOT EXISTS idx_learning_members_user ON learning_members(user_id);
        CREATE INDEX IF NOT EXISTS idx_learning_assignments_group ON learning_assignments(group_id);
        CREATE INDEX IF NOT EXISTS idx_learning_submissions_user ON learning_submissions(user_id);
        CREATE INDEX IF NOT EXISTS idx_learning_submissions_assignment ON learning_submissions(assignment_id);
    ''')


def catalog_metadata(content):
    """Enrich older assignment snapshots without modifying their stored content."""
    current = TEMPLATES.get(content.get('id'), {})
    defaults = {
        'category': 'basics', 'category_title': {'ru': 'Основы', 'uz': 'Asoslar'},
        'difficulty': 'beginner', 'difficulty_title': {'ru': 'Новичок', 'uz': 'Boshlovchi'},
    }
    return {key: content.get(key) or current.get(key) or value for key, value in defaults.items()}


class Learning:
    def __init__(self, path):
        self.path = path

    @contextmanager
    def connect(self):
        conn = connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def profile(self, conn, user_id):
        conn.execute('INSERT OR IGNORE INTO learning_profiles (user_id, slug) VALUES (?, ?)',
                     (user_id, secrets.token_urlsafe(18)))
        return dict(conn.execute('SELECT * FROM learning_profiles WHERE user_id=?', (user_id,)).fetchone())

    def get_profile(self, user_id):
        with self.connect() as c:
            return self.profile(c, user_id)

    def update_profile(self, user_id, values):
        with self.connect() as c:
            self.profile(c, user_id)
            # Teacher is a self-service workspace, with no authority outside owned groups.
            c.execute('UPDATE learning_profiles SET role=?, locale=?, bio=?, public=? WHERE user_id=?',
                      (values.role, values.locale, values.bio.strip(), int(values.portfolio_public), user_id))
            return self.profile(c, user_id)

    def group(self, c, group_id, user_id, owner_only=False):
        row = c.execute('SELECT * FROM learning_groups WHERE id=?', (group_id,)).fetchone()
        if not row or (row['owner_id'] != user_id and (owner_only or not c.execute(
            'SELECT 1 FROM learning_members WHERE group_id=? AND user_id=?', (group_id, user_id)).fetchone())):
            raise HTTPException(404, 'Group not found')
        result = dict(row)
        result['archived'] = bool(c.execute('SELECT 1 FROM learning_group_archives WHERE group_id=?', (group_id,)).fetchone())
        return result

    @staticmethod
    def require_active(group):
        if group['archived']:
            raise HTTPException(409, 'Group is archived')

    def set_archived(self, group_id, user_id, archived):
        with self.connect() as c:
            self.group(c, group_id, user_id, owner_only=True)
            if archived:
                c.execute('INSERT OR IGNORE INTO learning_group_archives VALUES (?, ?)', (group_id, now()))
            else:
                c.execute('DELETE FROM learning_group_archives WHERE group_id=?', (group_id,))
            return {'id': group_id, 'archived': archived}

    def create_group(self, user_id, data):
        with self.connect() as c:
            if self.profile(c, user_id)['role'] != 'teacher':
                raise HTTPException(403, 'Choose teacher workspace first')
            if c.execute('SELECT COUNT(*) FROM learning_groups WHERE owner_id=?', (user_id,)).fetchone()[0] >= 20:
                raise HTTPException(409, 'Group limit reached')
            group_id = secrets.token_hex(12)
            c.execute('INSERT INTO learning_groups VALUES (?, ?, ?, ?, ?, ?)',
                      (group_id, user_id, data.title.strip(), data.description.strip(), secrets.token_urlsafe(9), now()))
            return self.group(c, group_id, user_id)

    def groups(self, user_id):
        with self.connect() as c:
            rows = c.execute('''SELECT g.*, EXISTS(SELECT 1 FROM learning_group_archives ar WHERE ar.group_id=g.id) AS archived, (SELECT COUNT(*) FROM learning_members WHERE group_id=g.id) AS member_count
                FROM learning_groups g WHERE owner_id=? OR EXISTS
                (SELECT 1 FROM learning_members m WHERE m.group_id=g.id AND m.user_id=?) ORDER BY created_at DESC''', (user_id, user_id))
            result = []
            for row in rows:
                item = dict(row)
                item['is_owner'] = item['owner_id'] == user_id
                item['can_manage'] = item['is_owner']
                if not item['is_owner']:
                    item.pop('join_code')
                result.append(item)
            return result

    def join(self, user_id, code):
        with self.connect() as c:
            row = c.execute('SELECT id, owner_id FROM learning_groups WHERE join_code=?', (code.strip(),)).fetchone()
            if not row:
                raise HTTPException(404, 'Join code not found')
            if c.execute('SELECT 1 FROM learning_group_archives WHERE group_id=?', (row['id'],)).fetchone():
                raise HTTPException(409, 'Group is archived')
            if row['owner_id'] != user_id:
                c.execute('INSERT OR IGNORE INTO learning_members VALUES (?, ?, ?)', (row['id'], user_id, now()))
            return {'id': row['id']}

    def leave(self, group_id, user_id):
        with self.connect() as c:
            group = self.group(c, group_id, user_id)
            if group['owner_id'] == user_id:
                raise HTTPException(409, 'Group owner cannot leave')
            # Keep submitted work for teacher review and a possible later rejoin.
            c.execute('DELETE FROM learning_members WHERE group_id=? AND user_id=?',
                      (group_id, user_id))
            return {'left': True}

    def group_detail(self, group_id, user_id):
        with self.connect() as c:
            group = self.group(c, group_id, user_id)
            owner = group['owner_id'] == user_id
            group['is_owner'] = owner
            group['can_manage'] = owner
            if not owner:
                group.pop('join_code')
            group['assignments'] = []
            for row in c.execute('SELECT * FROM learning_assignments WHERE group_id=? ORDER BY created_at DESC', (group_id,)):
                content = json.loads(row['content'])
                item = {'id': row['id'], 'template_id': content.get('id'), 'title': content['title'], 'language': content['language']}
                item.update(catalog_metadata(content))
                group['assignments'].append(item)
            group['member_count'] = c.execute('SELECT COUNT(*) FROM learning_members WHERE group_id=?', (group_id,)).fetchone()[0]
            teacher = c.execute('SELECT display_name FROM users WHERE id=?', (group['owner_id'],)).fetchone()
            group['teacher_name'] = teacher['display_name'] if teacher else None
            if not owner:
                group['my_submissions'] = [dict(r) for r in c.execute('''SELECT s.id, s.assignment_id, s.status, s.tests_passed, s.created_at
                    FROM learning_submissions s JOIN learning_assignments a ON a.id=s.assignment_id
                    WHERE a.group_id=? AND s.user_id=? ORDER BY s.created_at DESC, s.id DESC''', (group_id, user_id))]
            if owner:
                group['members'] = [dict(r) for r in c.execute('''SELECT u.id, u.display_name FROM learning_members m
                    JOIN users u ON u.id=m.user_id WHERE group_id=? ORDER BY joined_at''', (group_id,))]
                reports = [dict(r) for r in c.execute('''SELECT s.id, s.user_id, u.display_name, s.assignment_id,
                    s.tests_passed, s.status, s.results, s.created_at FROM learning_submissions s
                    JOIN learning_assignments a ON a.id=s.assignment_id JOIN users u ON u.id=s.user_id
                    WHERE a.group_id=? ORDER BY s.created_at DESC''', (group_id,))]
                # Latest attempt per learner/assignment prevents repeated attempts inflating the class picture.
                latest = {}
                for r in reports:
                    latest.setdefault((r['user_id'], r['assignment_id']), r)
                failures = {}
                for r in latest.values():
                    for index, case in enumerate(json.loads(r['results'])):
                        if not case['passed']:
                            key = (r['assignment_id'], index + 1)
                            failures[key] = failures.get(key, 0) + 1
                group['summary'] = {'attempts': len(reports), 'learners_submitted': len({r['user_id'] for r in reports}),
                                    'approved': sum(r['status'] == 'approved' for r in latest.values()),
                                    'common_failures': [{'assignment_id': a, 'case': i, 'learners': count} for (a, i), count in failures.items()]}
                group['submissions'] = [{k: v for k, v in r.items() if k != 'results'} for r in reports]
            return group

    def assign(self, group_id, user_id, template_id):
        if template_id not in TEMPLATES:
            raise HTTPException(422, 'Unknown exercise')
        with self.connect() as c:
            self.require_active(self.group(c, group_id, user_id, owner_only=True))
            for row in c.execute('SELECT content FROM learning_assignments WHERE group_id=?', (group_id,)):
                if json.loads(row['content']).get('id') == template_id:
                    raise HTTPException(409, 'Exercise already assigned to this group')
            if c.execute('SELECT COUNT(*) FROM learning_assignments WHERE group_id=?', (group_id,)).fetchone()[0] >= 100:
                raise HTTPException(409, 'Assignment limit reached')
            item_id = secrets.token_hex(12)
            c.execute('INSERT INTO learning_assignments VALUES (?, ?, ?, ?)',
                      (item_id, group_id, json.dumps(TEMPLATES[template_id], ensure_ascii=False), now()))
            return {'id': item_id}

    def assignment(self, c, item_id, user_id):
        row = c.execute('SELECT * FROM learning_assignments WHERE id=?', (item_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Assignment not found')
        group = self.group(c, row['group_id'], user_id)
        return dict(row), json.loads(row['content']), group

    def detail(self, item_id, user_id):
        with self.connect() as c:
            row, content, group = self.assignment(c, item_id, user_id)
            progress = c.execute('SELECT revealed FROM learning_hints WHERE assignment_id=? AND user_id=?', (item_id, user_id)).fetchone()
            revealed = progress['revealed'] if progress else 0
            result = {k: v for k, v in content.items() if k not in ('solution', 'hints', 'id')}
            result.update(catalog_metadata(content))
            result.update(id=item_id, group_id=group['id'], is_owner=group['owner_id'] == user_id,
                          can_manage=group['owner_id'] == user_id, archived=group['archived'],
                          can_submit=group['owner_id'] != user_id and not group['archived'],
                          hints=content['hints'][:revealed], hint_count=len(content['hints']),
                          submissions=[self.serialize(r) for r in c.execute('SELECT * FROM learning_submissions WHERE assignment_id=? AND user_id=? ORDER BY created_at DESC', (item_id, user_id))])
            return result

    def hint(self, item_id, user_id):
        with self.connect() as c:
            _, content, group = self.assignment(c, item_id, user_id)
            if group['owner_id'] == user_id:
                raise HTTPException(403, 'Hints are for learners')
            c.execute('INSERT OR IGNORE INTO learning_hints (assignment_id, user_id) VALUES (?, ?)', (item_id, user_id))
            c.execute('UPDATE learning_hints SET revealed=MIN(revealed+1, ?) WHERE assignment_id=? AND user_id=?', (len(content['hints']), item_id, user_id))
            count = c.execute('SELECT revealed FROM learning_hints WHERE assignment_id=? AND user_id=?', (item_id, user_id)).fetchone()[0]
            return {'hints': content['hints'][:count], 'hint_count': len(content['hints'])}

    def solution(self, item_id, user_id, reflection):
        with self.connect() as c:
            _, content, group = self.assignment(c, item_id, user_id)
            progress = c.execute('SELECT revealed FROM learning_hints WHERE assignment_id=? AND user_id=?', (item_id, user_id)).fetchone()
            if group['owner_id'] != user_id and (not progress or progress[0] < len(content['hints'])):
                raise HTTPException(409, 'Read the progressive hints before requesting the example')
            c.execute('UPDATE learning_hints SET reflection=? WHERE assignment_id=? AND user_id=?', (reflection.strip(), item_id, user_id))
            return {'solution': content['solution']}

    @staticmethod
    def serialize(row):
        result = dict(row)
        result['results'] = json.loads(result['results'])
        result['tests_passed'] = bool(result['tests_passed'])
        result['verification'] = 'browser_report_unverified'
        return result

    def submit(self, item_id, user_id, data):
        with self.connect() as c:
            _, content, group = self.assignment(c, item_id, user_id)
            self.require_active(group)
            if group['owner_id'] == user_id:
                raise HTTPException(403, 'Teacher cannot submit to own assignment')
            if len(data.results) != len(content['tests']):
                raise HTTPException(422, 'Report every test case')
            if data.changed_code.strip() == data.code.strip():
                raise HTTPException(422, 'Mini-defense requires a changed version of the code')
            if c.execute('SELECT COUNT(*) FROM learning_submissions WHERE assignment_id=? AND user_id=?', (item_id, user_id)).fetchone()[0] >= 50:
                raise HTTPException(409, 'Submission limit reached')
            reports = []
            for expected, actual in zip(content['tests'], data.results):
                reports.append({'stdout': actual.stdout, 'error': actual.error,
                                'passed': not actual.error and actual.stdout.strip() == expected['expected_stdout'].strip()})
            submission_id = secrets.token_hex(12)
            c.execute('''INSERT INTO learning_submissions
                (id, assignment_id, user_id, code, code_hash, results, tests_passed, explanation, changed_code, change_explanation, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (submission_id, item_id, user_id, data.code, hashlib.sha256(data.code.encode()).hexdigest(),
                       json.dumps(reports, ensure_ascii=False), int(all(r['passed'] for r in reports)),
                       data.explanation.strip(), data.changed_code, data.change_explanation.strip(), now()))
            return self.serialize(c.execute('SELECT * FROM learning_submissions WHERE id=?', (submission_id,)).fetchone())

    def submission(self, submission_id, user_id):
        with self.connect() as c:
            row = c.execute('SELECT * FROM learning_submissions WHERE id=?', (submission_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Submission not found')
            _, content, group = self.assignment(c, row['assignment_id'], user_id)
            if row['user_id'] != user_id and group['owner_id'] != user_id:
                raise HTTPException(404, 'Submission not found')
            result = self.serialize(row)
            result.update(title=content['title'], defense_questions=content['defense_questions'], change=content['change'],
                          tests=content['tests'], group_id=group['id'], is_owner=group['owner_id'] == user_id,
                          can_manage=group['owner_id'] == user_id)
            return result

    def review(self, submission_id, user_id, data):
        with self.connect() as c:
            row = c.execute('SELECT * FROM learning_submissions WHERE id=?', (submission_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Submission not found')
            self.assignment(c, row['assignment_id'], user_id)
            group_id = c.execute('SELECT group_id FROM learning_assignments WHERE id=?', (row['assignment_id'],)).fetchone()[0]
            self.group(c, group_id, user_id, owner_only=True)
            if row['user_id'] == user_id:
                raise HTTPException(403, 'Cannot review your own work')
            if data.decision == 'approved' and not row['tests_passed']:
                raise HTTPException(409, 'Cannot approve failing tests')
            c.execute('UPDATE learning_submissions SET status=?, feedback=?, reviewed_at=? WHERE id=?',
                      (data.decision, data.feedback.strip(), now(), submission_id))
            return {'id': submission_id, 'status': data.decision}

    def portfolio(self, user_id=None, slug=None):
        with self.connect() as c:
            if slug:
                profile = c.execute('SELECT * FROM learning_profiles WHERE slug=? AND public=1', (slug,)).fetchone()
                if not profile:
                    raise HTTPException(404, 'Portfolio not found')
                profile = dict(profile)
                user_id = profile['user_id']
            else:
                profile = self.profile(c, user_id)
            user = c.execute('SELECT display_name FROM users WHERE id=?', (user_id,)).fetchone()
            if not user:
                raise HTTPException(404, 'Portfolio not found')
            # One item per approved assignment; code, answers, group data and email are never public.
            items = []
            seen = set()
            for row in c.execute('''SELECT s.assignment_id, s.reviewed_at, a.content FROM learning_submissions s
                JOIN learning_assignments a ON a.id=s.assignment_id WHERE s.user_id=? AND s.status='approved'
                ORDER BY s.reviewed_at DESC''', (user_id,)):
                if row['assignment_id'] in seen:
                    continue
                seen.add(row['assignment_id'])
                content = json.loads(row['content'])
                items.append({'title': content['title'], 'language': content['language'], 'reviewed_at': row['reviewed_at'], 'verification': 'teacher_reviewed'})
            return {'display_name': user['display_name'] or 'Learner', 'bio': profile['bio'],
                    'public': bool(profile['public']), 'slug': profile['slug'], 'projects': items,
                    'skills': sorted({i['language'] for i in items}), 'completed': len(items)}
