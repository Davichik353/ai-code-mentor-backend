from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
import json
import os
from dotenv import load_dotenv
import time

from models import (
    CodeAnalysisRequest, CodeAnalysisResponse, AnalysisItem, FeedbackItem,
    TodoCreate, TodoUpdate, TodoItem, UserRegister, UserLogin, TokenResponse, UserResponse,
    RegistrationResponse
)
from claude_analyzer import CodeAnalyzer
from database import Database
from auth import (
    create_access_token, decode_access_token, hash_password, is_valid_email,
    verify_password, is_disposable_email, is_strong_password
)
from cache import get_cache, CacheKey
from performance import get_rate_limiter, get_metrics
from migrations import run_migrations
from health import get_health_checker
import hashlib
import secrets
import smtplib
from datetime import timedelta
from email.message import EmailMessage

load_dotenv(Path(__file__).resolve().parent / ".env")

# Initialize database and analyzer
db = Database()
analyzer = CodeAnalyzer()
security = HTTPBearer(auto_error=True)
registration_attempts = {}

# Initialize performance optimization components
cache = get_cache()
rate_limiter = get_rate_limiter()
metrics = get_metrics()
LANGUAGE_BY_EXTENSION = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript/JSX", ".ts": "TypeScript",
    ".tsx": "TypeScript/TSX", ".java": "Java", ".c": "C", ".h": "C", ".cpp": "C++",
    ".cxx": "C++", ".cs": "C#", ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
    ".php": "PHP", ".swift": "Swift", ".kt": "Kotlin", ".kts": "Kotlin",
    ".dart": "Dart", ".r": "R", ".sql": "SQL", ".sh": "Shell", ".bash": "Shell",
    ".html": "HTML", ".css": "CSS", ".vue": "Vue", ".svelte": "Svelte",
}

def current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Registration or login is required")
    payload = decode_access_token(credentials.credentials)
    user = db.get_user_by_id(payload["sub"]) if payload and payload.get("sub") else None
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user

def detect_language(filename: str) -> str:
    return LANGUAGE_BY_EXTENSION.get(os.path.splitext(filename or "")[1].lower(), "source code")

def smtp_configured() -> bool:
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]
    return all(os.getenv(key) for key in required)

def require_email_verification() -> bool:
    flag = os.getenv("REQUIRE_EMAIL_VERIFICATION")
    if flag is not None and flag.strip() != "":
        return flag.strip().lower() in {"1", "true", "yes", "on"}
    return smtp_configured()

def send_verification_email(email: str, token: str):
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]
    if any(not os.getenv(key) for key in required):
        raise RuntimeError("Email verification is enabled but SMTP is not configured")
    message = EmailMessage()
    message["Subject"] = "Verify your AI Code Mentor account"
    message["From"] = os.environ["SMTP_FROM"]
    message["To"] = email
    message.set_content(
        f"Your verification code is: {token}\n\n"
        "This code expires in 30 minutes. If you did not register, ignore this email."
    )
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"]), timeout=15) as server:
        server.starttls()
        server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        server.send_message(message)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup (modern replacement for on_event)"""
    db.init_db()

    # Run database migrations for optimization
    print("[startup] Running database optimizations...")
    run_migrations()

    # Clean up old cache entries and metrics
    print("[startup] Starting cache and metrics cleanup...")
    cache.cleanup_expired()
    metrics.cleanup_old_metrics(hours=24)

    if not os.getenv("GOOGLE_API_KEY"):
        print("[main] WARNING: GOOGLE_API_KEY is not set — /analyze will use fallback feedback only")
    if not os.getenv("JWT_SECRET"):
        print("[main] WARNING: JWT_SECRET is not set — logins will be invalidated on every restart")
    if not require_email_verification():
        print("[main] Email verification is OFF (demo mode). Set REQUIRE_EMAIL_VERIFICATION=true after SMTP works.")

    print("[startup] Performance optimizations initialized")
    print(f"[startup] Cache stats: {cache.stats()}")
    yield

    # Cleanup on shutdown
    print("[shutdown] Saving cache and metrics statistics...")
    print(f"[shutdown] Final cache stats: {cache.stats()}")
    print(f"[shutdown] Metrics tracked {len(metrics._metrics)} endpoints")

app = FastAPI(
    title="AI Code Mentor",
    description="Intelligent code analysis with Claude AI",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend. Additional origins can be supplied as a comma-separated
# FRONTEND_ORIGINS environment variable for a custom Vercel domain or preview URL.
frontend_origins = {
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://ai-code-mentor-frontend.vercel.app",
    "https://ai-code-mentor-backend-z80q.onrender.com",
}
frontend_origins.update(
    origin.strip().rstrip("/")
    for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(frontend_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

UI_FILE = Path(__file__).with_name("ai-code-mentor-ui.html")

@app.get("/")
async def root(request: Request):
    accept = request.headers.get("accept", "")
    if UI_FILE.exists() and "text/html" in accept:
        return FileResponse(UI_FILE)
    return {
        "message": "AI Code Mentor API",
        "version": "1.0.0",
        "status": "running",
        "ui": "/app"
    }

@app.get("/health")
async def health_check():
    """
    Comprehensive health check endpoint for deployment monitoring.
    Returns detailed status for orchestration, load balancers, and monitoring.

    Checks: database connectivity/response-time, memory, CPU, disk, uptime
    Status codes: 200=healthy, 503=degraded/down
    """
    health_checker = get_health_checker(db.db_path)
    health_data = health_checker.get_health_status()
    status_code = 200 if health_data["status"] == "healthy" else 503
    return health_data


@app.get("/metrics")
async def metrics_endpoint():
    """
    Prometheus-compatible metrics endpoint for monitoring systems.

    Provides metrics on:
    - Service health status (0=down, 1=degraded, 2=healthy)
    - Database response time and connectivity
    - Process memory and CPU usage
    - Disk space utilization
    - Service uptime

    Usage: Configure Prometheus scrape target -> http://[host]/metrics
    """
    health_checker = get_health_checker(db.db_path)
    metrics_text = health_checker.get_prometheus_metrics()
    return metrics_text

@app.get("/app")
async def app_ui():
    if not UI_FILE.exists():
        raise HTTPException(status_code=404, detail="UI file is missing")
    return FileResponse(UI_FILE)

@app.post("/auth/register", response_model=RegistrationResponse, status_code=201)
async def register(user: UserRegister, request: Request):
    email = user.email.lower().strip()
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    if is_disposable_email(email):
        raise HTTPException(status_code=400, detail="Disposable email addresses are not allowed")
    if not is_strong_password(user.password):
        raise HTTPException(status_code=400, detail="Password must be 10+ characters with upper, lower, number, and symbol")
    now = datetime.now().timestamp()
    client_ip = request.client.host if request.client else "unknown"
    # Rate limit by IP
    recent_ip = [stamp for stamp in registration_attempts.get(client_ip, []) if now - stamp < 3600]
    if len(recent_ip) >= 5:
        raise HTTPException(status_code=429, detail="Too many registration attempts. Try again later.")
    registration_attempts[client_ip] = recent_ip + [now]
    # Rate limit by email
    email_attempts = registration_attempts.get(f"email_{email}", [])
    recent_email = [stamp for stamp in email_attempts if now - stamp < 3600]
    if len(recent_email) >= 3:
        raise HTTPException(status_code=429, detail="Too many attempts for this email. Try again later.")
    registration_attempts[f"email_{email}"] = recent_email + [now]
    verify = require_email_verification()
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest() if verify else None
    expires = (datetime.now() + timedelta(minutes=30)).isoformat() if verify else None
    user_id = db.create_user(
        email, hash_password(user.password), user.display_name, token_hash, expires,
        email_verified=0 if verify else 1
    )
    if not user_id:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    if not verify:
        public_user = db.get_user_by_id(user_id)
        return RegistrationResponse(
            message="Account created. You can start analyzing code.",
            email=email,
            verification_required=False,
            access_token=create_access_token(user_id, email),
            user=UserResponse(**public_user),
        )
    try:
        send_verification_email(email, token)
    except Exception:
        db.delete_user(user_id)
        raise HTTPException(status_code=503, detail="Email verification is temporarily unavailable")
    return RegistrationResponse(message="Check your email for the verification code", email=email)

@app.post("/auth/verify-email", response_model=TokenResponse)
async def verify_email(email: str, code: str):
    if not is_valid_email(email) or not code or len(code) < 10:
        raise HTTPException(status_code=400, detail="Invalid verification details")
    user = db.verify_user_email(hashlib.sha256(code.encode()).hexdigest())
    if not user or user["email"].lower() != email.lower().strip():
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")
    return TokenResponse(access_token=create_access_token(user["id"], user["email"]), user=UserResponse(**db.get_user_by_id(user["id"])))

@app.post("/auth/login", response_model=TokenResponse)
async def login(user: UserLogin):
    record = db.get_user_by_email(user.email)
    if not record or not verify_password(user.password, record["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if record["email_verified"] == 0 and require_email_verification():
        raise HTTPException(status_code=403, detail="Verify your email before signing in")
    public_user = db.get_user_by_id(record["id"])
    return TokenResponse(access_token=create_access_token(record["id"], record["email"]), user=UserResponse(**public_user))

@app.get("/auth/me", response_model=UserResponse)
async def me(user=Depends(current_user)):
    return UserResponse(**user)

@app.post("/analyze", response_model=CodeAnalysisResponse)
async def analyze_code(request: CodeAnalysisRequest, user=Depends(current_user)):
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
        language = request.language or detect_language(request.filename or "")
        analysis_result = await analyzer.analyze(
            code=request.code,
            filename=request.filename or "code.py",
            language=language
        )
        
        # Calculate score
        score = analyzer.calculate_score(analysis_result)
        
        # Save to database
        analysis_id = db.save_analysis(
            code=request.code,
            filename=request.filename or "untitled.py",
            feedback=analysis_result,
            score=score,
            user_id=user["id"]
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
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history")
async def get_history(limit: int = 10, user=Depends(current_user)):
    """
    Get analysis history
    """
    try:
        history = db.get_history(limit=min(max(limit, 1), 50), user_id=user["id"])
        return {
            "analyses": history,
            "total": len(history)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/learning-videos")
async def learning_videos(query: str = Query(..., min_length=2, max_length=200), user=Depends(current_user)):
    """Return a YouTube search link for a detected issue without storing or proxying videos."""
    from urllib.parse import quote_plus
    search = quote_plus(f"{query} programming tutorial")
    return {
        "query": query,
        "youtube_url": f"https://www.youtube.com/results?search_query={search}",
    }

@app.get("/analysis/{analysis_id}")
async def get_analysis(analysis_id: str, user=Depends(current_user)):
    """
    Get specific analysis by ID
    """
    try:
        analysis = db.get_analysis(analysis_id, user_id=user["id"])
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        return analysis
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/progress")
async def get_progress(request: Request):
    """
    Get progress statistics with caching and rate limiting.
    Cached for 60 seconds to reduce database load.
    """
    start_time = time.time()

    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    allowed, rate_info = rate_limiter.is_allowed(client_ip)
    if not allowed:
        metrics.record("progress", "GET", (time.time() - start_time) * 1000, 429)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {rate_info['retry_after']} seconds."
        )

    # Check cache
    cached_stats = cache.get(CacheKey.progress_stats())
    if cached_stats is not None:
        metrics.record("progress", "GET", (time.time() - start_time) * 1000, 200)
        return cached_stats

    # Generate stats
    try:
        stats = db.get_progress_stats()
        # Cache for 60 seconds
        cache.set(CacheKey.progress_stats(), stats, ttl_seconds=60)
        metrics.record("progress", "GET", (time.time() - start_time) * 1000, 200)
        return stats
    except Exception as e:
        metrics.record("progress", "GET", (time.time() - start_time) * 1000, 500)
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/analysis/{analysis_id}")
async def delete_analysis(analysis_id: str, user=Depends(current_user)):
    """
    Delete analysis from history
    """
    try:
        success = db.delete_analysis(analysis_id, user_id=user["id"])
        if not success:
            raise HTTPException(status_code=404, detail="Analysis not found")
        return {"message": "Analysis deleted successfully"}
    except HTTPException:
        raise
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

@app.get("/todos", response_model=list[TodoItem], dependencies=[Depends(current_user)])
async def get_todos(status: str = Query(default="all", pattern="^(all|active|completed)$"), user=Depends(current_user)):
    """Get the todo list, optionally filtered by completion status."""
    try:
        return db.get_todos(None if status == "all" else status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/todos", response_model=TodoItem, status_code=201, dependencies=[Depends(current_user)])
async def create_todo(todo: TodoCreate, user=Depends(current_user)):
    """Create a todo item."""
    try:
        if not todo.title.strip():
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        return db.create_todo(todo.title, todo.description)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/todos/{todo_id}", response_model=TodoItem, dependencies=[Depends(current_user)])
async def update_todo(todo_id: str, todo: TodoUpdate, user=Depends(current_user)):
    """Update a todo item."""
    try:
        if todo.title is not None and not todo.title.strip():
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        updated = db.update_todo(todo_id, todo.title, todo.description, todo.completed)
        if not updated:
            raise HTTPException(status_code=404, detail="Todo not found")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/todos/{todo_id}", dependencies=[Depends(current_user)])
async def delete_todo(todo_id: str, user=Depends(current_user)):
    """Delete a todo item."""
    try:
        if not db.delete_todo(todo_id):
            raise HTTPException(status_code=404, detail="Todo not found")
        return {"message": "Todo deleted successfully"}
    except HTTPException:
        raise
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
