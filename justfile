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

# Run backend E2E tests (pipeline, API, error handling, performance)
test-e2e *args='':
    cd backend && uv run pytest tests/e2e/ -v {{args}}

# Run Playwright E2E tests (requires frontend + backend running)
test-e2e-dashboard:
    cd frontend && npx playwright test --reporter=html

# Run a specific Playwright test file
test-e2e-dashboard-file file:
    cd frontend && npx playwright test e2e/{{file}}

# View Playwright HTML report
test-e2e-report:
    cd frontend && npx playwright show-report

# Run Docker smoke test
smoke-test:
    bash scripts/docker-smoke-test.sh

# Run full test suite (unit + integration + e2e)
test-all:
    cd backend && uv run pytest -v
