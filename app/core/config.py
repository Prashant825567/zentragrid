"""Application configuration.

All configuration is environment driven. Secrets are NEVER hardcoded here and
are NEVER returned through any API endpoint.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, List, Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ app
    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    APP_NAME: str = "ZentraGrid"
    API_PREFIX: str = "/v1"
    LOG_LEVEL: str = "INFO"
    PORT: int = 8000

    # ----------------------------------------------------------------- cors
    CORS_ORIGINS: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # ------------------------------------------------------------- telegram
    TG_API_ID: Optional[int] = None
    TG_API_HASH: Optional[str] = None
    TG_SESSION: Optional[str] = None  # Telethon StringSession

    # Private channel identifiers (e.g. -1001234567890). Never exposed via API.
    TG_FILES_CHANNEL: Optional[str] = None
    TG_METADATA_CHANNEL: Optional[str] = None
    TG_OWNERS_CHANNEL: Optional[str] = None

    # Telethon download/upload tuning
    TG_CHUNK_SIZE: int = 512 * 1024  # must divide 1MiB and be a multiple of 4096
    TG_CONNECT_TIMEOUT: int = 30

    # ------------------------------------------------------------- storage
    # "telegram" -> real MTProto storage, "memory" -> in-process (tests/dev only)
    STORAGE_BACKEND: Literal["telegram", "memory"] = "telegram"

    # ------------------------------------------------------------ firebase
    FIREBASE_PROJECT_ID: Optional[str] = None
    FIREBASE_CLIENT_EMAIL: Optional[str] = None
    FIREBASE_PRIVATE_KEY: Optional[str] = None
    # Dev/test escape hatch. MUST stay false in production.
    AUTH_ALLOW_INSECURE_TOKENS: bool = False

    # ------------------------------------------------------------- secrets
    # Pepper used when hashing API keys. Rotating it invalidates all keys.
    API_KEY_PEPPER: str = "change-me-in-production"
    API_KEY_PREFIX: str = "ZTG_live_"

    # --------------------------------------------------------------- files
    MAX_UPLOAD_BYTES: int = 2 * 1024 * 1024 * 1024  # 2 GiB
    # empty = allow every MIME type
    ALLOWED_MIME_TYPES: Annotated[List[str], NoDecode] = Field(default_factory=list)
    BLOCKED_EXTENSIONS: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: [".exe", ".bat", ".cmd", ".com", ".scr", ".msi"]
    )

    # -------------------------------------------------------- rate limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_UPLOAD_PER_MIN: int = 30
    RATE_LIMIT_DOWNLOAD_PER_MIN: int = 120
    RATE_LIMIT_STREAM_PER_MIN: int = 240
    RATE_LIMIT_GENERAL_PER_MIN: int = 300
    RATE_LIMIT_DASHBOARD_PER_MIN: int = 120

    # --------------------------------------------------------------- plans
    DEFAULT_PLAN: str = "free"
    DEFAULT_PLAN_MAX_BYTES: int = 10 * 1024 * 1024 * 1024  # 10 GiB
    DEFAULT_PLAN_MAX_FILES: int = 10_000

    @field_validator("CORS_ORIGINS", "ALLOWED_MIME_TYPES", "BLOCKED_EXTENSIONS", mode="before")
    @classmethod
    def _split_csv(cls, value):
        """Accept either a JSON list or a comma separated string from env."""
        if value is None or value == "":
            return []
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                import json

                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    pass
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("FIREBASE_PRIVATE_KEY", mode="before")
    @classmethod
    def _fix_private_key_newlines(cls, value):
        """Render/Heroku style env vars store the key with literal \\n sequences."""
        if isinstance(value, str):
            return value.replace("\\n", "\n").strip().strip('"')
        return value

    # ------------------------------------------------------------ helpers
    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def telegram_configured(self) -> bool:
        return all(
            [
                self.TG_API_ID,
                self.TG_API_HASH,
                self.TG_SESSION,
                self.TG_FILES_CHANNEL,
                self.TG_METADATA_CHANNEL,
                self.TG_OWNERS_CHANNEL,
            ]
        )

    @property
    def firebase_configured(self) -> bool:
        """True when a full service-account credential is available."""
        return all(
            [self.FIREBASE_PROJECT_ID, self.FIREBASE_CLIENT_EMAIL, self.FIREBASE_PRIVATE_KEY]
        )

    @property
    def auth_configured(self) -> bool:
        """True when ID tokens can be verified at all.

        Only FIREBASE_PROJECT_ID is strictly required: without a service-account
        key the backend verifies tokens against Google's public signing keys.
        """
        return bool(self.FIREBASE_PROJECT_ID) or self.AUTH_ALLOW_INSECURE_TOKENS

    def firebase_credentials_dict(self) -> dict:
        """Service-account shaped dict built from discrete env vars."""
        return {
            "type": "service_account",
            "project_id": self.FIREBASE_PROJECT_ID,
            "client_email": self.FIREBASE_CLIENT_EMAIL,
            "private_key": self.FIREBASE_PRIVATE_KEY,
            "token_uri": "https://oauth2.googleapis.com/token",
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
