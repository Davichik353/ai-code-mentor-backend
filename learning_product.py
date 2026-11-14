"""Classroom lifecycle, durable drafts and school ownership. No code execution here."""
import csv
import io
import json
import secrets
from datetime import datetime, timezone
from fastapi import HTTPException


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def init_product_schema(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS learning_assignment_settings (
        assignment_id TEXT PRIMARY KEY REFERENCES learning_assignments(id) ON DELETE CASCADE,
        due_at TEXT, allow_late INTEGER NOT NULL DEFAULT 1,
        hints_allowed INTEGER NOT NULL DEFAULT 1, solution_allowed INTEGER NOT NULL DEFAULT 1,
        server_check INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS learning_grades (
        submission_id TEXT PRIMARY KEY REFERENCES learning_submissions(id) ON DELETE CASCADE,
        score INTEGER, verification TEXT NOT NULL DEFAULT 'browser_report_unverified'
    );
    CREATE TABLE IF NOT EXISTS learning_drafts (
        assignment_id TEXT NOT NULL REFERENCES learning_assignments(id) ON DELETE CASCADE,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        payload TEXT NOT NULL, revision INTEGER NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY(assignment_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS learning_removed_members (
        group_id TEXT NOT NULL REFERENCES learning_groups(id) ON DELETE CASCADE,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        PRIMARY KEY(group_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS learning_schools (
        id TEXT PRIMARY KEY, title TEXT NOT NULL,
        admin_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS learning_school_staff (
        school_id TEXT NOT NULL REFERENCES learning_schools(id) ON DELETE CASCADE,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        PRIMARY KEY(school_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS learning_school_groups (
        group_id TEXT PRIMARY KEY REFERENCES learning_groups(id) ON DELETE CASCADE,
        school_id TEXT NOT NULL REFERENCES learning_schools(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS learning_school_invites (
        code TEXT PRIMARY KEY, school_id TEXT NOT NULL REFERENCES learning_schools(id) ON DELETE CASCADE,
        expires_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS learning_school_library (
        id TEXT PRIMARY KEY, school_id TEXT NOT NULL REFERENCES learning_schools(id) ON DELETE CASCADE,
        content TEXT NOT NULL, created_at TEXT NOT NULL
    );
    ''')


class ProductFeatures:
    def settings(self, c, item_id):
        row = c.execute('SELECT * FROM learning_assignment_settings WHERE assignment_id=?', (item_id,)).fetchone()
        return dict(row) if row else dict(due_at=None, allow_late=True, hints_allowed=True, solution_allowed=True, server_check=False)

    def assignment_settings(self, item_id, user_id, data):
        from judge import configured
        with self.connect() as c:
            _, _, group = self.assignment(c, item_id, user_id)
            self.require_active(self.group(c, group['id'], user_id, owner_only=True))
            if data.server_check and not configured():
                raise HTTPException(503, 'Judge unavailable')
            # Never reveal tests previously protected by server mode, even during an outage.
            if self.settings(c, item_id)['server_check'] and not data.server_check:
                raise HTTPException(409, 'Server checking cannot be disabled')
            c.execute('INSERT OR IGNORE INTO learning_assignment_settings (assignment_id) VALUES (?)', (item_id,))
            c.execute('''UPDATE learning_assignment_settings SET due_at=?,allow_late=?,hints_allowed=?,solution_allowed=?,server_check=? WHERE assignment_id=?''',
                      (data.due_at.astimezone(timezone.utc).isoformat() if data.due_at else None, int(data.allow_late), int(data.hints_allowed), int(data.solution_allowed), int(data.server_check), item_id))
            return self.settings(c, item_id)

    def remove_member(self, group_id, user_id, member_id, restore=False):
        with self.connect() as c:
            group = self.group(c, group_id, user_id, owner_only=True)
            self.require_active(group)
            if member_id == group['owner_id']:
                raise HTTPException(409, 'Cannot remove teacher')
            if restore:
                c.execute('DELETE FROM learning_removed_members WHERE group_id=? AND user_id=?', (group_id, member_id))
            else:
                if not c.execute('SELECT 1 FROM learning_members WHERE group_id=? AND user_id=?', (group_id,member_id)).fetchone():
                    raise HTTPException(404, 'Member not found')
                c.execute('INSERT OR IGNORE INTO learning_removed_members VALUES (?,?)', (group_id,member_id))
                c.execute('DELETE FROM learning_members WHERE group_id=? AND user_id=?', (group_id,member_id))
            return {'ok':True}

    def rotate_invite(self, group_id, user_id):
        with self.connect() as c:
            self.require_active(self.group(c, group_id, user_id, owner_only=True))
            code=secrets.token_urlsafe(18)
            c.execute('UPDATE learning_groups SET join_code=? WHERE id=?',(code,group_id))
            return {'join_code':code}

    def draft(self, item_id, user_id, data=None):
        with self.connect() as c:
            _,_,group=self.assignment(c,item_id,user_id)
            if group['owner_id']==user_id:
                raise HTTPException(403,'Drafts are for learners')
            if data is not None:
                self.require_active(group)
                c.execute('UPDATE learning_assignments SET created_at=created_at WHERE id=?',(item_id,))
            row=c.execute('SELECT * FROM learning_drafts WHERE assignment_id=? AND user_id=?',(item_id,user_id)).fetchone()
            if data is not None:
                if data.revision!=(row['revision'] if row else 0):
                    raise HTTPException(409,'Draft conflict')
                payload=data.payload.model_dump()
                if row:
                    old=json.loads(row['payload'])
                    payload['codePasteDetected']='true' if 'true' in (old.get('codePasteDetected'),payload['codePasteDetected']) else 'false'
                    c.execute('UPDATE learning_drafts SET payload=?,revision=?,updated_at=? WHERE assignment_id=? AND user_id=?',
                              (json.dumps(payload),data.revision+1,utcnow(),item_id,user_id))
                else:
                    c.execute('INSERT INTO learning_drafts VALUES (?,?,?,?,?)',(item_id,user_id,json.dumps(payload),1,utcnow()))
                row=c.execute('SELECT * FROM learning_drafts WHERE assignment_id=? AND user_id=?',(item_id,user_id)).fetchone()
            return {'payload':json.loads(row['payload']), 'revision':row['revision'],'updated_at':row['updated_at']} if row else {'payload':{},'revision':0,'updated_at':None}

    def journal_csv(self, group_id,user_id):
        with self.connect() as c:
            self.group(c,group_id,user_id,owner_only=True)
        group=self.group_detail(group_id,user_id)
        latest={}
        for report in group['submissions']:
            latest.setdefault((report['user_id'],report['assignment_id']),report)
        out=io.StringIO(); writer=csv.writer(out,delimiter=';')
        def cell(value):
            text=str(value or '')
            return "'"+text if text.lstrip().startswith(('=','+','-','@','\t','\r')) else text
        writer.writerow(['Ученик','Задание','Статус','Балл / 100','Сдано (UTC)','Срок (UTC)','Опоздание','Проверка'])
        for member in group['members']:
            for assignment in group['assignments']:
                work=latest.get((member['id'],assignment['id']),{})
                title=assignment['title']; title=title.get('ru','') if isinstance(title,dict) else title
                writer.writerow([cell(member['display_name']),cell(title),work.get('status','not_submitted'),work.get('score',''),
                                 work.get('created_at',''),assignment.get('due_at') or '', 'Да' if work.get('late') else '',work.get('verification','')])
        return '\ufeff'+out.getvalue()

    def school(self,c,school_id,user_id,admin=False):
        row=c.execute('SELECT * FROM learning_schools WHERE id=?',(school_id,)).fetchone()
        if not row or (row['admin_id']!=user_id and (admin or not c.execute('SELECT 1 FROM learning_school_staff WHERE school_id=? AND user_id=?',(school_id,user_id)).fetchone())):
            raise HTTPException(404,'School not found')
        return dict(row)

    def schools(self,user_id):
        with self.connect() as c:
            return [dict(r) for r in c.execute('SELECT * FROM learning_schools WHERE admin_id=? OR id IN (SELECT school_id FROM learning_school_staff WHERE user_id=?)',(user_id,user_id))]

    def create_school(self,user_id,title):
        with self.connect() as c:
            if c.execute('SELECT COUNT(*) FROM learning_schools WHERE admin_id=?',(user_id,)).fetchone()[0]>=5:
                raise HTTPException(409,'School limit reached')
            school_id=secrets.token_hex(12)
            c.execute('INSERT INTO learning_schools VALUES (?,?,?,?)',(school_id,title,user_id,utcnow()))
            return {'id':school_id}

    def school_detail(self,school_id,user_id):
        from judge import configured
        with self.connect() as c:
            s=self.school(c,school_id,user_id); s['is_admin']=s['admin_id']==user_id
            s['staff']=[dict(r) for r in c.execute('SELECT u.id,u.display_name FROM users u WHERE u.id=? OR u.id IN (SELECT user_id FROM learning_school_staff WHERE school_id=?)',(s['admin_id'],school_id))]
            s['groups']=[dict(r) for r in c.execute('SELECT g.id,g.title,g.owner_id FROM learning_groups g JOIN learning_school_groups sg ON sg.group_id=g.id WHERE sg.school_id=?',(school_id,))]
            s['library']=[{**json.loads(r['content']),'id':r['id']} for r in c.execute('SELECT * FROM learning_school_library WHERE school_id=? ORDER BY created_at DESC',(school_id,))]
            s['judge_available']=configured()
            return s

    def school_invite(self,school_id,user_id):
        from datetime import timedelta
        with self.connect() as c:
            self.school(c,school_id,user_id,admin=True)
            c.execute('DELETE FROM learning_school_invites WHERE school_id=?',(school_id,))
            code=secrets.token_urlsafe(24)
            expires=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()
            c.execute('INSERT INTO learning_school_invites VALUES (?,?,?)',(code,school_id,expires))
            return {'code':code,'expires_at':expires}

    def join_school(self,user_id,code):
        with self.connect() as c:
            row=c.execute('SELECT * FROM learning_school_invites WHERE code=?',(code,)).fetchone()
            if not row or row['expires_at']<utcnow(): raise HTTPException(404,'Invite expired')
            # A single-use invitation grants staff access, never administration.
            deleted=c.execute('DELETE FROM learning_school_invites WHERE code=?',(code,))
            if deleted.rowcount!=1: raise HTTPException(409,'Invite expired')
            c.execute('INSERT OR IGNORE INTO learning_school_staff VALUES (?,?)',(row['school_id'],user_id))
            self.profile(c,user_id)
            c.execute("UPDATE learning_profiles SET role='teacher' WHERE user_id=?",(user_id,))
            return {'id':row['school_id']}

    def attach_school_group(self,school_id,user_id,group_id):
        with self.connect() as c:
            self.school(c,school_id,user_id)
            self.group(c,group_id,user_id,owner_only=True)
            if c.execute('SELECT 1 FROM learning_school_groups WHERE group_id=?',(group_id,)).fetchone():
                raise HTTPException(409,'Group already belongs to school')
            c.execute('INSERT INTO learning_school_groups VALUES (?,?)',(group_id,school_id))
            return {'ok':True}

    def transfer_school_group(self,school_id,user_id,group_id,teacher_id):
        with self.connect() as c:
            school=self.school(c,school_id,user_id,admin=True)
            if not c.execute('SELECT 1 FROM learning_school_groups WHERE school_id=? AND group_id=?',(school_id,group_id)).fetchone():
                raise HTTPException(404,'Group not found')
            if teacher_id!=school['admin_id'] and not c.execute('SELECT 1 FROM learning_school_staff WHERE school_id=? AND user_id=?',(school_id,teacher_id)).fetchone():
                raise HTTPException(422,'Teacher must belong to school')
            # A pupil with submitted work must not gain the power to review that work.
            if c.execute('SELECT 1 FROM learning_members WHERE group_id=? AND user_id=?',(group_id,teacher_id)).fetchone():
                raise HTTPException(409,'Teacher is a learner in this group')
            c.execute('UPDATE learning_groups SET owner_id=? WHERE id=?',(teacher_id,group_id))
            return {'ok':True}

    def remove_staff(self,school_id,user_id,teacher_id):
        with self.connect() as c:
            s=self.school(c,school_id,user_id,admin=True)
            if s['admin_id']==teacher_id: raise HTTPException(409,'Cannot remove administrator')
            if c.execute('SELECT 1 FROM learning_groups g JOIN learning_school_groups sg ON g.id=sg.group_id WHERE sg.school_id=? AND g.owner_id=?',(school_id,teacher_id)).fetchone():
                raise HTTPException(409,'Transfer groups first')
            c.execute('DELETE FROM learning_school_staff WHERE school_id=? AND user_id=?',(school_id,teacher_id))
            return {'ok':True}

    def share_assignment(self,school_id,user_id,item_id):
        with self.connect() as c:
            self.school(c,school_id,user_id)
            _,content,g=self.assignment(c,item_id,user_id)
            self.group(c,g['id'],user_id,owner_only=True)
            if c.execute('SELECT COUNT(*) FROM learning_school_library WHERE school_id=?',(school_id,)).fetchone()[0]>=500:
                raise HTTPException(409,'Library limit reached')
            item=secrets.token_hex(12)
            c.execute('INSERT INTO learning_school_library VALUES (?,?,?,?)',(item,school_id,json.dumps(content,ensure_ascii=False),utcnow()))
            return {'id':item}

    def assign_library(self,school_id,user_id,library_id,group_id):
        with self.connect() as c:
            self.school(c,school_id,user_id)
            self.group(c,group_id,user_id,owner_only=True)
            if not c.execute('SELECT 1 FROM learning_school_groups WHERE group_id=? AND school_id=?',(group_id,school_id)).fetchone():
                raise HTTPException(404,'Group not found')
            row=c.execute('SELECT content FROM learning_school_library WHERE id=? AND school_id=?',(library_id,school_id)).fetchone()
            if not row: raise HTTPException(404,'Assignment not found')
            content=json.loads(row[0])
        return self.assign_custom(group_id,user_id,content)
