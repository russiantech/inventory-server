"""
main.py — Dunis Inventory API entry point  v2
================================================
Based on Intellect LMS patterns.
Fixes:
- CORS: never allow_origins=["*"] with allow_credentials=True (causes 400)
- Origins parsed from comma-separated env var or built from frontend_url
- Proper lifespan with isolated DB seeding
- Static files + exception handler kept from original
- Environment variable handling for host/port
"""

import logging
import os
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings

# ─────────────────────────────────────────────────────────────────────────────
# Config & Logging
# ─────────────────────────────────────────────────────────────────────────────

settings = get_settings()
print(f"Loaded settings: {settings.dict()}")

LOG_LEVEL = logging.DEBUG if settings.development_mode else logging.INFO
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "app.log")


def setup_logging():
    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)
    if root.handlers:
        return

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5)
    fh.setFormatter(fmt)

    root.addHandler(ch)
    root.addHandler(fh)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)


setup_logging()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s API...", settings.site_name)

    os.makedirs(settings.filesystem_base_path, exist_ok=True)

    # Seed roles (safe + isolated)
    try:
        from app.db.session import SessionLocal
        from app.models.rbac import Role

        db = SessionLocal()
        
        default_roles = [
            ("super_admin", "Full system access"),
            ("admin", "Administrative access"),
            ("manager", "Inventory & sales management"),
            ("staff", "Basic staff – sales only"),
        ]

        for name, desc in default_roles:
            exists = db.query(Role).filter(Role.name == name).first()
            if not exists:
                db.add(Role(
                    name=name,
                    description=desc,
                    is_default=(name == "staff")
                ))

        from app.models.category import Category
        
        default_categories = [
            ("Snacks & Beverages", "Snacks and beverages"),
            ("Accessories & Electronics", "Electronic items"),
            ("Laundry, Clothing & Apparel", "Clothing and apparel"),
            # ("Home & Living", "Home and living products"),
        ]

        for name, desc in default_categories:
            exists = db.query(Category).filter(Category.name == name).first()
            if not exists:
                db.add(Category(
                    name=name,
                    desc=desc
                ))

        db.commit()
        db.close()
        logger.info("Default roles and categories seeded.")

    except Exception as e:
        logger.warning("Role seeding skipped: %s", e)

    yield

    logger.info("Shutdown complete.")


# ─────────────────────────────────────────────────────────────────────────────
# App Initialization
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.site_name,
    description=settings.site_description,
    version=settings.api_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    # redirect_slashes=False,  # Optional: prevents automatic redirect from /endpoint to /endpoint/
)

# ─────────────────────────────────────────────────────────────────────────────
# Static Files
# ─────────────────────────────────────────────────────────────────────────────

os.makedirs(settings.filesystem_base_path, exist_ok=True)
app.mount(
    "/uploads",
    StaticFiles(directory=settings.filesystem_base_path),
    name="uploads"
)

_static_dir = Path("static")
_static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


# ─────────────────────────────────────────────────────────────────────────────
# Global Exception Handler
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_id = str(uuid.uuid4())[:8]

    logger.error(
        "[%s] %s %s — %s: %s",
        error_id, request.method, request.url.path,
        type(exc).__name__, exc
    )
    logger.error(traceback.format_exc())

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "An unexpected error occurred.",
            "error_id": error_id,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CORS — FIXED: Never use ["*"] with allow_credentials=True
# ═══════════════════════════════════════════════════════════════════════════════

# Parse origins from comma-separated string or list (if your config supports it)
_cors_origins = getattr(settings, "cors_allowed_origins", None)
if isinstance(_cors_origins, str):
    _cors_origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]
elif not isinstance(_cors_origins, list):
    _cors_origins = []

# Base origins: always include localhost for dev
_base_origins = [
    "http://localhost:5173", 
    "http://localhost:3000", 
    "https://inventory.dunistech.ng", 
    "https://www.inventory.dunistech.ng"
]
# Add the configured frontend_url if present and not already included
if settings.frontend_url and settings.frontend_url not in _base_origins:
    _base_origins.append(settings.frontend_url)

# Merge with any additional CORS origins from config
for origin in _base_origins:
    if origin not in _cors_origins:
        _cors_origins.append(origin)

# Safety: if somehow empty, default to frontend_url only (never "*")
if not _cors_origins:
    _cors_origins = [settings.frontend_url] if settings.frontend_url else ["http://localhost:5173"]

logger.info("CORS allowed origins: %s", _cors_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


# ─────────────────────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────────────────────

from app.api.v1.router import v1_router
from app.api.root import root_router

app.include_router(root_router)
app.include_router(v1_router)


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", settings.port))
    host = os.getenv("HOST", "127.0.0.1")

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=settings.development_mode,
        reload_excludes=["logs/*"],
        log_level="debug" if settings.development_mode else "info",
        access_log=True,
    )

