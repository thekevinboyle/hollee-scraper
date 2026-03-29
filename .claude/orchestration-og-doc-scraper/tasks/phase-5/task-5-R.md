# Task 5.R: Phase 5 Regression

## Objective

Full end-to-end regression testing of the entire Phase 5 frontend dashboard. Verify that all pages work together as a coherent application, all API proxy calls succeed, all interactive features function correctly, and there are no console errors, broken layouts, or regressions between tasks. This task does not write new feature code -- it only tests, identifies issues, and fixes regressions.

## Context

Tasks 5.1 through 5.5 built the complete frontend dashboard: layout and navigation (5.1), search/browse with DataTable (5.2), interactive map with clustering (5.3), scrape trigger with SSE progress (5.4), and review queue with PDF viewer (5.5). This regression task verifies the complete integration. It must be run with the full backend stack running (FastAPI + PostgreSQL + Huey workers via Docker Compose) so that all API calls resolve and SSE streams work.

## Dependencies

- Task 5.1 - Frontend foundation (layout, API proxy, types)
- Task 5.2 - Search & browse interface (wells, documents)
- Task 5.3 - Interactive map (Leaflet, Supercluster)
- Task 5.4 - Scrape trigger & progress (SSE)
- Task 5.5 - Review queue & document viewer (react-pdf)
- All Phase 3 tasks (backend API) must be complete and running

## Blocked By

- 5.1, 5.2, 5.3, 5.4, 5.5

## Research Findings

Key findings from research files relevant to this task:

- From `nextjs-dashboard` skill: Common pitfalls to verify -- Leaflet CSS imported, default marker icons working, Supercluster client-side only, SSE bypassing Next.js proxy, react-pdf using dynamic import, coordinate format consistency.
- From `og-scraper-architecture` skill: All 17 API endpoints should be callable through the frontend proxy. SSE endpoints connect directly to FastAPI.
- From `confidence-scoring` skill: Confidence thresholds (0.85/0.50) should be reflected in the UI color coding.

## Implementation Plan

### Step 1: Verify Full Stack Is Running

Before running any tests, ensure the complete stack is up:

```bash
# Start all backend services
docker compose up -d

# Verify services are healthy
docker compose ps
# Expected: db, backend, worker, frontend all "running"

# Verify backend health
curl http://localhost:8000/api/v1/health
# Expected: { "status": "healthy" }

# Verify frontend
curl -s http://localhost:3000 | head -20
# Expected: HTML response
```

If no seed data exists, create minimal test data by running any available seeder script or manually inserting via the API:
- At least 10 wells across 3+ states with lat/long coordinates
- At least 20 documents with varying confidence scores
- At least 5 documents in the review queue (confidence < 0.85)
- At least 1 completed scrape job in history
- At least 1 PDF file accessible via the documents file endpoint

### Step 2: Cross-Page Navigation Test

Verify that all sidebar navigation links work and pages render correctly.

**Playwright MCP flow:**
1. Navigate to `http://localhost:3000`
2. Verify dashboard home page renders with stat cards
3. Click "Wells" in sidebar -> verify `/wells` page loads with DataTable
4. Click "Documents" in sidebar -> verify `/documents` page loads
5. Click "Map" in sidebar -> verify `/map` page loads with Leaflet tiles
6. Click "Scrape" in sidebar -> verify `/scrape` page loads with state grid
7. Click "Review Queue" in sidebar -> verify `/review` page loads with list
8. Click "Dashboard" in sidebar -> verify returns to home page
9. Verify no full page reloads (SPA navigation)
10. Verify no console errors on any page

### Step 3: Wells Search & Browse Regression

**Playwright MCP flow:**
1. Navigate to `http://localhost:3000/wells`
2. Verify table loads with well data (or empty state if no data)
3. Type a search query in the search bar
4. Wait for debounce, verify URL params update
5. Verify table results change based on search
6. Select a state from the filter dropdown
7. Verify table narrows to that state's wells
8. Click a table row
9. Verify detail side panel slides in on the right
10. Verify panel shows API number, operator, state, county, status, coordinates
11. Click Documents tab in panel
12. Verify associated documents listed
13. Close the panel
14. Verify table returns to full width
15. Click pagination next
16. Verify new page of data loads
17. Refresh the browser
18. Verify filters and page state are restored from URL params
19. Clear all filters
20. Verify table shows all wells again

**Check for regressions:**
- [ ] No layout shift when panel opens/closes
- [ ] Table loading state (skeleton) appears during fetch
- [ ] Empty state appears when filters match no results

### Step 4: Interactive Map Regression

**Playwright MCP flow:**
1. Navigate to `http://localhost:3000/map`
2. Verify map tiles load (CartoDB Positron background visible)
3. Verify well pins or clusters appear on the map
4. Zoom into a clustered area
5. Verify clusters break into individual pins or smaller clusters
6. Click an individual well pin
7. Verify popup appears with well name, API number, operator
8. Verify detail panel slides in on the right
9. Close the detail panel
10. Use the map filter controls to select a state
11. Verify only that state's wells are displayed
12. Clear the filter
13. Pan the map to a new area
14. Verify wells update for the new viewport
15. Zoom all the way out to US level
16. Verify clusters reform at low zoom

**Check for regressions:**
- [ ] No `window is not defined` errors (Leaflet SSR issue)
- [ ] No missing marker icons (broken bundler path issue)
- [ ] Map legend renders with correct status colors
- [ ] Map fills the full content area (no scrollbars)
- [ ] Filter panel floats correctly over the map (z-index)

### Step 5: Scrape Trigger & Progress Regression

**Playwright MCP flow:**
1. Navigate to `http://localhost:3000/scrape`
2. Verify state grid renders with all 10 states (TX, NM, ND, OK, CO, WY, LA, PA, CA, AK)
3. Verify each state card shows well count and last scrape date
4. If a scraper is available and testable (e.g., PA from Phase 4):
   a. Click "Scrape PA" button
   b. Verify button changes to "Running" with spinner
   c. Verify progress card appears below the grid
   d. Verify progress bar updates (may require waiting)
   e. Verify documents found/downloaded/processed counters update
   f. Verify elapsed time ticks
   g. Wait for completion (or cancel if taking too long)
   h. Verify completed job appears in history table
5. If no scraper available, verify:
   a. Clicking a scrape button sends the POST request (check network tab)
   b. Toast notification appears (success or error)
6. Scroll down to scrape history
7. Verify history table shows past jobs (if any)
8. Verify status badges render correctly (completed=green, failed=red)

**Check for regressions:**
- [ ] SSE connects directly to FastAPI (not through Next.js proxy)
- [ ] SSE connection cleans up on navigation away
- [ ] Multiple scrape progress cards can display simultaneously
- [ ] Toast notifications appear and auto-dismiss

### Step 6: Review Queue & Document Viewer Regression

**Playwright MCP flow:**
1. Navigate to `http://localhost:3000/review`
2. Verify review list loads on the left
3. If review items exist:
   a. Verify items show confidence badges with correct colors
   b. Click the first item
   c. Verify side-by-side layout: PDF left, fields right
   d. Verify PDF renders (not blank, not error state)
   e. Navigate PDF pages with prev/next buttons
   f. Zoom in/out with zoom controls
   g. Verify extracted fields render with confidence badges
   h. Verify low-confidence fields have colored backgrounds
   i. Edit a field value
   j. Verify field turns blue (edited indicator)
   k. Verify "Save Corrections & Approve" button appears
   l. Click approve/correct (test both flows if multiple items)
   m. Verify toast notification
   n. Verify item removed from list
   o. Test reject flow: click Reject, verify confirmation dialog, confirm
   p. Verify item removed from list
4. If no review items:
   a. Verify empty state message ("No items pending review" or similar)
5. Verify "Select an item to review" placeholder when no item selected

**Check for regressions:**
- [ ] No SSR errors from react-pdf (loaded via dynamic import)
- [ ] PDF.js worker loads correctly (no silent failures)
- [ ] Confidence color thresholds match: green >= 85%, yellow 50-84%, red < 50%
- [ ] Reject confirmation dialog blocks accidental rejections

### Step 7: Dark Mode Regression

**Playwright MCP flow:**
1. Navigate to dashboard
2. Click dark mode toggle in header
3. Verify entire app switches to dark theme
4. Navigate to each page and verify:
   - Wells table renders correctly in dark mode
   - Map uses appropriate dark-compatible tiles (or stays light)
   - Scrape cards and progress bars are visible
   - Review queue confidence colors are visible on dark background
   - PDF viewer is readable
5. Toggle back to light mode
6. Verify all pages return to light theme

### Step 8: API Proxy Verification

Verify that the Next.js rewrite proxy correctly forwards all API calls used by the frontend.

**Test each endpoint category:**
1. Wells: `GET /api/v1/wells` (via browser fetch)
2. Well detail: `GET /api/v1/wells/{api_number}` (via browser fetch)
3. Documents: `GET /api/v1/documents` (via browser fetch)
4. Document file: `GET /api/v1/documents/{id}/file` (via browser -- PDF should download/render)
5. Map wells: `GET /api/v1/map/wells?min_lat=...` (via browser fetch)
6. Scrape trigger: `POST /api/v1/scrape` (via browser fetch)
7. Scrape jobs: `GET /api/v1/scrape/jobs` (via browser fetch)
8. Review list: `GET /api/v1/review` (via browser fetch)
9. Review action: `PATCH /api/v1/review/{id}` (via browser fetch)
10. Stats: `GET /api/v1/stats` (via browser fetch)

For each, verify:
- Response returns valid JSON (or binary for file endpoint)
- No CORS errors
- No 502/504 proxy errors

### Step 9: Responsive Layout Check

Test at multiple viewport sizes:
1. Desktop (1920x1080) -- verify full sidebar + content layout
2. Laptop (1366x768) -- verify content fits without horizontal scroll
3. Tablet (768x1024) -- verify sidebar collapses, content remains usable
4. Narrow (480x800) -- verify critical content is accessible (even if degraded)

Verify on each:
- [ ] Sidebar collapses at narrow widths
- [ ] DataTables remain scrollable
- [ ] Map fills container
- [ ] Review side-by-side layout adapts (may stack on mobile)

### Step 10: Console Error Audit

Open browser DevTools on every page and check for:
- [ ] No JavaScript errors
- [ ] No React hydration mismatches
- [ ] No failed fetch requests (unless expected with no data)
- [ ] No missing resource warnings (CSS, images, workers)
- [ ] No deprecation warnings from libraries

### Step 11: Build Verification

```bash
cd frontend
npm run build
```

Verify:
- [ ] Build succeeds with no errors
- [ ] No TypeScript compilation errors
- [ ] No ESLint errors (if configured)
- [ ] Build output size is reasonable (check for unexpected large bundles)

### Step 12: Fix Identified Issues

For any regressions or issues found in Steps 2-11:
1. Document the issue (page, component, error message)
2. Identify the root cause
3. Fix the issue in the appropriate component file
4. Re-test the specific flow to confirm the fix
5. Run the full build again to ensure no new regressions

## Files to Create

- `frontend/e2e/phase-5-regression.spec.ts` - Playwright E2E test file covering all flows (optional, but recommended)
- No other new files expected -- this is a testing and fix task

## Files to Modify

- Any files where regressions are found (fixes only, no new features)

## Contracts

### Provides (for downstream tasks)

- **Verified frontend**: All Phase 5 features confirmed working end-to-end
- **Regression test spec**: Playwright test file covering critical user flows (if created)

### Consumes (from upstream tasks)

- All Phase 5 tasks (5.1-5.5): All frontend pages, components, hooks, and API integrations
- All Phase 3 tasks: Backend API endpoints running and accessible

## Acceptance Criteria

- [ ] All 6 sidebar navigation links work correctly
- [ ] Wells search/browse page: search, filter, paginate, detail panel all functional
- [ ] Documents page: table, filters, confidence display all functional
- [ ] Map page: tiles load, pins/clusters render, click-to-detail works, filters work
- [ ] Scrape page: state grid renders, scrape trigger works, SSE progress updates in real-time
- [ ] Review page: list loads, PDF renders, fields editable, approve/correct/reject all work
- [ ] Dark mode toggle works on all pages
- [ ] API proxy forwards all requests without CORS or buffering issues
- [ ] No console errors on any page
- [ ] `npm run build` succeeds
- [ ] Layout is usable at desktop and laptop viewport sizes

## Testing Protocol

### Browser Testing (Playwright MCP)

This entire task IS browser testing. The implementation plan above describes every flow to test.

- Start: `docker compose up -d` (full stack), then `cd frontend && npm run dev`
- Test all pages sequentially as described in Steps 2-9
- Screenshot key screens:
  1. Dashboard home page (light mode)
  2. Dashboard home page (dark mode)
  3. Wells page with data and side panel open
  4. Documents page with confidence bars
  5. Map page with clusters and a popup
  6. Map page with detail panel open
  7. Scrape page with state grid
  8. Scrape page with active progress bar
  9. Review page with PDF and fields side-by-side
  10. Review page with edited field (blue highlight)

### Build/Lint/Type Checks

- [ ] `npm run build` succeeds
- [ ] `npx tsc --noEmit` passes
- [ ] No TypeScript errors across all Phase 5 files

## Skills to Read

- `nextjs-dashboard` - All common pitfalls to verify (Leaflet CSS, marker icons, SSR, SSE proxy bypass, react-pdf worker)
- `og-scraper-architecture` - Full API endpoint list to verify proxy coverage
- `confidence-scoring` - Threshold values to verify in the UI
- `og-testing-strategies` - Playwright testing patterns for frontend E2E

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/dashboard-map-implementation.md` - Full reference for expected behavior across all dashboard features
- `.claude/orchestration-og-doc-scraper/research/testing-deployment-implementation.md` - E2E testing strategy and Playwright patterns

## Git

- Branch: `feat/5.R-phase5-regression`
- Commit message prefix: `Task 5.R:`
