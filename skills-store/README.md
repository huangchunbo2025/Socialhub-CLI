# Skills Store Backend

Minimal FastAPI backend scaffold for the Skills Store MVP.

## Run locally

```bash
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

## Local development

1. Create a virtual environment.
2. Install dependencies from `pyproject.toml`.
3. Copy `.env.example` to `.env`.
4. Start PostgreSQL.
5. Run:

```bash
uvicorn backend.app.main:app --reload
```

## Alembic

Create the database schema with:

```bash
alembic upgrade head
```

## Seed demo data

Create one store admin, one developer, and one published demo skill:

```bash
python backend/seed.py
```

Seeded accounts:

- `admin@skills-store.local` / `Admin123!`
- `developer@skills-store.local` / `Developer123!`

## Deploy on Render

This project includes:

- `render.yaml`
- `start.sh`

Recommended Render setup:

1. Create a Web Service from this repo
2. Root directory: `skills-store`
3. Use `render.yaml`, or set:
   - Build command: `pip install -e .`
   - Start command: `bash ./start.sh`
4. Create a Render Postgres instance
5. Set `DATABASE_URL` and `JWT_SECRET`

The service exposes:

- Health check: `/health`
- OpenAPI: `/openapi.json`
