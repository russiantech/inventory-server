# app/api/root.py
from fastapi import APIRouter
from app.core.config import get_settings
from app.utils.responses import api_response

root_router = APIRouter()
settings = get_settings()


@root_router.get("/", tags=["Root"])
async def root():
    return api_response(True, f"{settings.site_name} API is running.", data={"version": settings.api_version})


@root_router.get("/health", tags=["Root"])
async def health():
    return {"status": "ok", "app": settings.site_name}
