# Oil & Gas Document Scraper Orchestrator

When `/start` is invoked, this orchestrator manages sequential execution of all tasks across all phases. Designed for **fully autonomous execution**.

---

## Startup Sequence

1. **Read PROGRESS.md** at `.claude/orchestration-og-doc-scraper/PROGRESS.md` - Determine current state: which tasks are complete, which phase is active
2. **Read PHASES.md** at `.claude/orchestration-og-doc-scraper/PHASES.md` - Load the full implementation plan
3. **Identify next task** - Find the lowest-numbered pending task whose dependencies are all met
4. **Execute the task** - Spawn a subagent (see below)
5. **After task completes** - Verify PROGRESS.md was updated, then repeat from step 3

---

## Spawning a Subagent

For each task, spawn a `general-purpose` subagent via the Agent tool:

```
You are executing Task N.M for the Oil & Gas Document Scraper.

## Your Task File
Read your full task specification at: .claude/orchestration-og-doc-scraper/tasks/phase-N/task-N-M.md

## Execution Protocol

### Phase 0: Orient
- Read PROGRESS.md at .claude/orchestration-og-doc-scraper/PROGRESS.md to confirm this task is next
- Read your task file for full spec, acceptance criteria, files to create/modify
- Read ALL skill files listed in your task's "Skills to Read" field at .claude/skills/<name>/SKILL.md
- Read relevant research files listed in your task at .claude/orchestration-og-doc-scraper/research/

### Phase 1: Explore & Plan
- Explore existing codebase - understand what prior tasks built
- Read files you'll modify to understand current state
- Plan approach before writing code

### Phase 2: Implement
- Create feature branch: git checkout -b task/N-M-<short-description> main
- Write code following existing patterns and contracts from your task file
- Write tests as specified in your task's Testing Protocol

### Phase 3: Test Locally
- Run all testing methods specified in your task file
- Unit tests: uv run pytest backend/tests/ (for Python tasks)
- Integration tests: uv run pytest -m integration (requires Docker)
- API tests: uv run pytest backend/tests/api/
- Browser tests: Use Playwright MCP to test UI flows on localhost
- Lint: ruff check backend/ && ruff format --check backend/
- Iterate until all tests pass

### Phase 4: Complete
- Update PROGRESS.md with status="done", branch name, date, and notes
- Git add, commit with message "Task N.M: <title>"
- Merge to main branch
```

---

## Regression Tasks

Regression tasks use a different prompt:

```
This is a REGRESSION task for Phase N of the Oil & Gas Document Scraper.

Read your task file at: .claude/orchestration-og-doc-scraper/tasks/phase-N/task-N-R.md

1. Ensure Docker Compose is running: docker compose up -d
2. Wait for all services to be healthy
3. Run ALL tests from this phase on the running stack
4. Test every feature built in this phase AND all prior phases
5. Run full test suite: just test
6. For UI phases: full Playwright browser testing via Playwright MCP
7. Screenshot key screens as evidence
8. Update PROGRESS.md with regression results (detailed pass/fail per check)
9. If regression fails: fix the issue, redeploy, retest until green
10. Merge phase branch to main
```

---

## Final Phase Tasks (Phase 7)

The final phase tests on the fully deployed local software:

```
This is a FINAL E2E task testing the fully deployed Oil & Gas Document Scraper.

Read your task file at: .claude/orchestration-og-doc-scraper/tasks/phase-7/task-7-M.md

1. Verify Docker Compose stack is current and all services healthy
2. Test every user path and edge case as specified in your task file
3. Apply all testing methods (unit, integration, API, browser, Docker smoke)
4. Performance and error handling validation
5. Iterate directly on main branch — fix issues, retest
6. Update PROGRESS.md with comprehensive results
```

---

## Orchestrator Rules

### Execution Order
- Execute ONE task at a time (sequential, not parallel)
- Follow task numbering within each phase (1.1 → 1.2 → 1.3 → 1.4 → 1.R)
- Complete all tasks in a phase before moving to the next
- Regression task is always the last task in each phase

### Dependency Checking
- Before spawning, verify all dependency tasks are marked `done` in PROGRESS.md
- Check the "Blocked by" field in each task file
- Tasks within a phase are generally sequential (1.1 before 1.2)
- Some tasks across phases can overlap if dependencies are met (e.g., 2.1 only needs 1.1)

### Failure Handling (3-Tier Escalation)

**Tier 1: Subagent Self-Recovery** (automatic)
- Debug and fix within its own session
- Retry failed tool calls with different parameters
- Create missing dependencies inline

**Tier 2: Orchestrator Intervention** (if subagent reports failure)
- Read error output and PROGRESS.md notes
- Spawn a targeted fix subagent
- Re-run original task after fix

**Tier 3: User Escalation** (last resort)
- Provide: task number, what was attempted, the error, suggested fix
- Continue with next unblocked task while waiting

### Phase Transitions
- After regression task passes, update Phase Overview status to `done` in PROGRESS.md
- Announce phase completion before starting next phase

### Session Boundaries
- If context is getting large, report progress and suggest compacting or starting fresh
- PROGRESS.md enables session continuity — nothing is lost between sessions

---

## Available Tools

| Tool | Purpose |
|------|---------|
| **Playwright MCP** | Browser E2E testing on localhost:3000 |
| **context7 MCP** | Library documentation lookup |
| **Bash** | Shell commands, Docker, git, pytest, etc. |
| **Read/Write/Edit** | File operations |
| **Glob/Grep** | Code search |

---

## File Locations

| File | Path | Purpose |
|------|------|---------|
| Master plan | `.claude/orchestration-og-doc-scraper/PHASES.md` | All tasks, skills, testing methods |
| Orchestrator | `.claude/orchestration-og-doc-scraper/START.md` | This file |
| Discovery | `.claude/orchestration-og-doc-scraper/DISCOVERY.md` | Top authority for all decisions |
| PRD | `.claude/orchestration-og-doc-scraper/PRD.md` | Original product requirements |
| Research | `.claude/orchestration-og-doc-scraper/research/` | 10 research files |
| Task files | `.claude/orchestration-og-doc-scraper/tasks/phase-N/task-N-M.md` | Per-task specs |
| Progress | `.claude/orchestration-og-doc-scraper/PROGRESS.md` | Task status tracker |
| Skills | `.claude/skills/` | 10 project skills |
| Reports | `.claude/orchestration-og-doc-scraper/reports/` | Tool verification, synergy review |

---

## Key Reminders

- **DISCOVERY.md is top authority** — if anything contradicts it, follow DISCOVERY.md
- **No paid APIs** — PaddleOCR only, no cloud OCR/LLM services
- **No auth** — internal tool, no user authentication
- **Local only** — Docker Compose on local machine, no cloud deployment
- **On-demand scraping** — user triggers from dashboard, no scheduled runs
- **Strict quality** — reject uncertain data, review queue for medium confidence
