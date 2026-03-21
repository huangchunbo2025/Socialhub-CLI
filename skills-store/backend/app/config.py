from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


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


if settings.alembic_database_url == "postgresql+psycopg://postgres:postgres@localhost:5432/skills_store":
    settings.alembic_database_url = settings.database_url.replace("+asyncpg", "+psycopg", 1)
