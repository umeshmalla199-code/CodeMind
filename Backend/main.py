import sys
from pathlib import Path

# Ensure Backend directory is in sys.path so imports resolve whether run from project root or Backend dir
_backend_path = Path(__file__).resolve().parent
_backend_dir = str(_backend_path)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from dotenv import load_dotenv
load_dotenv(_backend_path / ".env")
load_dotenv(_backend_path.parent / ".env")

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from db.session import SessionLocal
from db.migrate import upgrade_database
from seed.seed_runner import seed_database, _bootstrap_admin
from routes import (
    problems_router,
    topics_router,
    sources_router,
    execution_router,
    tests_router,
    ai_router,
    progress_router,
    mastery_router,
    auth_router,
    admin_router,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Apply every approved schema change before application code touches data.
    upgrade_database()

    db = SessionLocal()
    try:
        seed_database(db, force=False)
        # Ensure the documented bootstrap admin (username `admin`, password
        # `Admin@CodeMind2026!`) is present on every boot so the admin portal is
        # reproducible for new deployments.
        _bootstrap_admin(db)
    finally:
        db.close()
    yield
    # Shutdown: Clean up resources if necessary

app = FastAPI(
    title="CodeMind API",
    description="Scalable problem library and learning platform backend for CodeMind.",
    version="1.0.0",
    lifespan=lifespan
)

import os

# Configurable CORS with explicit origins
_cors_env = os.environ.get("CORS_ORIGINS", "").strip()
if _cors_env:
    ALLOWED_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()]
else:
    ALLOWED_ORIGINS = [
        "null",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

_allow_credentials = "*" not in ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "Frontend"

from fastapi.responses import JSONResponse, FileResponse
import logging

logger = logging.getLogger("codemind.api")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."}
    )

@app.get("/api/health")
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "CodeMind API",
        "database": "connected",
        "execution_languages": ["python", "c", "cpp", "java"],
    }


from typing import Optional
from fastapi import Depends
from sqlalchemy.orm import Session
from db.session import get_db

@app.get("/api/announcements")
def get_public_announcements(
    institute: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Returns active published announcements for students."""
    from datetime import datetime, timezone
    from models.admin_models import Announcement
    now = datetime.now(timezone.utc)
    query = db.query(Announcement).filter(Announcement.status == "published")
    anns = query.order_by(Announcement.created_at.desc()).all()
    results = []
    for a in anns:
        if a.expires_at:
            exp = a.expires_at if a.expires_at.tzinfo else a.expires_at.replace(tzinfo=timezone.utc)
            if now > exp:
                continue
        if a.target == "everyone":
            results.append(a.to_dict())
        elif a.target == "institute" and institute and institute.strip() in (a.target_ids or []):
            results.append(a.to_dict())
    return {"status": "success", "announcements": results}


@app.get("/api/feature-flags")
def get_public_feature_flags(db: Session = Depends(get_db)):
    """Returns enabled feature flags for client applications."""
    from models.admin_models import FeatureFlag
    flags = db.query(FeatureFlag).all()
    return {"status": "success", "flags": {f.key: f.enabled for f in flags}}


# Mount routes
app.include_router(problems_router)
app.include_router(topics_router)
app.include_router(sources_router)
app.include_router(execution_router)
app.include_router(tests_router)
app.include_router(ai_router)
app.include_router(progress_router)
app.include_router(mastery_router)
app.include_router(auth_router)
app.include_router(admin_router)

# Mount static frontend files if FRONTEND_DIR exists
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def serve_frontend_root(request: Request):
        ua = request.headers.get("user-agent", "")
        accept = request.headers.get("accept", "")
        if ua.startswith("Python-urllib") or ("application/json" in accept and "text/html" not in accept):
            return {"message": "CodeMind backend is working!"}
        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"message": "CodeMind backend is working!"}

    @app.get("/mira vrm.vrm")
    def serve_vrm():
        vrm_file = FRONTEND_DIR / "mira vrm.vrm"
        if vrm_file.exists():
            return FileResponse(str(vrm_file))
        return {"error": "Model not found"}, 404
else:
    @app.get("/")
    def home():
        return {"message": "CodeMind backend is working!"}
