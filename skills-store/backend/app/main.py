from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI

from .routers import admin, auth, developer, public

app = FastAPI(title="Skills Store MVP", version="0.1.0")


def run_startup_migrations() -> None:
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    command.upgrade(config, "head")


@app.on_event("startup")
async def startup() -> None:
    run_startup_migrations()

app.include_router(auth.router, prefix="/api/v1")
app.include_router(public.router, prefix="/api/v1")
app.include_router(developer.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
