from fastapi import FastAPI, HTTPException, Query, Depends, Request, BackgroundTasks
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
import json
import os
from dotenv import load_dotenv
import time

# Load environment variables BEFORE importing auth
load_dotenv(Path(__file__).resolve().parent / ".env")

from models import (
    CodeAnalysisRequest, CodeAnalysisResponse, AnalysisItem, FeedbackItem,
    TodoCreate, TodoUpdate, TodoItem, UserRegister, UserLogin, TokenResponse, UserResponse,
    RegistrationResponse, PasswordResetRequest, PasswordResetConfirm, ProfileUpdateRequest
)
from claude_analyzer import CodeAnalyzer
from database import Database
from authorship import inspect_authorship
from learning_routes import learning_router
from auth import (
    create_access_token, decode_access_token, hash_password, is_valid_email,
    verify_password, is_disposable_email, is_strong_password
)
from cache import get_cache, CacheKey
from performance import get_rate_limiter, get_metrics, RateLimiter
from migrations import run_migrations
from health import get_health_checker
import hashlib
import secrets
from mail_delivery import smtp_configured, mail_configured, send_mail
from datetime import timedelta

# Initialize database and analyzer
db = Database()
analyzer = CodeAnalyzer()
security = HTTPBearer(auto_error=True)
registration_ip_limiter = RateLimiter(10, 60)
registration_email_limiter = RateLimiter(3, 3)

# Initialize performance optimization components
cache = get_cache()
rate_limiter = get_rate_limiter()
metrics = get_metrics()
analysis_limiter = RateLimiter(requests_per_minute=5, requests_per_hour=60)
login_limiter = RateLimiter(10, 50)
reset_limiter = RateLimiter(3, 3)
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(24))
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
    if not user or payload.get("ver", 0) != user.get("token_version", 0):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if require_email_verification() and not user["email_verified"]:
        raise HTTPException(status_code=403, detail="Verify your email before signing in")
    return user

def detect_language(filename: str) -> str:
    return LANGUAGE_BY_EXTENSION.get(os.path.splitext(filename or "")[1].lower(), "source code")

def require_email_verification() -> bool:
    flag = os.getenv("REQUIRE_EMAIL_VERIFICATION")
    if flag is not None and flag.strip() != "":
        return flag.strip().lower() in {"1", "true", "yes", "on"}
    return smtp_configured()

def send_verification_email(email: str, token: str):
    send_mail(email, 'AI Code Mentor: подтверждение почты',
        f'Ваш код подтверждения: {token}\n\n'
        'Введите его на сайте AI Code Mentor. Код действует 30 минут. '
        'Если вы не регистрировались, проигнорируйте письмо.')

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup (modern replacement for on_event)"""
    db.init_db()

    # Run database migrations for optimization
    print("[startup] Running database optimizations...")
    run_migrations(db.db_path)

    # Clean up old cache entries and metrics
    print("[startup] Starting cache and metrics cleanup...")
    cache.cleanup_expired()
    metrics.cleanup_old_metrics(hours=24)

    if not os.getenv("GOOGLE_API_KEY"):
        print("[main] WARNING: GOOGLE_API_KEY is not set — /analyze will use fallback feedback only")
    if not os.getenv("JWT_SECRET"):
        print("[main] WARNING: JWT_SECRET is not set — logins will be invalidated on every restart")
    if os.getenv("PUBLIC_LAUNCH", "false").lower() == "true":
        if not mail_configured() or not require_email_verification():
            raise RuntimeError("Public launch requires email delivery and email verification")
    if not require_email_verification():
        print("[main] Email verification is OFF (demo mode). Set REQUIRE_EMAIL_VERIFICATION=true after email delivery works.")

    print("[startup] Performance optimizations initialized")
    print(f"[startup] Cache stats: {cache.stats()}")
    yield

    # Cleanup on shutdown
    print("[shutdown] Saving cache and metrics statistics...")
    print(f"[shutdown] Final cache stats: {cache.stats()}")
    print(f"[shutdown] Metrics tracked {len(metrics._metrics)} endpoints")

app = FastAPI(
    title="AI Code Mentor",
    description="Programming practice, teacher groups and Gemini code feedback",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend. Additional origins can be supplied as a comma-separated
# FRONTEND_ORIGINS environment variable for a custom Vercel domain or preview URL.
frontend_origins = {
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://ai-code-mentor-frontend.vercel.app",
    "https://ai-code-mentor-frontend-iota.vercel.app",
    "https://ai-code-mentor-backend-z80q.onrender.com",
}
frontend_origins.update(
    origin.strip().rstrip("/")
    for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
)

from request_security import RequestSecurity
api_limiter = RateLimiter(int(os.getenv("API_REQUESTS_PER_MINUTE", "120")), 3000)
auth_ip_limiter = RateLimiter(int(os.getenv("AUTH_REQUESTS_PER_MINUTE", "15")), 100)
app.add_middleware(RequestSecurity, general=api_limiter, auth=auth_ip_limiter)
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(frontend_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

app.include_router(learning_router(lambda: db, current_user))

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://ai-code-mentor-frontend-iota.vercel.app").rstrip("/")

@app.get("/")
async def root():
    return {"message": "AI Code Mentor API", "version": "1.0.0", "status": "running", "ui": FRONTEND_URL}

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
    health_data['email_delivery'] = {'configured': mail_configured(),
        'provider': 'brevo' if os.getenv('BREVO_API_KEY', '').strip() else 'smtp',
        'verification_required': require_email_verification()}
    health_data['database_maintenance'] = os.getenv('DATABASE_MAINTENANCE', '').lower() == 'true'
    status_code = 200 if health_data["status"] == "healthy" else 503
    return JSONResponse(content=health_data, status_code=status_code)


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
    return RedirectResponse(FRONTEND_URL, status_code=307)

@app.post("/auth/register", response_model=RegistrationResponse, status_code=201)
async def register(user: UserRegister, request: Request):
    email = user.email.lower().strip()
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    if is_disposable_email(email):
        raise HTTPException(status_code=400, detail="Disposable email addresses are not allowed")
    if not is_strong_password(user.password):
        raise HTTPException(status_code=400, detail="Password must be 10+ characters with upper, lower, number, and symbol")
    client_ip = request.client.host if request.client else "unknown"
    identity = hashlib.sha256(email.encode()).hexdigest()
    for limiter, key in ((registration_ip_limiter, client_ip), (registration_email_limiter, identity)):
        allowed, info = limiter.is_allowed(key)
        if not allowed:
            raise HTTPException(429, "Too many registration attempts", headers={"Retry-After": str(info['retry_after'])})
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
    user = db.verify_user_email(hashlib.sha256(code.encode()).hexdigest(), email.lower().strip())
    if not user or user["email"].lower() != email.lower().strip():
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")
    return TokenResponse(access_token=create_access_token(user["id"], user["email"], user["token_version"]), user=UserResponse(**db.get_user_by_id(user["id"])))

@app.post("/auth/login", response_model=TokenResponse)
def login(user: UserLogin):
    identity = hashlib.sha256(user.email.strip().lower().encode()).hexdigest()
    allowed, info = login_limiter.is_allowed(identity)
    if not allowed:
        raise HTTPException(429, "Too many sign-in attempts", headers={"Retry-After": str(info['retry_after'])})
    record = db.get_user_by_email(user.email)
    valid = verify_password(user.password, record["password_hash"] if record else DUMMY_PASSWORD_HASH)
    if not record or not valid:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if record["email_verified"] == 0 and require_email_verification():
        raise HTTPException(status_code=403, detail="Verify your email before signing in")
    public_user = db.get_user_by_id(record["id"])
    return TokenResponse(access_token=create_access_token(record["id"], record["email"], record["token_version"]), user=UserResponse(**public_user))

@app.post("/auth/forgot-password")
def forgot_password(body: PasswordResetRequest, background_tasks: BackgroundTasks):
    if not mail_configured():
        raise HTTPException(503, "Password recovery is temporarily unavailable")
    email = body.email.strip().lower()
    identity = hashlib.sha256(email.encode()).hexdigest()
    allowed, info = reset_limiter.is_allowed(identity)
    if not allowed:
        raise HTTPException(429, "Too many recovery requests", headers={"Retry-After": str(info['retry_after'])})
    # Queue lookup/delivery after responding, including lookup for absent accounts.
    # SMTP latency must not reveal account existence in the HTTP response time.
    background_tasks.add_task(deliver_password_recovery, email)
    return {"message": "If an account exists, a recovery email will be sent."}


def deliver_password_recovery(email):
    record = db.get_user_by_email(email)
    if record:
        token = secrets.token_urlsafe(32)
        db.issue_password_reset(record['id'], hashlib.sha256(token.encode()).hexdigest(),
            (datetime.utcnow() + timedelta(minutes=15)).isoformat())
        try:
            send_password_reset_email(email, token)
        except Exception:
            # Do not disclose account existence through SMTP errors or log the token.
            db.issue_password_reset(record['id'], None, None)
            print('[auth] Password recovery delivery failed')


def send_password_reset_email(email, token):
    send_mail(email, 'AI Code Mentor: восстановление доступа',
        f'Откройте {FRONTEND_URL}/#reset={token}\n\n'
        'Одноразовая ссылка действует 15 минут. '
        'Если вы не запрашивали смену пароля, проигнорируйте письмо.')


@app.post("/auth/reset-password")
def reset_password(body: PasswordResetConfirm):
    if not is_strong_password(body.password):
        raise HTTPException(400, "Use 10+ characters with upper/lowercase, number and symbol")
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    if not db.reset_password(token_hash, hash_password(body.password)):
        raise HTTPException(400, "Invalid or expired recovery link")
    return {"message": "Password changed. Sign in again."}

@app.get("/auth/me", response_model=UserResponse)
async def me(user=Depends(current_user)):
    return UserResponse(**user)

@app.patch("/auth/profile", response_model=UserResponse)
def update_account_profile(body: ProfileUpdateRequest, user=Depends(current_user)):
    name = (body.display_name or '').strip()
    if any(ord(char) < 32 for char in name):
        raise HTTPException(400, "Name contains invalid characters")
    db.update_display_name(user['id'], name or None)
    return UserResponse(**db.get_user_by_id(user['id']))


@app.delete("/auth/account")
async def delete_account(user=Depends(current_user)):
    """Delete the authenticated account and its private analysis data."""
    try:
        if not db.delete_user(user["id"]):
            raise HTTPException(status_code=404, detail="Account not found")
        cache.delete(CacheKey.progress_stats(user["id"]))
        return {"message": "Account deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="The operation could not be completed")

@app.post("/authorship")
async def authorship_check(request: CodeAnalysisRequest, user=Depends(current_user)):
    """Inspect explicit provenance disclosures; does not establish authorship."""
    return inspect_authorship(request.code, request.filename or "code.py", request.language or "")

@app.post("/analyze", response_model=CodeAnalysisResponse)
async def analyze_code(request: CodeAnalysisRequest, user=Depends(current_user)):
    """
    Analyze Python code and return feedback
    """
    allowed, limits = analysis_limiter.is_allowed(user["id"])
    if not allowed:
        raise HTTPException(status_code=429, detail="Analysis limit reached. Please try again later.",
                            headers={"Retry-After": str(limits["retry_after"])})
    try:
        # Validate code
        if not request.code or len(request.code.strip()) < 5:
            raise HTTPException(status_code=400, detail="Code must be at least 5 characters")
        
        if len(request.code) > 10000:
            raise HTTPException(status_code=400, detail="Code exceeds 10000 characters")
        
        if not db.reserve_analysis_quota(user['id'], int(os.getenv('ANALYSES_PER_USER_PER_DAY', '20')),
                int(os.getenv('ANALYSES_TOTAL_PER_DAY', '200'))):
            raise HTTPException(429, "Daily analysis quota reached", headers={"Retry-After": "3600"})
        # Analyze code
        language = request.language or detect_language(request.filename or "")
        analysis_result = await analyzer.analyze(
            code=request.code,
            filename=request.filename or "code.py",
            language=language,
            response_language=request.response_language,
            usage_recorder=lambda rows: db.record_ai_usage(user["id"], rows)
        )

        if analysis_result.get("analysis_available") is False:
            raise HTTPException(
                status_code=503,
                detail=analysis_result.get("summary", "AI analysis service is unavailable")
            )
        
        analysis_result["authorship"] = inspect_authorship(
            request.code, request.filename or "code.py", language
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
        cache.delete(CacheKey.progress_stats(user["id"]))
        
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
        raise HTTPException(status_code=500, detail="The operation could not be completed")

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
        raise HTTPException(status_code=500, detail="The operation could not be completed")

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
        raise HTTPException(status_code=500, detail="The operation could not be completed")

@app.get("/progress")
async def get_progress(request: Request, user=Depends(current_user)):
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
    cached_stats = cache.get(CacheKey.progress_stats(user["id"]))
    if cached_stats is not None:
        metrics.record("progress", "GET", (time.time() - start_time) * 1000, 200)
        return cached_stats

    # Generate stats
    try:
        stats = db.get_progress_stats(user_id=user["id"])
        # Cache for 60 seconds
        cache.set(CacheKey.progress_stats(user["id"]), stats, ttl_seconds=60)
        metrics.record("progress", "GET", (time.time() - start_time) * 1000, 200)
        return stats
    except Exception as e:
        metrics.record("progress", "GET", (time.time() - start_time) * 1000, 500)
        raise HTTPException(status_code=500, detail="The operation could not be completed")

@app.delete("/analysis/{analysis_id}")
async def delete_analysis(analysis_id: str, user=Depends(current_user)):
    """
    Delete analysis from history
    """
    try:
        success = db.delete_analysis(analysis_id, user_id=user["id"])
        if not success:
            raise HTTPException(status_code=404, detail="Analysis not found")
        cache.delete(CacheKey.progress_stats(user["id"]))
        return {"message": "Analysis deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="The operation could not be completed")

@app.get("/stats")
async def get_stats(user=Depends(current_user)):
    """
    Get overall statistics
    """
    try:
        stats = db.get_stats(user["id"])
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail="The operation could not be completed")

@app.get("/todos", response_model=list[TodoItem], dependencies=[Depends(current_user)])
async def get_todos(status: str = Query(default="all", pattern="^(all|active|completed)$"), user=Depends(current_user)):
    """Get the todo list, optionally filtered by completion status."""
    try:
        return db.get_todos(user["id"], None if status == "all" else status)
    except Exception as e:
        raise HTTPException(status_code=500, detail="The operation could not be completed")

@app.post("/todos", response_model=TodoItem, status_code=201, dependencies=[Depends(current_user)])
async def create_todo(todo: TodoCreate, user=Depends(current_user)):
    """Create a todo item."""
    try:
        if not todo.title.strip():
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        return db.create_todo(user["id"], todo.title, todo.description)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="The operation could not be completed")

@app.patch("/todos/{todo_id}", response_model=TodoItem, dependencies=[Depends(current_user)])
async def update_todo(todo_id: str, todo: TodoUpdate, user=Depends(current_user)):
    """Update a todo item."""
    try:
        if todo.title is not None and not todo.title.strip():
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        updated = db.update_todo(user["id"], todo_id, todo.title, todo.description, todo.completed)
        if not updated:
            raise HTTPException(status_code=404, detail="Todo not found")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="The operation could not be completed")

@app.delete("/todos/{todo_id}", dependencies=[Depends(current_user)])
async def delete_todo(todo_id: str, user=Depends(current_user)):
    """Delete a todo item."""
    try:
        if not db.delete_todo(user["id"], todo_id):
            raise HTTPException(status_code=404, detail="Todo not found")
        return {"message": "Todo deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="The operation could not be completed")

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
