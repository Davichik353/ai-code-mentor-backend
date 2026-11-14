"""Private in-app support inbox. Staff roles are deployment-controlled, never self-assigned."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated
from learning import Learning
from performance import RateLimiter

Text = Annotated[str, StringConstraints(strip_whitespace=True,min_length=10,max_length=4000)]

def init_support_schema(c):
    c.executescript('''
        CREATE TABLE IF NOT EXISTS support_tickets (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category TEXT NOT NULL, message TEXT NOT NULL, diagnostics TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open', reply TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_support_user ON support_tickets(user_id);
    ''')

class Diagnostic(BaseModel):
    js_errors: int = Field(default=0,ge=0,le=1000)
    network_errors: int = Field(default=0,ge=0,le=1000)
    locale: Literal['ru','uz'] = 'ru'
    online: bool = True

class Ticket(BaseModel):
    category: Literal['access','code','classroom','other'] = 'other'
    message: Text
    diagnostics: Diagnostic | None = None
    request_key: str = Field(pattern=r'^[a-zA-Z0-9-]{16,64}$')

class Reply(BaseModel):
    reply: Text
    status: Literal['open','resolved'] = 'resolved'

def staff_emails():
    configured=os.getenv('SUPPORT_ADMIN_EMAILS')
    if configured is not None:return {x.strip().lower() for x in configured.split(',') if x.strip()}
    return set(json.loads(Path(__file__).with_name('support-admins.json').read_text()))

def is_staff(user):
    emails=staff_emails()
    return bool(user.get('email_verified')) and user['email'].lower() in emails

def support_router(get_db,current_user):
    router=APIRouter(prefix='/support',tags=['Support'])
    limiter=RateLimiter(3,15)
    def store():return Learning(get_db().db_path)

    @router.get('/tickets')
    def tickets(user=Depends(current_user)):
        staff=is_staff(user)
        with store().connect() as c:
            rows=c.execute('SELECT * FROM support_tickets '+('' if staff else 'WHERE user_id=? ')+'ORDER BY updated_at DESC LIMIT 100',() if staff else (user['id'],)).fetchall()
        return {'is_staff':staff,'staff_configured':bool(staff_emails()),'tickets':[dict(r) for r in rows]}

    @router.post('/tickets',status_code=201)
    def create(data:Ticket,user=Depends(current_user)):
        import hashlib
        # Idempotent retries after a network failure must not create duplicates.
        ticket_id=hashlib.sha256((user['id']+':'+data.request_key).encode()).hexdigest()[:24]
        with store().connect() as c:
            old=c.execute('SELECT id FROM support_tickets WHERE id=?',(ticket_id,)).fetchone()
            if old:return {'id':old['id']}
            allowed,info=limiter.is_allowed(user['id'])
            if not allowed:raise HTTPException(429,'Support rate limit',headers={'Retry-After':str(info['retry_after'])})
            when=datetime.now(timezone.utc).isoformat()
            c.execute('INSERT OR IGNORE INTO support_tickets (id,user_id,category,message,diagnostics,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                (ticket_id,user['id'],data.category,data.message,json.dumps(data.diagnostics.model_dump() if data.diagnostics else {}),when,when))
        return {'id':ticket_id}

    @router.post('/tickets/{ticket_id}/reply')
    def reply(ticket_id:str,data:Reply,user=Depends(current_user)):
        if not is_staff(user):raise HTTPException(404,'Ticket not found')
        with store().connect() as c:
            if not c.execute('SELECT 1 FROM support_tickets WHERE id=?',(ticket_id,)).fetchone():raise HTTPException(404,'Ticket not found')
            c.execute('UPDATE support_tickets SET reply=?,status=?,updated_at=? WHERE id=?',(data.reply,data.status,datetime.now(timezone.utc).isoformat(),ticket_id))
        return {'id':ticket_id,'status':data.status}
    return router
