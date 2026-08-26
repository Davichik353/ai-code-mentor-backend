from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class FeedbackItem(BaseModel):
    """Individual feedback item"""
    issue: str = ""
    explanation: str = ""
    why: str = ""
    fix: Optional[str] = None
    suggestion: Optional[str] = None
    practice: Optional[str] = None
    topic: Optional[str] = None
    resource: Optional[str] = None

class HintItem(BaseModel):
    """Mentor hint for guiding students"""
    level: str = Field(..., description="critical, hint, or learn")
    hint: str = Field(..., description="The hint text")
    guide: str = Field(..., description="Guiding question or direction")

class CodeAnalysisRequest(BaseModel):
    """Request model for code analysis"""
    code: str = Field(..., min_length=5, max_length=10000, description="Python code to analyze")
    filename: Optional[str] = Field(default="code.py", description="Original filename")
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": "def hello():\n    print('Hello, World!')",
                "filename": "hello.py"
            }
        }

class CodeAnalysisResponse(BaseModel):
    """Response model for code analysis"""
    id: str = Field(..., description="Unique analysis ID")
    score: int = Field(..., ge=0, le=100, description="Overall score 0-100")
    timestamp: str = Field(..., description="Analysis timestamp")
    summary: str = Field(..., description="One-line summary of analysis")
    feedback: dict = Field(..., description="Detailed feedback with 4 levels")
    mentor_hints: List[HintItem] = Field(..., description="Hints for student learning")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "analysis_123",
                "score": 82,
                "timestamp": "2024-01-15T10:30:00",
                "summary": "Good code with room for improvement in error handling",
                "feedback": {
                    "critical": [],
                    "improvements": [{"issue": "error handling", "explanation": "..."}],
                    "learning": [{"topic": "try-except", "explanation": "..."}],
                    "good": [{"practice": "clear naming", "explanation": "..."}]
                },
                "mentor_hints": [
                    {"level": "hint", "hint": "Check error handling", "guide": "What happens if this fails?"}
                ]
            }
        }

class AnalysisItem(BaseModel):
    """Analysis item in history"""
    id: str
    filename: str
    code_preview: str
    score: int
    timestamp: str
    feedback_summary: str

class HistoryResponse(BaseModel):
    """History response model"""
    analyses: List[AnalysisItem]
    total: int

class ProgressStats(BaseModel):
    """Progress statistics"""
    total_analyses: int
    average_score: float
    best_score: int
    worst_score: int
    score_trend: List[int]
    improvements_by_category: dict

class StatsResponse(BaseModel):
    """Overall statistics"""
    total_analyses: int
    average_score: float
    best_score: int
    categories: dict

class UserRegister(BaseModel):
    """Registration request"""
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Password, minimum 8 characters")
    display_name: Optional[str] = Field(default=None, description="Optional display name")

class UserLogin(BaseModel):
    """Login request"""
    email: str
    password: str

class UserResponse(BaseModel):
    """Public user info (never includes password)"""
    id: str
    email: str
    display_name: Optional[str] = None
    created_at: str

class TokenResponse(BaseModel):
    """Response after successful register/login"""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
