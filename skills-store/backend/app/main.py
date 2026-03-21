from fastapi import FastAPI

from .routers import admin, auth, developer, public

app = FastAPI(title="Skills Store MVP", version="0.1.0")

app.include_router(auth.router, prefix="/api/v1")
app.include_router(public.router, prefix="/api/v1")
app.include_router(developer.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
