"""Platform administration. Deployment-controlled roles, audited mutations, no password exposure."""
import json
import os
import secrets
from pathlib import Path
from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints
from learning import Learning


def stamp():return datetime.now(timezone.utc).isoformat()

def admin_emails():
    configured=os.getenv('PLATFORM_ADMIN_EMAILS')
    return {v.strip().lower() for v in configured.split(',') if v.strip()} if configured is not None else set(json.loads(Path(__file__).with_name('platform-admins.json').read_text()))

def is_admin(user):return bool(user.get('email_verified')) and user['email'].lower() in admin_emails()

def init_admin_schema(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS admin_user_blocks (
        user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        reason TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS admin_settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS admin_audit (
        id TEXT PRIMARY KEY, actor_id TEXT REFERENCES users(id) ON DELETE SET NULL,
        action TEXT NOT NULL, target_id TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS admin_operations (name TEXT PRIMARY KEY, checked_at TEXT NOT NULL, status TEXT NOT NULL);
    ''')


def blocked(path,user_id):
    with Learning(path).connect() as c:
        return bool(c.execute('SELECT 1 FROM admin_user_blocks WHERE user_id=?',(user_id,)).fetchone())

def ai_settings(path):
    result={'enabled':True,'per_user':int(os.getenv('ANALYSES_PER_USER_PER_DAY','20')),'total':int(os.getenv('ANALYSES_TOTAL_PER_DAY','200'))}
    with Learning(path).connect() as c:
        row=c.execute("SELECT value FROM admin_settings WHERE name='ai'").fetchone()
        if row:result.update(json.loads(row[0]))
    return result

def require_ai(path):
    settings=ai_settings(path)
    if not settings['enabled']:raise HTTPException(503,'AI disabled by administrator')
    return settings

def audit(c,actor,action,target):
    c.execute('INSERT INTO admin_audit VALUES (?,?,?,?,?)',(secrets.token_hex(12),actor,action,target,stamp()))

class Block(BaseModel):
    blocked: bool
    reason: Annotated[str,StringConstraints(strip_whitespace=True,min_length=5,max_length=500)]

class AISettings(BaseModel):
    enabled: bool
    per_user: int = Field(ge=1,le=1000,strict=True)
    total: int = Field(ge=1,le=100000,strict=True)

class Teacher(BaseModel):
    email: Annotated[str,StringConstraints(strip_whitespace=True,to_lower=True,min_length=3,max_length=254)]

class Archive(BaseModel):
    archived: bool


def admin_router(get_db,current_user):
    router=APIRouter(prefix='/admin',tags=['Administration'])
    def db():return Learning(get_db().db_path)
    def operator(user=Depends(current_user)):
        if not is_admin(user):raise HTTPException(403,'Administrator access required')
        return user
    def target(c,email):
        u=c.execute('SELECT id,email,email_verified FROM users WHERE email=?',(email,)).fetchone()
        if not u:raise HTTPException(404,'User not found')
        if not u['email_verified']:raise HTTPException(409,'User email must be verified')
        if c.execute('SELECT 1 FROM admin_user_blocks WHERE user_id=?',(u['id'],)).fetchone():raise HTTPException(409,'User is blocked')
        return u

    @router.get('/access')
    def access(user=Depends(current_user)):return {'is_admin':is_admin(user)}

    @router.get('/users')
    def users(q:str=Query('',max_length=120),offset:int=Query(0,ge=0),user=Depends(operator)):
        with db().connect() as c:
            where="WHERE LOWER(u.email) LIKE ? ESCAPE '!' OR LOWER(COALESCE(u.display_name,'')) LIKE ? ESCAPE '!'"
            needle='%'+q.lower().replace('!','!!').replace('%','!%').replace('_','!_')+'%'
            count=c.execute('SELECT COUNT(*) FROM users u '+where,(needle,needle)).fetchone()[0]
            rows=c.execute('''SELECT u.id,u.email,u.display_name,u.email_verified,u.created_at,
                EXISTS(SELECT 1 FROM admin_user_blocks b WHERE b.user_id=u.id) AS blocked
                FROM users u '''+where+' ORDER BY u.created_at DESC,u.id LIMIT 50 OFFSET ?',(needle,needle,offset)).fetchall()
        return {'total':count,'offset':offset,'users':[{**dict(r),'protected':r['email'].lower() in admin_emails()} for r in rows]}

    @router.post('/users/{user_id}/block')
    def block(user_id:str,data:Block,user=Depends(operator)):
        with db().connect() as c:
            row=c.execute('SELECT id,email FROM users WHERE id=?',(user_id,)).fetchone()
            if not row:raise HTTPException(404,'User not found')
            if user_id==user['id'] or row['email'].lower() in admin_emails():raise HTTPException(409,'Cannot block administrator')
            c.execute('UPDATE users SET token_version=token_version+1 WHERE id=?',(user_id,))
            c.execute('DELETE FROM admin_user_blocks WHERE user_id=?',(user_id,))
            if data.blocked:c.execute('INSERT INTO admin_user_blocks VALUES (?,?,?)',(user_id,data.reason,stamp()))
            audit(c,user['id'],'block_user' if data.blocked else 'unblock_user',user_id)
        return {'blocked':data.blocked}

    @router.get('/classrooms')
    def classrooms(offset:int=Query(0,ge=0),user=Depends(operator)):
        with db().connect() as c:
            schools=[dict(r) for r in c.execute('''SELECT s.id,s.title,u.email AS admin_email,
                (SELECT COUNT(*) FROM learning_school_staff t WHERE t.school_id=s.id AND t.user_id<>s.admin_id) + 1 AS staff_count
                FROM learning_schools s JOIN users u ON u.id=s.admin_id ORDER BY s.created_at DESC,s.id LIMIT 50 OFFSET ?''',(offset,))]
            groups=[dict(r) for r in c.execute('''SELECT g.id,g.title,u.email AS teacher_email,
                (SELECT COUNT(*) FROM learning_members m WHERE m.group_id=g.id) AS member_count,
                EXISTS(SELECT 1 FROM learning_group_archives a WHERE a.group_id=g.id) AS archived
                FROM learning_groups g JOIN users u ON u.id=g.owner_id ORDER BY g.created_at DESC,g.id LIMIT 50 OFFSET ?''',(offset,))]
            totals={name:c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for name,table in [('schools','learning_schools'),('groups','learning_groups')]}
        return {'schools':schools,'groups':groups,'totals':totals,'offset':offset}

    @router.post('/groups/{group_id}/teacher')
    def teacher(group_id:str,data:Teacher,user=Depends(operator)):
        store=db()
        with store.connect() as c:
            row=c.execute('SELECT id,owner_id FROM learning_groups WHERE id=?',(group_id,)).fetchone()
            if not row:raise HTTPException(404,'Group not found')
            new=target(c,data.email)
            if c.execute('SELECT 1 FROM learning_members WHERE group_id=? AND user_id=?',(group_id,new['id'])).fetchone():raise HTTPException(409,'Teacher is a learner in this group')
            school=c.execute('SELECT school_id FROM learning_school_groups WHERE group_id=?',(group_id,)).fetchone()
            if school:c.execute('INSERT OR IGNORE INTO learning_school_staff VALUES (?,?)',(school[0],new['id']))
            store.profile(c,new['id'])
            c.execute("UPDATE learning_profiles SET role='teacher' WHERE user_id=?",(new['id'],))
            c.execute('UPDATE learning_groups SET owner_id=? WHERE id=?',(new['id'],group_id))
            audit(c,user['id'],'assign_teacher',group_id+':'+new['id'])
        return {'ok':True}

    @router.post('/schools/{school_id}/administrator')
    def school_admin(school_id:str,data:Teacher,user=Depends(operator)):
        with db().connect() as c:
            school=c.execute('SELECT admin_id FROM learning_schools WHERE id=?',(school_id,)).fetchone()
            if not school:raise HTTPException(404,'School not found')
            new=target(c,data.email)
            c.execute('INSERT OR IGNORE INTO learning_school_staff VALUES (?,?)',(school_id,school[0]))
            c.execute('INSERT OR IGNORE INTO learning_school_staff VALUES (?,?)',(school_id,new['id']))
            c.execute('UPDATE learning_schools SET admin_id=? WHERE id=?',(new['id'],school_id))
            audit(c,user['id'],'assign_school_admin',school_id+':'+new['id'])
        return {'ok':True}

    @router.post('/groups/{group_id}/archive')
    def archive(group_id:str,data:Archive,user=Depends(operator)):
        with db().connect() as c:
            if not c.execute('SELECT 1 FROM learning_groups WHERE id=?',(group_id,)).fetchone():raise HTTPException(404,'Group not found')
            if data.archived:c.execute('INSERT OR IGNORE INTO learning_group_archives VALUES (?,?)',(group_id,stamp()))
            else:c.execute('DELETE FROM learning_group_archives WHERE group_id=?',(group_id,))
            audit(c,user['id'],'archive_group' if data.archived else 'restore_group',group_id)
        return {'archived':data.archived}

    @router.get('/ai')
    def ai(user=Depends(operator)):
        with db().connect() as c:
            day=stamp()[:10]
            used=c.execute("SELECT count FROM analysis_quotas WHERE scope='all' AND day=?",(day,)).fetchone()
            usage=[dict(r) for r in c.execute('''SELECT model,COUNT(*) AS requests,COALESCE(SUM(input_tokens),0) AS input_tokens,
                COALESCE(SUM(output_tokens),0) AS output_tokens,COALESCE(SUM(total_tokens),0) AS total_tokens
                FROM ai_usage WHERE created_at>=? GROUP BY model''',(day,))]
        return {'settings':ai_settings(get_db().db_path),'today':day,'analyses_used':used[0] if used else 0,'usage':usage,'cost_available':False}

    @router.post('/ai')
    def save_ai(data:AISettings,user=Depends(operator)):
        if data.per_user>data.total:raise HTTPException(422,'Per-user limit exceeds total limit')
        with db().connect() as c:
            c.execute("INSERT OR IGNORE INTO admin_settings VALUES ('ai','{}')")
            c.execute("UPDATE admin_settings SET value=? WHERE name='ai'",(data.model_dump_json(),))
            audit(c,user['id'],'update_ai_limits','ai')
        return data

    @router.get('/system')
    def system(user=Depends(operator)):
        from health import HealthChecker
        from judge import configured
        from reliability import recent_errors
        checker=HealthChecker(get_db().db_path)
        try:health=checker.get_health_status()
        finally:checker.pool.close_all()
        with db().connect() as c:
            backup=c.execute("SELECT checked_at,status FROM admin_operations WHERE name='backup'").fetchone()
            log=[dict(r) for r in c.execute('SELECT action,target_id,actor_id,created_at FROM admin_audit ORDER BY created_at DESC,id DESC LIMIT 50')]
        return {'health':health,'judge_configured':configured(),'backup':dict(backup) if backup else None,
                'errors':recent_errors(),'audit':log}
    return router
