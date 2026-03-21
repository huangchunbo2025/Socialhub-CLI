$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($env:PORT)) {
    $env:PORT = "10000"
}

python -m alembic upgrade head
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $env:PORT
