"""Application settings, loaded from environment variables / the root `.env`."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parents[1]
SEED_DIR = REPO_ROOT / "packages" / "seed"


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    PRODUCTION = "production"


class AuthMode(StrEnum):
    SUPABASE = "supabase"
    LOCAL = "local"


class StorageBackend(StrEnum):
    SUPABASE = "supabase"
    LOCAL = "local"


class BotMode(StrEnum):
    POLLING = "polling"
    WEBHOOK = "webhook"
    DISABLED = "disabled"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", API_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Environment = Environment.LOCAL
    log_level: str = "INFO"
    log_json: bool = False
    public_api_url: str = "http://localhost:8000"

    # --- Database / cache ---
    database_url: str = "postgresql://jer:jer@localhost:54322/jer"
    db_pool_size: int = 5
    redis_url: str = "redis://localhost:6379/0"

    # --- HTTP ---
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174"]
    )

    # --- Auth ---
    auth_mode: AuthMode = AuthMode.LOCAL
    supabase_url: str = ""
    supabase_anon_key: SecretStr = SecretStr("")
    supabase_service_role_key: SecretStr = SecretStr("")
    supabase_jwt_secret: SecretStr = SecretStr("")
    local_jwt_secret: SecretStr = SecretStr("local-dev-secret-change-me-please-32b")
    demo_inspector_email: str = "inspector@jer.kz"
    demo_inspector_password: SecretStr = SecretStr("demo12345")
    demo_inspector_name: str = "Инспектор Демо"
    service_api_key: SecretStr = SecretStr("local-service-key")

    # --- Storage ---
    storage_backend: StorageBackend = StorageBackend.LOCAL
    local_storage_dir: Path = API_ROOT / ".storage"
    supabase_storage_bucket: str = "photos"
    signed_url_ttl_seconds: int = 3600

    # --- Telegram ---
    telegram_bot_token: SecretStr = SecretStr("")
    bot_mode: BotMode = BotMode.DISABLED
    telegram_webhook_secret: SecretStr = SecretStr("")
    signals_per_hour_limit: int = 5
    fsm_timeout_minutes: int = 30

    # --- Geo ---
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = "JerBaqylau/0.1 (hackathon demo)"
    # Zhambyl region bounding box: min_lon, min_lat, max_lon, max_lat
    region_bbox: Annotated[tuple[float, float, float, float], NoDecode] = (69.0, 42.2, 75.5, 45.6)

    # --- Background jobs ---
    satellite_scan_interval_minutes: int = 30
    scheduler_enabled: bool = True

    # --- Startup ---
    run_migrations_on_start: bool = False
    seed_on_start: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("region_bbox", mode="before")
    @classmethod
    def _split_bbox(cls, value: Any) -> Any:
        if isinstance(value, str):
            parts = tuple(float(item) for item in value.split(","))
            if len(parts) != 4:
                raise ValueError("REGION_BBOX must be 'min_lon,min_lat,max_lon,max_lat'")
            return parts
        return value

    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        if self.env is Environment.PRODUCTION:
            problems: list[str] = []
            if self.auth_mode is not AuthMode.SUPABASE:
                problems.append("AUTH_MODE must be 'supabase' in production")
            if self.service_api_key.get_secret_value() in {"", "local-service-key"}:
                problems.append("SERVICE_API_KEY must be set in production")
            if self.bot_mode is BotMode.WEBHOOK and not self.telegram_webhook_secret.get_secret_value():
                problems.append("TELEGRAM_WEBHOOK_SECRET is required for webhook mode")
            if problems:
                raise ValueError("; ".join(problems))
        return self

    @property
    def is_production(self) -> bool:
        return self.env is Environment.PRODUCTION

    @property
    def bot_enabled(self) -> bool:
        return self.bot_mode is not BotMode.DISABLED and bool(self.telegram_bot_token.get_secret_value())

    @property
    def async_database_url(self) -> str:
        """Database URL for SQLAlchemy + asyncpg, without libpq-only query params."""
        url = self.database_url
        for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://", "postgresql://", "postgres://"):
            if url.startswith(prefix):
                url = "postgresql+asyncpg://" + url[len(prefix) :]
                break
        base, _, query = url.partition("?")
        kept = [p for p in query.split("&") if p and not p.startswith("sslmode=")]
        return base + ("?" + "&".join(kept) if kept else "")

    @property
    def database_requires_ssl(self) -> bool:
        return "sslmode=require" in self.database_url or "supabase" in self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
