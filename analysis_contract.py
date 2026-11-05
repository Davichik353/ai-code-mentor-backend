"""Typed structured output contract shared by Gemini and the response parser."""
from pydantic import BaseModel, Field


class Issue(BaseModel):
    issue: str
    explanation: str
    why: str = ''
    fix: str = ''


class Improvement(BaseModel):
    issue: str
    explanation: str
    why: str = ''
    suggestion: str = ''


class LearningItem(BaseModel):
    topic: str
    explanation: str
    resource: str = ''


class GoodPractice(BaseModel):
    practice: str
    explanation: str


class MentorHint(BaseModel):
    hint: str
    guide: str = ''


class AnalysisFeedback(BaseModel):
    summary: str = Field(min_length=1)
    critical: list[Issue]
    improvements: list[Improvement]
    learning: list[LearningItem]
    good: list[GoodPractice]
    mentor_hints: list[MentorHint] = Field(default_factory=list)
