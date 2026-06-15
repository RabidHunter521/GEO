#!/bin/sh
# Railway "api" service. Applies pending Alembic migrations, then serves the API.
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
