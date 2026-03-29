---
name: docker-local-deployment
description: Docker Compose local deployment with PostgreSQL+PostGIS, FastAPI, Huey, and Next.js. Use when managing containers, environment config, or deployment.
---

# Docker Compose Local Deployment

## What It Is

Docker Compose orchestration for the Oil & Gas Document Scraper local development and deployment environment. Four services run together: a PostgreSQL+PostGIS database, a FastAPI backend, a Huey task queue worker, and a Next.js frontend. Everything runs on the developer's machine with no cloud dependencies.

This is a local-only deployment (DISCOVERY D6). There is no authentication (D7), no paid services (D5), and no cloud hosting. Docker Compose is the single deployment target.

## When To Use This Skill

- Setting up the development environment for the first time
- Modifying `docker-compose.yml` or any `Dockerfile`
- Debugging container startup failures, networking issues, or volume problems
- Configuring environment variables for services
- Running or troubleshooting database migrations
- Managing the Huey worker process
- Deploying for local use on a coworker's machine

---

## Services

### docker-compose.yml

Four services, one custom network (`ogdocs-network`), and shared volumes:

#### 1. `db` -- PostgreSQL 16 + PostGIS 3.4

```yaml
db:
  image: postgis/postgis:16-3.4
  container_name: ogdocs-db
  environment:
    POSTGRES_USER: ${POSTGRES_USER:-ogdocs}
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-ogdocs_dev}
    POSTGRES_DB: ${POSTGRES_DB:-ogdocs}
  ports:
    - "${DB_PORT:-5432}:5432"
  volumes:
    - pgdata:/var/lib/postgresql/data
    - ./backend/scripts/init-db.sql:/docker-entrypoint-initdb.d/01-init.sql
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-ogdocs} -d ${POSTGRES_DB:-ogdocs}"]
    interval: 5s
    timeout: 5s
    retries: 5
    start_period: 10s
  restart: unless-stopped
```

- Uses the `postgis/postgis:16-3.4` image (PostgreSQL 16 with PostGIS 3.4 pre-installed).
- The `init-db.sql` script runs on first container creation to enable the PostGIS extension.
- Port 5432 is exposed to the host for local tooling (psql, pgAdmin). In production overlay, this port is closed.
- Data persists in the `pgdata` named volume across container restarts.

#### 2. `backend` -- FastAPI + Uvicorn

```yaml
backend:
  build:
    context: ./backend
    dockerfile: Dockerfile.dev
  container_name: ogdocs-backend
  environment:
    - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER:-ogdocs}:${POSTGRES_PASSWORD:-ogdocs_dev}@db:5432/${POSTGRES_DB:-ogdocs}
    - SYNC_DATABASE_URL=postgresql://${POSTGRES_USER:-ogdocs}:${POSTGRES_PASSWORD:-ogdocs_dev}@db:5432/${POSTGRES_DB:-ogdocs}
    - DATA_DIR=/app/data
    - HUEY_DB_PATH=/app/data/huey.db
    - DOCUMENTS_DIR=/data/documents
    - LOG_LEVEL=${LOG_LEVEL:-debug}
    - ENVIRONMENT=development
  ports:
    - "${BACKEND_PORT:-8000}:8000"
  volumes:
    - ./backend/src:/app/src
    - ./backend/alembic:/app/alembic
    - documents:/data/documents
    - paddleocr-models:/root/.paddleocr
  depends_on:
    db:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health')"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 30s
  restart: unless-stopped
```

- Built from `backend/Dockerfile.dev` using Python 3.13-slim + uv.
- `DATABASE_URL` uses `asyncpg` driver for async SQLAlchemy operations.
- `SYNC_DATABASE_URL` uses the standard `postgresql://` scheme, required by Alembic (which does not support async).
- `DATA_DIR` and `HUEY_DB_PATH` point to the mounted data volume where Huey stores its SQLite queue database.
- Source code bind-mounted at `/app/src` and `/app/alembic` for hot reload via `uvicorn --reload`.
- `start_period: 30s` because PaddleOCR model loading is slow on first boot.
- Alembic migrations run automatically on backend startup (`alembic upgrade head`).

#### 3. `worker` -- Huey Task Queue Worker

```yaml
worker:
  build:
    context: ./backend
    dockerfile: Dockerfile.dev
  container_name: ogdocs-worker
  entrypoint: ["uv", "run", "huey_consumer", "src.worker.main.huey", "-w", "2", "-k", "thread"]
  environment:
    - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER:-ogdocs}:${POSTGRES_PASSWORD:-ogdocs_dev}@db:5432/${POSTGRES_DB:-ogdocs}
    - SYNC_DATABASE_URL=postgresql://${POSTGRES_USER:-ogdocs}:${POSTGRES_PASSWORD:-ogdocs_dev}@db:5432/${POSTGRES_DB:-ogdocs}
    - DATA_DIR=/app/data
    - HUEY_DB_PATH=/app/data/huey.db
    - DOCUMENTS_DIR=/data/documents
    - LOG_LEVEL=${LOG_LEVEL:-debug}
    - ENVIRONMENT=development
  volumes:
    - ./backend/src:/app/src
    - documents:/data/documents
    - paddleocr-models:/root/.paddleocr
  depends_on:
    db:
      condition: service_healthy
  restart: unless-stopped
```

- Uses the **same image** as `backend` but with a **different entrypoint**: `huey_consumer` instead of `uvicorn`.
- Huey uses `SqliteHuey` with the database file at `/app/data/huey.db` -- no Redis or RabbitMQ required.
- The `-w 2` flag runs 2 worker threads; `-k thread` uses thread-based workers (suitable for I/O-bound OCR/scraping tasks).
- **Must share the same `documents` volume** as `backend` so it can read/write document files.
- **Must share the same `paddleocr-models` volume** so PaddleOCR models are cached and available.

#### 4. `frontend` -- Next.js Dev Server

```yaml
frontend:
  build:
    context: ./frontend
    dockerfile: Dockerfile.dev
  container_name: ogdocs-frontend
  environment:
    - NEXT_PUBLIC_API_URL=http://localhost:${BACKEND_PORT:-8000}
    - WATCHPACK_POLLING=true
  ports:
    - "${FRONTEND_PORT:-3000}:3000"
  volumes:
    - ./frontend/src:/app/src
    - ./frontend/public:/app/public
    - frontend-node-modules:/app/node_modules
  depends_on:
    backend:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:3000"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 20s
  restart: unless-stopped
```

- Built from `frontend/Dockerfile.dev` using Node 22-alpine + pnpm.
- `WATCHPACK_POLLING=true` is required for file-watching to work inside Docker containers.
- `node_modules` is stored in a named volume (`frontend-node-modules`) to avoid slow bind-mount performance on macOS.
- Source code and public assets are bind-mounted for hot reload.

---

## Environment Variables

### Required Variables

| Variable | Value | Used By | Purpose |
|----------|-------|---------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@db:5432/ogdocs` | backend, worker | Async SQLAlchemy database connection |
| `SYNC_DATABASE_URL` | `postgresql://postgres:postgres@db:5432/ogdocs` | backend | Alembic migrations (sync driver only) |
| `DATA_DIR` | `/app/data` | backend, worker | Mounted volume for document storage |
| `HUEY_DB_PATH` | `/app/data/huey.db` | backend, worker | Huey SQLite queue database location |
| `DOCUMENTS_DIR` | `/data/documents` | backend, worker | Original document storage root |

### Configurable Variables (with defaults)

| Variable | Default | Purpose |
|----------|---------|---------|
| `POSTGRES_USER` | `ogdocs` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `ogdocs_dev` | PostgreSQL password |
| `POSTGRES_DB` | `ogdocs` | PostgreSQL database name |
| `DB_PORT` | `5432` | Host port for PostgreSQL |
| `BACKEND_PORT` | `8000` | Host port for FastAPI |
| `FRONTEND_PORT` | `3000` | Host port for Next.js |
| `LOG_LEVEL` | `debug` | Backend/worker log verbosity |
| `OCR_CONFIDENCE_THRESHOLD` | `0.80` | Minimum OCR confidence to accept |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | API URL used by the browser |

### .env File Setup

Copy `.env.example` to `.env` and customize values. The `.env` file is in `.gitignore`; `.env.example` is committed to the repo.

---

## Volumes

### Named Volumes (Docker-managed, persistent)

| Volume | Mount Point | Purpose |
|--------|-------------|---------|
| `pgdata` | `/var/lib/postgresql/data` | PostgreSQL data files. Survives container recreation. |
| `documents` | `/data/documents` | Original scraped documents, organized as `data/{state}/{operator}/{doc_type}/`. Shared between backend and worker. |
| `paddleocr-models` | `/root/.paddleocr` | Cached PaddleOCR model files (~1.5 GB). Avoids re-downloading on container rebuild. |
| `frontend-node-modules` | `/app/node_modules` | Persisted node_modules. Avoids slow npm installs on bind mounts. |

### Bind Mounts (development only, for hot reload)

| Host Path | Container Path | Service | Purpose |
|-----------|---------------|---------|---------|
| `./backend/src` | `/app/src` | backend, worker | Python source code hot reload |
| `./backend/alembic` | `/app/alembic` | backend | Alembic migration files |
| `./frontend/src` | `/app/src` | frontend | Next.js source code hot reload |
| `./frontend/public` | `/app/public` | frontend | Static assets hot reload |

---

## Development Workflow

### Starting Services

```bash
# Start everything (database, backend, worker, frontend)
docker compose up

# Start in detached mode (background)
docker compose up -d

# Start only the database (for running backend/frontend outside Docker)
docker compose up -d db

# View logs for a specific service
docker compose logs -f backend
docker compose logs -f worker
```

### Running Backend and Frontend Outside Docker

For faster development iteration, run only the database in Docker and run backend/frontend natively:

```bash
# Terminal 1: Database only
docker compose up -d db

# Terminal 2: Backend (requires uv installed locally)
cd backend
export DATABASE_URL="postgresql+asyncpg://ogdocs:ogdocs_dev@localhost:5432/ogdocs"
export SYNC_DATABASE_URL="postgresql://ogdocs:ogdocs_dev@localhost:5432/ogdocs"
uv run uvicorn src.app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 3: Huey worker
cd backend
uv run huey_consumer src.worker.main.huey -w 2 -k thread

# Terminal 4: Frontend (requires pnpm installed locally)
cd frontend
pnpm dev
```

### Database Migrations

```bash
# Run pending migrations (also runs on backend startup)
docker compose exec backend uv run alembic upgrade head

# Create a new migration after model changes
docker compose exec backend uv run alembic revision --autogenerate -m "add_new_column"

# Check current migration status
docker compose exec backend uv run alembic current
```

### Rebuilding Containers

```bash
# Rebuild all images (after Dockerfile or dependency changes)
docker compose build --no-cache

# Rebuild a single service
docker compose build --no-cache backend

# Stop everything and remove volumes (DESTRUCTIVE -- deletes database data)
docker compose down -v
```

### Database Access

```bash
# Open psql shell
docker compose exec db psql -U ogdocs -d ogdocs

# Check service health
docker compose exec db pg_isready -U ogdocs
```

### Justfile Shortcuts

If `just` is installed (`brew install just`), the project provides a `justfile` with shortcuts:

```
just up          # docker compose up -d
just down        # docker compose down
just logs        # docker compose logs -f backend
just migrate     # Run Alembic migrations
just psql        # Open database shell
just test        # Run all tests
just lint        # Run all linters
just health      # Check all service health
```

---

## Networking

All services communicate over the `ogdocs-network` Docker bridge network using service names as hostnames:

```
frontend (port 3000) --> backend (port 8000) --> db (port 5432)
                              |
                              v
                    documents volume (/data/documents)
                              ^
                              |
                         worker (no exposed port)
```

- `frontend` calls the backend API at `http://backend:8000` (server-side rendering) or `http://localhost:8000` (client-side browser requests).
- `backend` and `worker` connect to the database at `db:5432`.
- `worker` has no exposed ports -- it only consumes tasks from the Huey SQLite queue and writes results to the database and document volume.
- The database port is exposed to the host only for development tooling (psql, pgAdmin).

---

## Common Pitfalls

### 1. PostGIS Extension Not Created

The `postgis/postgis:16-3.4` image includes PostGIS but the extension must be explicitly created in the database. The `init-db.sql` script handles this:

```sql
-- backend/scripts/init-db.sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- for full-text search trigrams
```

If you see errors like `type "geometry" does not exist`, the extension was not created. Run manually:

```bash
docker compose exec db psql -U ogdocs -d ogdocs -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

### 2. PaddleOCR on ARM64 / Apple Silicon

PaddleOCR in Docker on Apple Silicon (M1/M2/M3/M4) needs attention:
- Use `python:3.13-slim` as the base image (supports ARM64 natively).
- PaddlePaddle >= 3.2.x runs on ARM64 without Rosetta.
- CPU-only mode -- no GPU acceleration on macOS.
- System dependencies required in the Dockerfile: `libgl1`, `libglib2.0-0`, `libgomp1`.
- First run downloads ~1.5 GB of OCR models; the `paddleocr-models` volume caches these across rebuilds.
- If builds fail with architecture errors, verify Docker Desktop is set to use the native `linux/arm64` platform, not Rosetta emulation.

### 3. Huey Worker Must Share Volumes

The worker container must have access to:
- The same `documents` volume as backend (it reads/writes document files during processing).
- The same `paddleocr-models` volume (it runs OCR on documents).
- The same `DATA_DIR` path where `huey.db` lives (both backend and worker read/write the Huey SQLite queue file).

If the worker cannot find documents or the queue is not shared, tasks will silently fail.

### 4. Docker Desktop Must Be Running

Before running `docker compose up`, Docker Desktop (or the Docker daemon) must be running. Common error:

```
Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?
```

On macOS: open Docker Desktop and wait for the status indicator to show "Running" before executing compose commands.

### 5. Port Conflicts

If ports 5432, 8000, or 3000 are already in use on the host, change them in `.env`:

```bash
DB_PORT=5433
BACKEND_PORT=8001
FRONTEND_PORT=3001
```

### 6. Volume Permissions on Linux

On Linux hosts, files created inside Docker containers may be owned by root. If you encounter permission errors accessing mounted volumes:

```bash
# Fix ownership of bind-mounted directories
sudo chown -R $USER:$USER ./backend/src ./frontend/src ./data
```

### 7. Hot Reload Not Working

- **Backend**: Verify `uvicorn --reload` is in the CMD and source code is bind-mounted at `/app/src`.
- **Frontend**: Verify `WATCHPACK_POLLING=true` is set. File-watching via inotify does not work across Docker bind mounts on macOS; polling is required.
- **Worker**: The Huey consumer does not hot reload automatically. Restart the worker after code changes: `docker compose restart worker`.

---

## Testing

Tests use **testcontainers** to spin up their own isolated PostgreSQL+PostGIS container, completely separate from the development database. No test data ever touches the dev `pgdata` volume.

```python
# tests/conftest.py
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer(
        image="postgis/postgis:16-3.4",
        username="test",
        password="test",
        dbname="test_ogdocs",
    ) as postgres:
        yield postgres
```

- The test container starts fresh for each test session and is destroyed afterward.
- Docker must be running to execute tests (testcontainers launches real containers).
- Tests are marked with `@pytest.mark.integration` for slow integration tests and `@pytest.mark.slow` for OCR-dependent tests, allowing selective test execution:
  ```bash
  uv run pytest -x -v -m "not slow and not integration"  # fast tests only
  ```

---

## Cost

Free. All services run locally on Docker. No cloud resources, no paid APIs, no external services (per DISCOVERY D6). PaddleOCR is the sole OCR engine (free, local-only, per D5). PostgreSQL, PostGIS, Huey, and Next.js are all open source.

---

## References

- Discovery document: `.claude/orchestration-og-doc-scraper/DISCOVERY.md` (decisions D5, D6, D7)
- Docker Compose and deployment research: `.claude/orchestration-og-doc-scraper/research/testing-deployment-implementation.md` (sections 5 and 6)
- Architecture, database, and task queue research: `.claude/orchestration-og-doc-scraper/research/architecture-storage.md` (sections 1, 7, 12, 16)
- Document pipeline and Huey integration: `.claude/orchestration-og-doc-scraper/research/document-pipeline-implementation.md` (section 6)
