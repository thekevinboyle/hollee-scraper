#!/bin/bash
set -e

echo "Running database migrations..."
uv run alembic upgrade head

echo "Starting FastAPI server..."
exec uv run uvicorn og_scraper.api.app:create_app --factory --host 0.0.0.0 --port 8000 --reload
