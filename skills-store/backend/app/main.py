from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine

from .config import settings
from .models import developer, skill, skill_certification, skill_review, skill_version  # noqa: F401
from .models.base import Base
from .routers import admin, auth, developer, public

app = FastAPI(title="Skills Store MVP", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://huangchunbo2025.github.io",
        "http://127.0.0.1:8765",
        "http://localhost:8765",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "null",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def run_startup_migrations() -> None:
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    command.upgrade(config, "head")


def ensure_schema() -> None:
    engine = create_engine(settings.alembic_database_url)
    try:
        Base.metadata.create_all(bind=engine, checkfirst=True)
    finally:
        engine.dispose()


@app.on_event("startup")
async def startup() -> None:
    run_startup_migrations()
    ensure_schema()

app.include_router(auth.router, prefix="/api/v1")
app.include_router(public.router, prefix="/api/v1")
app.include_router(developer.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
