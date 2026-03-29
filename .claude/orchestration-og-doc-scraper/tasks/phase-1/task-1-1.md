# Task 1.1: Project Scaffolding

## Objective

Create the complete monorepo structure for the Oil & Gas Document Scraper with UV Python workspace, Next.js frontend, Docker Compose for all 4 services (db, backend, worker, frontend), and dev tooling (justfile, ruff, .gitignore). This task lays the foundation that every subsequent task builds upon.

## Context

This is the very first task of the project. Nothing exists yet -- you are creating the entire repository from scratch. Every subsequent task in every phase depends on the project structure, dependency manifests, Docker Compose configuration, and development tooling established here. The project is a monorepo with a Python backend (FastAPI + Scrapy + PaddleOCR), a Next.js frontend, and Docker Compose for local deployment.

Key constraints from DISCOVERY.md:
- Local deployment only (Docker Compose on laptop/desktop) -- D6
- No authentication -- D7
- No paid APIs -- D5
- Python 3.12+ backend, Next.js frontend -- D4
- Huey task queue with SQLite backend (NOT Redis) -- no Redis service needed
- UV for Python package management, npm for Node

## Dependencies

- None (first task)

## Blocked By

- None (first task)

## Research Findings

Key findings from research files relevant to this task:

- From `architecture-storage.md`: PostgreSQL with JSONB hybrid pattern is the primary database. Monorepo structure with UV workspace for Python packages.
- From `backend-schema-implementation.md`: Docker Compose has 4 services: db (postgis/postgis:16-3.4), backend (FastAPI), worker (Huey), frontend (Next.js). Huey uses SQLite backend, NOT Redis.
- From `docker-local-deployment` skill: Detailed Docker Compose YAML for all 4 services with health checks, volumes, networking. Environment variable defaults: POSTGRES_USER=ogdocs, POSTGRES_PASSWORD=ogdocs_dev, POSTGRES_DB=ogdocs.

## Implementation Plan

### Step 1: Create Root Project Files

Create the root `pyproject.toml` as a UV workspace that references the backend package:

```toml
# pyproject.toml (root)
[project]
name = "og-doc-scraper"
version = "0.1.0"
description = "Oil & Gas Document Scraper - scrapes regulatory documents from 10 US state agencies"
requires-python = ">=3.12"

[tool.uv.workspace]
members = ["backend"]
```

Create `.python-version`:
```
3.12
```

Create `ruff.toml`:
```toml
target-version = "py312"
line-length = 120
src = ["backend/src"]

[lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "SIM", "TCH"]
ignore = ["E501"]

[lint.isort]
known-first-party = ["og_scraper"]

[format]
quote-style = "double"
indent-style = "space"
```

Create `.gitignore` with entries for:
- Python: `__pycache__/`, `.venv/`, `*.pyc`, `.ruff_cache/`, `dist/`, `*.egg-info/`
- Node: `node_modules/`, `.next/`, `.turbo/`
- Data: `data/documents/`, `data/exports/`
- Environment: `.env`, `*.db`
- Docker: (no ignores needed)
- IDE: `.idea/`, `.vscode/`, `*.swp`
- OS: `.DS_Store`, `Thumbs.db`

### Step 2: Create Backend Python Package

Create `backend/pyproject.toml`:

```toml
[project]
name = "og-scraper"
version = "0.1.0"
description = "Oil & Gas Document Scraper Backend"
requires-python = ">=3.12"
dependencies = [
    # API
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "sse-starlette>=2.0.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.7.0",
    # Database
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "geoalchemy2>=0.15.0",
    # Task Queue
    "huey>=2.5.2",
    # Scraping
    "scrapy>=2.12.0",
    "scrapy-playwright>=0.0.43",
    "httpx>=0.28.0",
    # OCR & PDF
    "paddleocr>=3.0.0",
    "pymupdf4llm>=0.0.17",
    # Processing
    "tenacity>=9.0.0",
    "pybreaker>=1.2.0",
    # Logging
    "structlog>=24.4.0",
    # Utilities
    "python-multipart>=0.0.18",
    # State-specific parsers (Phase 4+6)
    "ebcdic-parser>=0.3.0",
    "pyproj>=3.7.0",
    "openpyxl>=3.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=6.0.0",
    "httpx>=0.28.0",
    "testcontainers>=4.9.0",
    "vcrpy>=7.0.0",
    "ruff>=0.8.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/og_scraper"]
```

Create the backend source directory structure:

- `backend/src/og_scraper/__init__.py` -- package init with `__version__ = "0.1.0"`
- `backend/src/og_scraper/models/__init__.py` -- empty, will be populated in Task 1.2
- `backend/src/og_scraper/schemas/__init__.py` -- empty
- `backend/src/og_scraper/api/__init__.py` -- empty
- `backend/src/og_scraper/api/routes/__init__.py` -- empty
- `backend/src/og_scraper/services/__init__.py` -- empty
- `backend/src/og_scraper/scrapers/__init__.py` -- empty
- `backend/src/og_scraper/pipeline/__init__.py` -- empty
- `backend/src/og_scraper/utils/__init__.py` -- empty
- `backend/tests/__init__.py` -- empty
- `backend/tests/conftest.py` -- empty for now (will be filled in Task 1.2)

Also create placeholder directories via empty `__init__.py` files for the scraper sub-packages:
- `backend/src/og_scraper/scrapers/spiders/__init__.py`
- `backend/src/og_scraper/scrapers/pipelines/__init__.py`
- `backend/src/og_scraper/scrapers/middlewares/__init__.py`
- `backend/src/og_scraper/scrapers/adapters/__init__.py`
- `backend/src/og_scraper/scrapers/parsers/__init__.py`

### Step 3: Create Backend Dockerfile

Create `backend/Dockerfile.dev`:

```dockerfile
FROM python:3.12-slim

# System dependencies for PaddleOCR and PostgreSQL client
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files first for caching
COPY pyproject.toml ./

# Install dependencies
RUN uv sync --no-dev --no-install-project

# Copy source code
COPY . .

# Install the project itself
RUN uv sync --no-dev

# Install Playwright browsers
RUN uv run playwright install chromium --with-deps

EXPOSE 8000

COPY scripts/start.sh /app/scripts/start.sh
RUN chmod +x /app/scripts/start.sh

CMD ["/app/scripts/start.sh"]
```

Create `backend/scripts/start.sh` (runs Alembic migrations then starts the server):

```bash
#!/bin/bash
set -e

echo "Running database migrations..."
uv run alembic upgrade head

echo "Starting FastAPI server..."
exec uv run uvicorn og_scraper.api.app:create_app --factory --host 0.0.0.0 --port 8000 --reload
```

### Step 4: Create Frontend Next.js Project

Create `frontend/package.json`:

```json
{
  "name": "og-doc-scraper-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev --port 3000",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "type-check": "tsc --noEmit"
  },
  "dependencies": {
    "next": "^15.3.0",
    "react": "^19.1.0",
    "react-dom": "^19.1.0",
    "leaflet": "^1.9.4",
    "react-leaflet": "^5.0.0",
    "react-pdf": "^9.2.1",
    "recharts": "^2.15.0",
    "swr": "^2.2.0",
    "@tanstack/react-table": "^8.21.0",
    "use-supercluster": "^1.2.0",
    "supercluster": "^8.0.1",
    "clsx": "^2.1.1",
    "tailwind-merge": "^3.0.0",
    "class-variance-authority": "^0.7.1",
    "lucide-react": "^0.482.0"
  },
  "devDependencies": {
    "@types/node": "^22.14.0",
    "@types/react": "^19.1.0",
    "@types/react-dom": "^19.1.0",
    "@types/leaflet": "^1.9.16",
    "typescript": "^5.8.0",
    "tailwindcss": "^4.1.0",
    "@tailwindcss/postcss": "^4.1.0",
    "postcss": "^8.5.0",
    "eslint": "^9.24.0",
    "eslint-config-next": "^15.3.0",
    "@eslint/eslintrc": "^3.3.1"
  }
}
```

Create `frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

Create `frontend/next.config.ts`:

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
```

Create `frontend/postcss.config.mjs`:

```javascript
/** @type {import('postcss-load-config').Config} */
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
```

Create `frontend/src/app/globals.css`:

```css
@import "tailwindcss";
```

Create `frontend/src/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Oil & Gas Document Scraper",
  description: "Search and browse regulatory documents from 10 US state agencies",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background antialiased">
        {children}
      </body>
    </html>
  );
}
```

Create `frontend/src/app/page.tsx`:

```tsx
export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <h1 className="text-4xl font-bold">Oil &amp; Gas Document Scraper</h1>
      <p className="mt-4 text-lg text-gray-600">Dashboard coming soon</p>
    </main>
  );
}
```

Create `frontend/Dockerfile.dev`:

```dockerfile
FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
```

### Step 5: Create Docker Compose

Create `docker-compose.yml` at project root:

```yaml
services:
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

  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile.dev
    container_name: ogdocs-worker
    entrypoint: ["uv", "run", "huey_consumer", "og_scraper.worker.huey_app", "-w", "2", "-k", "thread"]
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
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:3000"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s
    restart: unless-stopped

volumes:
  pgdata:
  documents:
  paddleocr-models:
  frontend-node-modules:

networks:
  default:
    name: ogdocs-network
```

Create `backend/scripts/init-db.sql`:

```sql
-- Enable required PostgreSQL extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

### Step 6: Create Environment and Config Files

Create `.env.example`:

```bash
# Database
POSTGRES_USER=ogdocs
POSTGRES_PASSWORD=ogdocs_dev
POSTGRES_DB=ogdocs

# Ports (change if conflicts with existing services)
DB_PORT=5432
BACKEND_PORT=8000
FRONTEND_PORT=3000

# Logging
LOG_LEVEL=debug

# OCR
OCR_CONFIDENCE_THRESHOLD=0.80
```

### Step 7: Create Justfile

Create `justfile` at project root:

```just
# Oil & Gas Document Scraper - Development Commands

# Default: list available commands
default:
    @just --list

# Start all services in background
up:
    docker compose up -d

# Stop all services
down:
    docker compose down

# View logs for all services (follow mode)
logs *args='':
    docker compose logs -f {{args}}

# View backend logs
logs-backend:
    docker compose logs -f backend

# View worker logs
logs-worker:
    docker compose logs -f worker

# Start only the database
db:
    docker compose up -d db

# Open psql shell
psql:
    docker compose exec db psql -U ogdocs -d ogdocs

# Run Alembic migrations
migrate:
    docker compose exec backend uv run alembic upgrade head

# Create a new migration
migration name:
    docker compose exec backend uv run alembic revision --autogenerate -m "{{name}}"

# Check migration status
migrate-status:
    docker compose exec backend uv run alembic current

# Run all Python tests
test *args='':
    cd backend && uv run pytest {{args}}

# Run tests with coverage
test-cov:
    cd backend && uv run pytest --cov=og_scraper --cov-report=term-missing

# Lint Python code
lint:
    cd backend && uv run ruff check src/ tests/

# Format Python code
fmt:
    cd backend && uv run ruff format src/ tests/

# Lint and format
lint-fix:
    cd backend && uv run ruff check --fix src/ tests/ && uv run ruff format src/ tests/

# Check health of all services
health:
    @echo "--- Database ---" && docker compose exec db pg_isready -U ogdocs && echo "--- Backend ---" && curl -s http://localhost:8000/health | python3 -m json.tool && echo "--- Frontend ---" && curl -s -o /dev/null -w "%{http_code}" http://localhost:3000

# Rebuild all Docker images
rebuild:
    docker compose build --no-cache

# Stop and remove all volumes (DESTRUCTIVE)
nuke:
    docker compose down -v

# Install Python dependencies locally (outside Docker)
install:
    cd backend && uv sync

# Install frontend dependencies locally (outside Docker)
install-frontend:
    cd frontend && npm install
```

### Step 8: Create Data Directories

Create the following empty directories with `.gitkeep` files:
- `data/documents/.gitkeep`
- `data/exports/.gitkeep`
- `config/states/.gitkeep`

These directories are referenced by the Docker Compose volumes and the file storage pipeline.

### Step 9: Create frontend/public directory

Create `frontend/public/.gitkeep` as a placeholder for static assets.

## Files to Create

- `pyproject.toml` - Root UV workspace config
- `.python-version` - Python version pin (3.12)
- `.gitignore` - Ignore patterns for Python, Node, data, Docker, IDE
- `ruff.toml` - Ruff linter/formatter config
- `justfile` - Development task runner commands
- `.env.example` - Environment variable template
- `docker-compose.yml` - 4 services: db, backend, worker, frontend
- `backend/pyproject.toml` - Python package with all dependencies
- `backend/Dockerfile.dev` - Development Dockerfile for backend/worker
- `backend/scripts/init-db.sql` - PostGIS + pg_trgm extension setup
- `backend/src/og_scraper/__init__.py` - Package init with version
- `backend/src/og_scraper/models/__init__.py` - Empty placeholder
- `backend/src/og_scraper/schemas/__init__.py` - Empty placeholder
- `backend/src/og_scraper/api/__init__.py` - Empty placeholder
- `backend/src/og_scraper/api/routes/__init__.py` - Empty placeholder
- `backend/src/og_scraper/services/__init__.py` - Empty placeholder
- `backend/src/og_scraper/scrapers/__init__.py` - Empty placeholder
- `backend/src/og_scraper/scrapers/spiders/__init__.py` - Empty placeholder
- `backend/src/og_scraper/scrapers/pipelines/__init__.py` - Empty placeholder
- `backend/src/og_scraper/scrapers/middlewares/__init__.py` - Empty placeholder
- `backend/src/og_scraper/scrapers/adapters/__init__.py` - Empty placeholder
- `backend/src/og_scraper/scrapers/parsers/__init__.py` - Empty placeholder
- `backend/src/og_scraper/pipeline/__init__.py` - Empty placeholder
- `backend/src/og_scraper/utils/__init__.py` - Empty placeholder
- `backend/tests/__init__.py` - Empty
- `backend/tests/conftest.py` - Empty placeholder
- `frontend/package.json` - Next.js + all frontend deps
- `frontend/tsconfig.json` - TypeScript config
- `frontend/next.config.ts` - Next.js config (standalone output)
- `frontend/postcss.config.mjs` - PostCSS with Tailwind v4
- `frontend/Dockerfile.dev` - Development Dockerfile for frontend
- `frontend/src/app/globals.css` - Tailwind import
- `frontend/src/app/layout.tsx` - Root layout with metadata
- `frontend/src/app/page.tsx` - Placeholder home page
- `frontend/public/.gitkeep` - Public assets placeholder
- `data/documents/.gitkeep` - Document storage placeholder
- `data/exports/.gitkeep` - Export storage placeholder
- `config/states/.gitkeep` - State config placeholder

## Files to Modify

- None (greenfield project)

## Contracts

### Provides (for downstream tasks)

- **Docker Compose service names**: `db`, `backend`, `worker`, `frontend`
- **Ports**: db=5432, backend=8000, frontend=3000
- **DATABASE_URL**: `postgresql+asyncpg://${POSTGRES_USER:-ogdocs}:${POSTGRES_PASSWORD:-ogdocs_dev}@db:5432/${POSTGRES_DB:-ogdocs}`
- **SYNC_DATABASE_URL**: `postgresql://${POSTGRES_USER:-ogdocs}:${POSTGRES_PASSWORD:-ogdocs_dev}@db:5432/${POSTGRES_DB:-ogdocs}`
- **DATA_DIR**: `/app/data` (container), `./data` (host)
- **DOCUMENTS_DIR**: `/data/documents` (container)
- **HUEY_DB_PATH**: `/app/data/huey.db`
- **Python package**: `og_scraper` importable from `backend/src/og_scraper/`
- **Backend source root**: `backend/src/`
- **Frontend source root**: `frontend/src/`
- **Init SQL**: PostGIS, uuid-ossp, pg_trgm extensions enabled on DB creation

### Consumes (from upstream tasks)

- Nothing (first task)

## Acceptance Criteria

- [ ] `uv sync` in the backend directory installs all Python dependencies without errors
- [ ] `cd frontend && npm install` installs all Node dependencies without errors
- [ ] `docker compose up db` starts PostgreSQL+PostGIS and passes its health check
- [ ] `docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT PostGIS_Version();"` returns a PostGIS version
- [ ] `docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT 'pg_trgm'::regextension;"` confirms pg_trgm is installed
- [ ] `just --list` shows all available dev commands
- [ ] Project directory structure matches the architecture skill layout
- [ ] `.env.example` contains all required environment variables with defaults
- [ ] `ruff.toml` is valid and `uv run ruff check backend/src/` produces no errors on the scaffolding code
- [ ] All `__init__.py` files exist in the correct locations
- [ ] Build succeeds: `docker compose build` completes without errors

## Testing Protocol

### Unit/Integration Tests

- No unit tests for this task (pure scaffolding). Verification is via CLI commands below.

### API/Script Testing

- `uv sync` in the `backend/` directory completes successfully
- `uv run python -c "import og_scraper; print(og_scraper.__version__)"` prints `0.1.0`
- `uv run python -c "import fastapi; print(fastapi.__version__)"` succeeds
- `uv run python -c "import sqlalchemy; print(sqlalchemy.__version__)"` succeeds
- `cd frontend && npm install && npx next --version` succeeds

### Docker Testing

- `docker compose config` validates the compose file without errors
- `docker compose up -d db` starts the database service
- `docker compose ps` shows db as healthy
- `docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT PostGIS_Version();"` returns a version string
- `docker compose exec db psql -U ogdocs -d ogdocs -c "SELECT 'pg_trgm'::regextension;"` succeeds
- `docker compose down` shuts everything down cleanly

### Build/Lint/Type Checks

- [ ] `docker compose build` succeeds for all services
- [ ] `cd backend && uv run ruff check src/` passes with no errors
- [ ] `cd frontend && npx tsc --noEmit` passes (after npm install)

## Skills to Read

- `og-scraper-architecture` - Project structure, folder layout, service architecture
- `docker-local-deployment` - Docker Compose config, environment variables, volumes, health checks

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/architecture-storage.md` - Monorepo structure (section 16), deployment (section 12)
- `.claude/orchestration-og-doc-scraper/research/backend-schema-implementation.md` - Docker Compose config (section 6)

## Git

- Branch: `task/1.1-project-scaffolding`
- Commit message prefix: `Task 1.1:`
