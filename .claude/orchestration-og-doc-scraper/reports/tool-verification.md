# Tool Verification Report

**Date**: 2026-03-28
**Phase**: 5 (Tool Setup) + 6 (Verification)

---

## System-Level Tools

| Tool | Type | Status | Version | Test Performed | Notes |
|------|------|--------|---------|---------------|-------|
| Python | Runtime | PASS | 3.12.4 | `python3 --version` | System Python at /Library/Frameworks/Python.framework |
| Node.js | Runtime | PASS | 25.2.1 | `node --version` | - |
| npm | Package Mgr | PASS | 11.6.2 | `npm --version` | - |
| Git | VCS | PASS | 2.46.2 | `git --version` | Homebrew install |
| Homebrew | Package Mgr | PASS | 5.1.1 | `brew --version` | - |
| UV | Package Mgr | PASS | 0.11.2 | `uv --version` | Installed this session via brew |
| just | Task Runner | PASS | 1.48.1 | `just --version` | Installed this session via brew |
| ruff | Linter | PASS | 0.15.8 | `ruff --version` | Installed this session via brew |
| psql | DB Client | PASS | 14.17 | `psql --version` | Homebrew PostgreSQL client |
| Playwright | Browser Auto | PASS | 1.58.0 (py) / 1.58.2 (npx) | `npx playwright --version` | Python + Node bindings available |
| Docker Desktop | Container | PASS | 29.3.1 + Compose 5.1.0 | `docker --version` succeeded | Installed via brew cask |

## MCP Servers

| Server | Type | Status | Test Performed | Notes |
|--------|------|--------|---------------|-------|
| Playwright MCP | MCP | PASS | `claude mcp list` → Connected | @playwright/mcp@latest, installed this session |
| context7 | MCP | PASS | `claude mcp list` → Connected | Documentation lookup |
| figma | MCP | PASS | `claude mcp list` → Connected | Design integration |

## Pre-Installed Python Packages (Global)

| Package | Status | Version | Notes |
|---------|--------|---------|-------|
| Playwright (Python) | PASS | 1.58.0 | `pip3 list` confirmed |
| SQLAlchemy | PASS | 2.0.37 | `pip3 list` confirmed |

## Project Dependencies (To Be Installed During Phase 1 Implementation)

These are NOT installed globally — they'll be managed via `pyproject.toml` (UV) and `package.json` (npm) within the project:

### Python (via UV + pyproject.toml)
- Scrapy, scrapy-playwright
- FastAPI, uvicorn
- PaddleOCR (paddleocr, paddlepaddle)
- PyMuPDF4LLM (pymupdf4llm)
- Alembic
- Huey
- asyncpg, psycopg2-binary
- structlog
- sse-starlette
- python-multipart
- pydantic, pydantic-settings
- VCR.py (vcrpy)
- testcontainers
- pytest, pytest-asyncio, httpx

### Node.js (via npm + package.json)
- Next.js
- React, React DOM
- shadcn/ui (@shadcn/ui)
- Leaflet, react-leaflet
- use-supercluster, supercluster
- @tanstack/react-table
- react-pdf
- Tailwind CSS
- ESLint
- TypeScript

## Architecture

- **Platform**: macOS (Darwin 25.3.0)
- **Architecture**: arm64 (Apple Silicon)
- **Note for PaddleOCR**: Apple Silicon requires `paddlepaddle` (not GPU version). Research file confirms macOS ARM64 is supported.

---

## Blocking Issue

**Docker Desktop is NOT installed.** This is required for:
- PostgreSQL + PostGIS container
- Full Docker Compose dev stack (per DISCOVERY D6)
- Production-like local deployment

User must install Docker Desktop for Mac from https://www.docker.com/products/docker-desktop/

## Summary

- **10/11 system tools**: PASS
- **3/3 MCP servers**: PASS
- **1 blocking**: Docker Desktop (user action required)
