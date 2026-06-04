# app/core/config/models.py
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class AppSettings(BaseSettings):
    # Security
    auth_jwt_secret_key: str = Field("changeme", alias="APP_AUTH_JWT_SECRET_KEY")
    jwt_algorithm: str = Field("HS256", alias="APP_JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(1440, alias="APP_ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_minutes: int = Field(10080, alias="APP_REFRESH_TOKEN_EXPIRE_MINUTES")

    # App
    site_name: str = Field("IMF", alias="APP_SITE_NAME")
    site_description: str = Field("Inventory Management System", alias="APP_SITE_DESCRIPTION")
    api_version: str = Field("1.0.0", alias="APP_API_VERSION")
    api_prefix: str = Field("/api/v1", alias="APP_API_PREFIX")
    frontend_url: str = Field("http://localhost:5173", alias="APP_FRONTEND_URL")
    filesystem_base_path: str = Field("./uploads", alias="APP_FILESYSTEM_BASE_PATH")
    development_mode: bool = Field(True, alias="APP_DEVELOPMENT_MODE")
    port: int = Field(8000, alias="APP_PORT")
    domain: str = Field("localhost", alias="APP_DOMAIN")

    # Database
    database_url: str = Field("postgresql://postgres:postgres@localhost:5432/imf_db", alias="APP_DATABASE_URL")

    # Redis
    redis_url: str = Field("redis://localhost:6379/0", alias="APP_REDIS_URL")

    model_config = {"env_file": ".env", "extra": "ignore", "populate_by_name": True}


_settings: Optional[AppSettings] = None


def get_settings() -> AppSettings:
    global _settings
    if _settings is None:
        _settings = AppSettings()
    return _settings
