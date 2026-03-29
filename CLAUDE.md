# Oil & Gas Document Scraper

Automated scraping, classification, and extraction of oil & gas regulatory documents from 10 US state websites. Replaces a full day of manual work.

## Quick Reference

| What | Where |
|------|-------|
| **Top authority** | `.claude/orchestration-og-doc-scraper/DISCOVERY.md` - all product/tech/scope decisions |
| **Implementation plan** | `.claude/orchestration-og-doc-scraper/PHASES.md` - 33 tasks across 7 phases |
| **Progress tracker** | `.claude/orchestration-og-doc-scraper/PROGRESS.md` - task status, phase status |
| **Task files** | `.claude/orchestration-og-doc-scraper/tasks/phase-N/task-N-M.md` - per-task specs |
| **Orchestrator** | `.claude/orchestration-og-doc-scraper/START.md` - how to run the system |
| **Research** | `.claude/orchestration-og-doc-scraper/research/` - 10 research files |

## Authority Rule

DISCOVERY.md overrides everything. If a research file, skill, or this document contradicts DISCOVERY.md, follow DISCOVERY.md. If still unsure, ask the human.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Scraping | Scrapy + scrapy-playwright |
| OCR | PaddleOCR v3 (free, local only) |
| PDF Text | PyMuPDF4LLM |
| Task Queue | Huey (SQLite backend, no Redis) |
| Database | PostgreSQL 16 + PostGIS 3.4 |
| ORM | SQLAlchemy 2.0 async + asyncpg |
| Migrations | Alembic |
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| UI | shadcn/ui |
| Map | Leaflet + react-leaflet + OpenStreetMap |
| Clustering | Supercluster via use-supercluster |
| Real-time | SSE via sse-starlette |
| Containers | Docker Compose (local only) |
| Package Mgmt | UV (Python), npm (Node) |
| Task Runner | just |
| Linting | ruff (Python), ESLint (JS/TS) |

## Scope Constraints (DO NOT implement)

No auth, no scheduled scraping, no paid OCR/LLM APIs, no cloud deployment, no mobile app, no ETL integration, no real-time streaming, no amendment tracking.

## Git Workflow

- Feature branches from `main`: `task/N-M-<short-description>`
- Merge to `main` after tests pass
- Commit prefix: `Task N.M: <description>`

## Testing

Every task requires:
1. Tests per task file testing protocol
2. Playwright MCP browser test (for UI tasks)
3. Backend log check — no errors

## Skills

Agents MUST read relevant skill files before starting a task. All at `.claude/skills/<name>/SKILL.md`:

| Skill | Use When |
|-------|----------|
| `og-scraper-architecture` | Project structure, folder layout, service connections |
| `scrapy-playwright-scraping` | Implementing scrapers, adding states |
| `document-processing-pipeline` | OCR, PDF extraction, classification, pipeline stages |
| `fastapi-backend` | API endpoints, database models, task queue |
| `postgresql-postgis-schema` | Database schema, queries, migrations |
| `nextjs-dashboard` | Frontend pages, map, UI components |
| `state-regulatory-sites` | State-specific scraper details, URLs, quirks |
| `confidence-scoring` | Data quality, thresholds, review queue |
| `og-testing-strategies` | Writing/running tests, VCR, testcontainers |
| `docker-local-deployment` | Docker Compose, containers, environment |

## MCP Servers

| Server | Purpose |
|--------|---------|
| Playwright | Browser E2E testing on localhost |
| context7 | Library documentation lookup |

## For Subagents

If you are a subagent spawned to execute a task:
1. Read your task file at `.claude/orchestration-og-doc-scraper/tasks/phase-N/task-N-M.md` first
2. Follow the Task Execution Protocol in `.claude/orchestration-og-doc-scraper/PHASES.md`
3. Read ALL skills listed in your task's Skills field
4. Check PROGRESS.md for current state before starting
5. Update PROGRESS.md when done
