from typing import Literal, Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from learning import Learning
from learning_content import TEMPLATES, GLOSSARY
from performance import RateLimiter

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Reflection = Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=3000)]
Code = Annotated[str, StringConstraints(min_length=5, max_length=10000)]


class ProfileUpdate(BaseModel):
    role: Literal['learner', 'teacher'] = 'learner'
    locale: Literal['ru', 'uz'] = 'ru'
    bio: str = Field(default='', max_length=500)
    portfolio_public: bool = False


class GroupCreate(BaseModel):
    title: Title
    description: str = Field(default='', max_length=1000)


class JoinGroup(BaseModel):
    code: str = Field(min_length=6, max_length=64)


class AssignmentCreate(BaseModel):
    template_id: str = Field(min_length=1, max_length=50)


class SolutionRequest(BaseModel):
    reflection: Reflection


class CaseReport(BaseModel):
    stdout: str = Field(default='', max_length=50000)
    error: str | None = Field(default=None, max_length=2000)


class SubmissionCreate(BaseModel):
    code: Code
    results: list[CaseReport] = Field(min_length=1, max_length=10)
    explanation: Reflection
    changed_code: Code
    change_explanation: Reflection


class Review(BaseModel):
    decision: Literal['approved', 'needs_revision']
    feedback: Reflection


def learning_router(get_db, current_user):
    router = APIRouter(prefix='/learning', tags=['Learning'])
    join_limiter = RateLimiter(10, 60)

    def store():
        return Learning(get_db().db_path)

    @router.get('/profile')
    def profile(user=Depends(current_user)):
        return store().get_profile(user['id'])

    @router.post('/profile')
    def update_profile(data: ProfileUpdate, user=Depends(current_user)):
        return store().update_profile(user['id'], data)

    @router.get('/templates')
    def templates(user=Depends(current_user)):
        return [{k: item[k] for k in ('id', 'title', 'prompt', 'language')} for item in TEMPLATES.values()]

    @router.get('/glossary')
    def glossary(user=Depends(current_user)):
        return GLOSSARY

    @router.get('/groups')
    def groups(user=Depends(current_user)):
        return store().groups(user['id'])

    @router.post('/groups', status_code=201)
    def create_group(data: GroupCreate, user=Depends(current_user)):
        return store().create_group(user['id'], data)

    @router.post('/groups/join')
    def join(data: JoinGroup, user=Depends(current_user)):
        allowed, info = join_limiter.is_allowed(user['id'])
        if not allowed:
            raise HTTPException(429, 'Join limit reached', headers={'Retry-After': str(info['retry_after'])})
        return store().join(user['id'], data.code)

    @router.get('/groups/{group_id}')
    def group(group_id: str, user=Depends(current_user)):
        return store().group_detail(group_id, user['id'])

    @router.post('/groups/{group_id}/assignments', status_code=201)
    def assign(group_id: str, data: AssignmentCreate, user=Depends(current_user)):
        return store().assign(group_id, user['id'], data.template_id)

    @router.get('/assignments/{item_id}')
    def assignment(item_id: str, user=Depends(current_user)):
        return store().detail(item_id, user['id'])

    @router.post('/assignments/{item_id}/hints')
    def hint(item_id: str, user=Depends(current_user)):
        return store().hint(item_id, user['id'])

    @router.post('/assignments/{item_id}/solution')
    def solution(item_id: str, data: SolutionRequest, user=Depends(current_user)):
        return store().solution(item_id, user['id'], data.reflection)

    @router.post('/assignments/{item_id}/submissions', status_code=201)
    def submit(item_id: str, data: SubmissionCreate, user=Depends(current_user)):
        return store().submit(item_id, user['id'], data)

    @router.get('/submissions/{item_id}')
    def submission(item_id: str, user=Depends(current_user)):
        return store().submission(item_id, user['id'])

    @router.post('/submissions/{item_id}/review')
    def review(item_id: str, data: Review, user=Depends(current_user)):
        return store().review(item_id, user['id'], data)

    @router.get('/portfolio')
    def portfolio(user=Depends(current_user)):
        return store().portfolio(user_id=user['id'])

    # Public only after explicit opt-in. No source code, email, group names or join codes.
    @router.get('/portfolios/{slug}')
    def public_portfolio(slug: str):
        if len(slug) > 64:
            raise HTTPException(404, 'Portfolio not found')
        return store().portfolio(slug=slug)

    return router
