#!/usr/bin/env bash
set -euo pipefail

python -m alembic upgrade head
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-10000}"
