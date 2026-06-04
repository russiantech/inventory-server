import os
import uuid
import logging
import traceback
from datetime import datetime
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.api.v1.router import v1_router
from app.api.root import root_router


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

settings = get_settings()

LOG_LEVEL = logging.DEBUG if settings.development_mode else logging.INFO

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "app.log")


# ─────────────────────────────────────────────────────────────────────────────
# Logging Setup (Clean & Non-duplicating)
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)

    if logger.handlers:
        return  # جلوگیری از duplicate handlers

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        "%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # Reduce noisy logs
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)


setup_logging()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan (Startup / Shutdown)
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.site_name} API...")

    # Ensure upload directory exists
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

        db.commit()
        db.close()

        logger.info("Default roles seeded.")

    except Exception as e:
        logger.warning(f"Role seeding skipped: {e}")

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


# ─────────────────────────────────────────────────────────────────────────────
# Global Exception Handler
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_id = str(uuid.uuid4())[:8]

    logger.error(
        f"[{error_id}] {request.method} {request.url.path} "
        f"— {type(exc).__name__}: {exc}"
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


# ─────────────────────────────────────────────────────────────────────────────
# Middleware
# ─────────────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.development_mode else [settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


# ─────────────────────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────────────────────

app.include_router(root_router)
app.include_router(v1_router)


# ─────────────────────────────────────────────────────────────────────────────
# Run (Single Source of Truth)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", settings.port)),
        reload=settings.development_mode,
        reload_excludes=["logs/*"],  # prevent log loop
        log_level="debug" if settings.development_mode else "info",
        access_log=True,
    )
