from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_database_url(url: str, driver: str) -> str:
    normalized = url.strip()
    if normalized.startswith("postgres://"):
        normalized = normalized.replace("postgres://", f"postgresql+{driver}://", 1)
    elif normalized.startswith("postgresql+asyncpg://"):
        normalized = normalized.replace("postgresql+asyncpg://", f"postgresql+{driver}://", 1)
    elif normalized.startswith("postgresql+psycopg://"):
        normalized = normalized.replace("postgresql+psycopg://", f"postgresql+{driver}://", 1)
    elif normalized.startswith("postgresql://"):
        normalized = normalized.replace("postgresql://", f"postgresql+{driver}://", 1)
    return normalized


class Settings(BaseSettings):
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 10000
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/skills_store"
    alembic_database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/skills_store"
    jwt_secret: str = "change-me"
    jwt_expire_hours: int = 24
    package_storage_mode: str = "local"
    package_storage_root: Path = Path("./data/packages")
    ed25519_private_key_path: Path = Path("./secrets/ed25519-private.pem")
    ed25519_public_key_id: str = "ed25519-main"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
settings.database_url = _normalize_database_url(settings.database_url, "asyncpg")
default_sync_url = "postgresql+psycopg://postgres:postgres@localhost:5432/skills_store"
if settings.alembic_database_url == default_sync_url:
    settings.alembic_database_url = settings.database_url
settings.alembic_database_url = _normalize_database_url(settings.alembic_database_url, "psycopg")
