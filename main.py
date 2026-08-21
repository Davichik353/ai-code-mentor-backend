from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime
import json
import os
from dotenv import load_dotenv

from models import CodeAnalysisRequest, CodeAnalysisResponse, AnalysisItem, FeedbackItem
from claude_analyzer import CodeAnalyzer
from database import Database

load_dotenv()

# Initialize database and analyzer
db = Database()
analyzer = CodeAnalyzer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup (modern replacement for on_event)"""
    db.init_db()
    if not os.getenv("GOOGLE_API_KEY"):
        print("[main] WARNING: GOOGLE_API_KEY is not set — /analyze will use fallback feedback only")
    yield

app = FastAPI(
    title="AI Code Mentor",
    description="Intelligent code analysis with Claude AI",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "AI Code Mentor API",
        "version": "1.0.0",
        "status": "running"
    }

@app.post("/analyze", response_model=CodeAnalysisResponse)
async def analyze_code(request: CodeAnalysisRequest):
    """
    Analyze Python code and return feedback
    """
    try:
        # Validate code
        if not request.code or len(request.code.strip()) < 5:
            raise HTTPException(status_code=400, detail="Code must be at least 5 characters")
        
        if len(request.code) > 10000:
            raise HTTPException(status_code=400, detail="Code exceeds 10000 characters")
        
        # Analyze code
        analysis_result = await analyzer.analyze(
            code=request.code,
            filename=request.filename or "code.py"
        )
        
        # Calculate score
        score = analyzer.calculate_score(analysis_result)
        
        # Save to database
        analysis_id = db.save_analysis(
            code=request.code,
            filename=request.filename or "untitled.py",
            feedback=analysis_result,
            score=score
        )
        
        # Create response
        response = CodeAnalysisResponse(
            id=analysis_id,
            score=score,
            timestamp=datetime.now().isoformat(),
            feedback=analysis_result,
            mentor_hints=analyzer.generate_hints(analysis_result),
            summary=analysis_result.get("summary", "")
        )
        
        return response
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history")
async def get_history(limit: int = 10):
    """
    Get analysis history
    """
    try:
        history = db.get_history(limit=limit)
        return {
            "analyses": history,
            "total": len(history)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analysis/{analysis_id}")
async def get_analysis(analysis_id: str):
    """
    Get specific analysis by ID
    """
    try:
        analysis = db.get_analysis(analysis_id)
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        return analysis
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/progress")
async def get_progress():
    """
    Get progress statistics
    """
    try:
        stats = db.get_progress_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/analysis/{analysis_id}")
async def delete_analysis(analysis_id: str):
    """
    Delete analysis from history
    """
    try:
        success = db.delete_analysis(analysis_id)
        if not success:
            raise HTTPException(status_code=404, detail="Analysis not found")
        return {"message": "Analysis deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
async def get_stats():
    """
    Get overall statistics
    """
    try:
        stats = db.get_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # Note: reload=True only works reliably when running as a module:
    #   python -m uvicorn main:app --reload
    # Running this file directly (python main.py) still works, just without hot-reload.
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
