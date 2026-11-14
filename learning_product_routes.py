from datetime import datetime
from typing import Literal
from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, Field, AwareDatetime
from performance import RateLimiter
from learning_mentor import advise

class AssignmentSettings(BaseModel):
    due_at: AwareDatetime | None = None
    allow_late: bool = True
    hints_allowed: bool = True
    solution_allowed: bool = True
    server_check: bool = False

class DraftPayload(BaseModel):
    assignmentCode: str = Field(default='',max_length=10000)
    changedCode: str = Field(default='',max_length=10000)
    changedInput: str = Field(default='',max_length=5000)
    defenseExplanation: str = Field(default='',max_length=3000)
    changeExplanation: str = Field(default='',max_length=3000)
    codePasteDetected: Literal['true','false'] = 'false'

class DraftUpdate(BaseModel):
    revision: int = Field(ge=0)
    payload: DraftPayload

class CodeRequest(BaseModel):
    code: str = Field(min_length=5,max_length=10000)

class MentorRequest(CodeRequest):
    question: str = Field(default='',max_length=1500)
    locale: Literal['ru','uz'] = 'ru'

class Name(BaseModel):
    title: str = Field(min_length=1,max_length=120,pattern=r'\S')

class Identifier(BaseModel):
    id: str = Field(min_length=1,max_length=100)

class Transfer(BaseModel):
    group_id: str = Field(min_length=1,max_length=100)
    teacher_id: str = Field(min_length=1,max_length=100)

class LibraryAssignment(BaseModel):
    library_id: str = Field(min_length=1,max_length=100)
    group_id: str = Field(min_length=1,max_length=100)


def add_product_routes(router,store,current_user):
    execution_limiter=RateLimiter(6,60)
    mentor_limiter=RateLimiter(5,30)
    invite_limiter=RateLimiter(5,30)
    def limit(limiter,user):
        allowed,info=limiter.is_allowed(user['id'])
        if not allowed: raise HTTPException(429,'Rate limit',headers={'Retry-After':str(info['retry_after'])})

    @router.post('/groups/{group_id}/members/{member_id}/remove')
    def remove_member(group_id:str,member_id:str,user=Depends(current_user)):
        return store().remove_member(group_id,user['id'],member_id)

    @router.post('/groups/{group_id}/members/{member_id}/restore')
    def restore_member(group_id:str,member_id:str,user=Depends(current_user)):
        return store().remove_member(group_id,user['id'],member_id,True)

    @router.post('/groups/{group_id}/invite/rotate')
    def rotate(group_id:str,user=Depends(current_user)):
        return store().rotate_invite(group_id,user['id'])

    @router.get('/groups/{group_id}/journal.csv')
    def journal(group_id:str,user=Depends(current_user)):
        return Response(store().journal_csv(group_id,user['id']),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="journal.csv"','Cache-Control':'no-store'})

    @router.post('/assignments/{item_id}/settings')
    def settings(item_id:str,data:AssignmentSettings,user=Depends(current_user)):
        return store().assignment_settings(item_id,user['id'],data)

    @router.get('/assignments/{item_id}/draft')
    def draft(item_id:str,user=Depends(current_user)):
        return store().draft(item_id,user['id'])

    @router.post('/assignments/{item_id}/draft')
    def save_draft(item_id:str,data:DraftUpdate,user=Depends(current_user)):
        return store().draft(item_id,user['id'],data)

    @router.post('/assignments/{item_id}/run')
    def run(item_id:str,data:CodeRequest,user=Depends(current_user)):
        limit(execution_limiter,user)
        return {'results':store().execute_tests(item_id,user['id'],data.code)}

    @router.post('/assignments/{item_id}/mentor')
    async def mentor(item_id:str,data:MentorRequest,user=Depends(current_user)):
        db=store()
        with db.connect() as c:
            _,content,group=db.assignment(c,item_id,user['id'])
            db.require_active(group)
            if not db.settings(c,item_id)['hints_allowed']: raise HTTPException(403,'Hints disabled')
            history=[dict(r) for r in c.execute('SELECT code,feedback FROM learning_submissions WHERE assignment_id=? AND user_id=? ORDER BY created_at DESC LIMIT 2',(item_id,user['id']))]
        limit(mentor_limiter,user)
        return await advise(content,data.code,data.question,history,data.locale)

    @router.get('/schools')
    def schools(user=Depends(current_user)): return store().schools(user['id'])

    @router.post('/schools',status_code=201)
    def create_school(data:Name,user=Depends(current_user)): return store().create_school(user['id'],data.title.strip())

    @router.post('/schools/join')
    def join_school(data:Identifier,user=Depends(current_user)):
        limit(invite_limiter,user)
        return store().join_school(user['id'],data.id)

    @router.get('/schools/{school_id}')
    def school(school_id:str,user=Depends(current_user)): return store().school_detail(school_id,user['id'])

    @router.post('/schools/{school_id}/invite')
    def invite(school_id:str,user=Depends(current_user)): return store().school_invite(school_id,user['id'])

    @router.post('/schools/{school_id}/groups')
    def attach(school_id:str,data:Identifier,user=Depends(current_user)): return store().attach_school_group(school_id,user['id'],data.id)

    @router.post('/schools/{school_id}/transfer')
    def transfer(school_id:str,data:Transfer,user=Depends(current_user)): return store().transfer_school_group(school_id,user['id'],data.group_id,data.teacher_id)

    @router.post('/schools/{school_id}/staff/{teacher_id}/remove')
    def remove_staff(school_id:str,teacher_id:str,user=Depends(current_user)): return store().remove_staff(school_id,user['id'],teacher_id)

    @router.post('/schools/{school_id}/admin')
    def transfer_admin(school_id:str,data:Identifier,user=Depends(current_user)):
        db=store()
        with db.connect() as c:
            s=db.school(c,school_id,user['id'],admin=True)
            if not c.execute('SELECT 1 FROM learning_school_staff WHERE school_id=? AND user_id=?',(school_id,data.id)).fetchone():
                raise HTTPException(422,'Teacher must belong to school')
            c.execute('INSERT OR IGNORE INTO learning_school_staff VALUES (?,?)',(school_id,user['id']))
            c.execute('UPDATE learning_schools SET admin_id=? WHERE id=?',(data.id,school_id))
        return {'ok':True}

    @router.post('/schools/{school_id}/library')
    def share(school_id:str,data:Identifier,user=Depends(current_user)): return store().share_assignment(school_id,user['id'],data.id)

    @router.post('/schools/{school_id}/library/assign',status_code=201)
    def assign_library(school_id:str,data:LibraryAssignment,user=Depends(current_user)): return store().assign_library(school_id,user['id'],data.library_id,data.group_id)
