# app/core/config/models.py
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from functools import lru_cache

class AppSettings(BaseSettings):

    # Security
    auth_jwt_secret_key: str = Field("changeme", alias="APP_AUTH_JWT_SECRET_KEY")
    jwt_algorithm: str = Field("HS256", alias="APP_JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(1440, alias="APP_ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_minutes: int = Field(10080, alias="APP_REFRESH_TOKEN_EXPIRE_MINUTES")

    # App
    site_name: str = Field("Dunis Inventory", alias="APP_SITE_NAME")
    site_description: str = Field("Inventory Management System", alias="APP_SITE_DESCRIPTION")
    api_version: str = Field("1.0.0", alias="APP_API_VERSION")
    api_prefix: str = Field("/api/v1", alias="APP_API_PREFIX")
    frontend_url: str = Field("http://localhost:5173", alias="APP_FRONTEND_URL")
    whatsapp_community_link: str = Field('https:dunistech.ng', alias="APP_WHATSAPP_LINK")
    filesystem_base_path: str = Field("./uploads", alias="APP_FILESYSTEM_BASE_PATH")
    development_mode: bool = Field(True, alias="APP_DEVELOPMENT_MODE")
    port: int = Field(8002, alias="APP_PORT")
    domain: str = Field("localhost", alias="APP_DOMAIN")

    # Database
    database_url: str = Field("postgresql://postgres:postgres@localhost:5432/imf_db", alias="APP_DATABASE_URL")

    # Redis
    redis_url: str = Field("redis://localhost:6379/0", alias="APP_REDIS_URL")

    # ------------------------------------------------------------------
    # Email — provider selection: "console" | "smtp" | "sendgrid" | "mailgun" | "resend"
    # ------------------------------------------------------------------
    provider: str = Field("console", alias="APP_MAIL_PROVIDER")
    mail_sender_name: str = Field("IMF", alias="APP_EMAIL_SENDER_NAME")
    mail_sender_email: str = Field("noreply@example.com", alias="APP_MAIL_SENDER_EMAIL")

    # SMTP / Sendgrid / Mailgun (all use the smtp transport in email_service)
    smtp_host: str = Field("smtp.gmail.com", alias="APP_SMTP_HOST")
    smtp_port: int = Field(587, alias="APP_SMTP_PORT")
    smtp_username: str = Field("", alias="APP_SMTP_USERNAME")
    smtp_password: str = Field("", alias="APP_SMTP_PASSWORD")
    smtp_use_tls: bool = Field(True, alias="APP_SMTP_USE_TLS")
    smtp_use_ssl: bool = Field(False, alias="APP_SMTP_USE_SSL")
    smtp_timeout: int = Field(10, alias="APP_SMTP_TIMEOUT")

    # Resend
    resend_api_key: str = Field("", alias="APP_RESEND_API_KEY")

    # Paystack
    paystack_secret_key: str = Field("", alias="APP_PAYSTACK_SECRET_KEY")
    paystack_public_key: str = Field("", alias="APP_PAYSTACK_PUBLIC_KEY")

    model_config = {"env_file": ".env", "extra": "ignore", "populate_by_name": True}


_settings: Optional[AppSettings] = None

@lru_cache
def get_settings() -> AppSettings:
    global _settings
    if _settings is None:
        _settings = AppSettings()
    return _settings
