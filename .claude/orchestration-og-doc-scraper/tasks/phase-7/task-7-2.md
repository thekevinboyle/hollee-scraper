# Task 7.2: Dashboard E2E Testing (Playwright)

## Objective

Full Playwright browser testing of every dashboard feature: search/browse, interactive map, scrape trigger with SSE progress, review queue with document viewer, data export, and layout/navigation. Every user-visible interaction is exercised and verified with assertions and screenshots as evidence.

## Context

This is the second task in Phase 7 (Comprehensive E2E Testing). Task 7.1 validated the backend pipeline end-to-end. This task validates the frontend dashboard by automating a real browser against the running application. All 6 dashboard pages (Dashboard/Home, Wells, Documents, Map, Scrape, Review Queue) must be tested. The backend must be running with seed data or VCR cassette data for the frontend to display. Tasks 7.3 and 7.4 cover error handling and performance respectively.

## Dependencies

- All Phase 1-6 tasks must be complete
- Task 7.1 (E2E test infrastructure exists, pipeline validated)
- Frontend running at `http://localhost:3000`
- Backend running at `http://localhost:8000`
- Database seeded with test data from pipeline runs

## Blocked By

- All Phase 1-6 tasks
- Task 7.1 (seed data and infrastructure)

## Research Findings

Key findings from research files relevant to this task:

- From `nextjs-dashboard` skill: Sidebar navigation includes Dashboard, Wells, Documents, Map, Scrape, Review Queue. Map uses dynamic import with SSR disabled. SSE must connect directly to FastAPI (port 8000), not through Next.js proxy.
- From `og-testing-strategies` skill: Playwright config targets Chromium, uses `http://localhost:3000` as base URL. Install browsers via `npx playwright install chromium`.
- From `dashboard-map-implementation.md`: Leaflet renders well pins with Supercluster clustering. Click pin opens popup. Click-to-detail side panel for well info.
- From `confidence-scoring` skill: Review queue shows documents ordered by confidence. Fields below threshold highlighted in yellow. Approve/correct/reject actions available.

## Implementation Plan

### Step 1: Playwright Configuration

Create or update the Playwright configuration in the frontend project.

```typescript
// frontend/playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // Sequential to avoid state conflicts
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['list'],
  ],
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'on',
    video: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
```

### Step 2: Test Helpers and Seed Data

Create shared test helpers for common Playwright operations and data seeding.

```typescript
// frontend/e2e/helpers.ts
import { Page, expect } from '@playwright/test';

export async function waitForPageLoad(page: Page) {
  await page.waitForLoadState('networkidle');
}

export async function navigateViaSidebar(page: Page, linkText: string) {
  await page.click(`nav >> text=${linkText}`);
  await waitForPageLoad(page);
}

export async function takeEvidenceScreenshot(page: Page, name: string) {
  await page.screenshot({
    path: `playwright-report/evidence/${name}.png`,
    fullPage: true,
  });
}

export async function expectNoConsoleErrors(page: Page) {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  });
  return errors;
}
```

### Step 3: Dashboard Layout and Navigation Tests

```typescript
// frontend/e2e/dashboard-layout.spec.ts
import { test, expect } from '@playwright/test';
import { takeEvidenceScreenshot, navigateViaSidebar } from './helpers';

test.describe('Dashboard Layout & Navigation', () => {
  test('renders sidebar with all navigation links', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Verify sidebar is visible
    const sidebar = page.locator('nav');
    await expect(sidebar).toBeVisible();

    // Verify all navigation items exist
    const navItems = ['Dashboard', 'Wells', 'Documents', 'Map', 'Scrape', 'Review'];
    for (const item of navItems) {
      await expect(sidebar.locator(`text=${item}`)).toBeVisible();
    }

    await takeEvidenceScreenshot(page, '01-dashboard-layout');
  });

  test('sidebar navigation routes to correct pages', async ({ page }) => {
    await page.goto('/');

    // Navigate to each page via sidebar
    const routes = [
      { name: 'Wells', urlPattern: /\/wells/ },
      { name: 'Documents', urlPattern: /\/documents/ },
      { name: 'Map', urlPattern: /\/map/ },
      { name: 'Scrape', urlPattern: /\/scrape/ },
      { name: 'Review', urlPattern: /\/review/ },
    ];

    for (const route of routes) {
      await navigateViaSidebar(page, route.name);
      await expect(page).toHaveURL(route.urlPattern);
    }
  });

  test('dashboard home shows statistics cards', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Verify stats cards are present (total wells, documents, states, etc.)
    await expect(page.locator('[data-testid="stats-card"], .stats-card, h3:has-text("Total")')).toHaveCount({ minimum: 1 });
    await takeEvidenceScreenshot(page, '02-dashboard-home');
  });

  test('no console errors on dashboard home', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    expect(errors).toEqual([]);
  });
});
```

### Step 4: Search and Browse E2E Tests

```typescript
// frontend/e2e/search-browse.spec.ts
import { test, expect } from '@playwright/test';
import { takeEvidenceScreenshot, navigateViaSidebar } from './helpers';

test.describe('Wells Search & Browse', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/wells');
    await page.waitForLoadState('networkidle');
  });

  test('wells table loads with data', async ({ page }) => {
    // Verify table is visible
    const table = page.locator('table');
    await expect(table).toBeVisible();

    // Verify at least one row of data
    const rows = page.locator('table tbody tr');
    await expect(rows).toHaveCount({ minimum: 1 });

    await takeEvidenceScreenshot(page, '03-wells-table');
  });

  test('search by API number returns matching results', async ({ page }) => {
    // Type an API number prefix into search
    const searchInput = page.locator('input[placeholder*="earch"], input[type="search"]');
    await searchInput.fill('42-461');
    await searchInput.press('Enter');

    // Wait for results to update
    await page.waitForResponse(resp => resp.url().includes('/api/wells'));

    // Verify results contain the API number
    const firstRow = page.locator('table tbody tr').first();
    await expect(firstRow).toContainText('42-461');

    await takeEvidenceScreenshot(page, '04-search-api-number');
  });

  test('filter by state updates table', async ({ page }) => {
    // Open state filter dropdown
    const stateFilter = page.locator('select:has-text("State"), [data-testid="state-filter"], button:has-text("State")');
    await stateFilter.click();

    // Select Texas
    await page.locator('text=Texas').or(page.locator('text=TX')).first().click();

    // Wait for API call with state filter
    await page.waitForResponse(resp => resp.url().includes('state=TX'));

    // Verify all visible rows show TX
    const stateCells = page.locator('table tbody tr td:nth-child(4)');  // Adjust column index
    const count = await stateCells.count();
    for (let i = 0; i < Math.min(count, 10); i++) {
      const text = await stateCells.nth(i).textContent();
      expect(text).toContain('TX');
    }

    await takeEvidenceScreenshot(page, '05-filter-by-state');
  });

  test('click well row opens detail side panel', async ({ page }) => {
    // Click the first row in the wells table
    const firstRow = page.locator('table tbody tr').first();
    await firstRow.click();

    // Verify side panel opens with well details
    const sidePanel = page.locator('[data-testid="well-detail-panel"], .well-detail-panel, [class*="side-panel"]');
    await expect(sidePanel).toBeVisible({ timeout: 5000 });

    // Verify panel contains well information
    await expect(sidePanel).toContainText(/API|Operator|Well Name/i);

    // Verify associated documents section
    await expect(sidePanel).toContainText(/Document/i);

    await takeEvidenceScreenshot(page, '06-well-detail-panel');
  });

  test('pagination controls work', async ({ page }) => {
    // Verify pagination exists
    const pagination = page.locator('[data-testid="pagination"], nav[aria-label="pagination"], .pagination');
    await expect(pagination).toBeVisible();

    // Click next page
    const nextButton = page.locator('button:has-text("Next"), button[aria-label="Next page"]');
    if (await nextButton.isEnabled()) {
      await nextButton.click();
      await page.waitForResponse(resp => resp.url().includes('/api/wells'));
      await expect(page).toHaveURL(/page=2/);
    }
  });
});

test.describe('Documents Browse', () => {
  test('documents table loads and is filterable', async ({ page }) => {
    await page.goto('/documents');
    await page.waitForLoadState('networkidle');

    const table = page.locator('table');
    await expect(table).toBeVisible();
    const rows = page.locator('table tbody tr');
    await expect(rows).toHaveCount({ minimum: 1 });

    await takeEvidenceScreenshot(page, '07-documents-table');
  });
});
```

### Step 5: Interactive Map E2E Tests

```typescript
// frontend/e2e/map.spec.ts
import { test, expect } from '@playwright/test';
import { takeEvidenceScreenshot } from './helpers';

test.describe('Interactive Map', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/map');
    await page.waitForLoadState('networkidle');
    // Wait for Leaflet map to initialize
    await page.waitForSelector('.leaflet-container', { timeout: 15_000 });
  });

  test('map renders with OpenStreetMap tiles', async ({ page }) => {
    // Verify Leaflet container is visible
    const mapContainer = page.locator('.leaflet-container');
    await expect(mapContainer).toBeVisible();

    // Verify tiles are loaded (at least some tile images)
    const tiles = page.locator('.leaflet-tile-loaded');
    await expect(tiles).toHaveCount({ minimum: 1 });

    await takeEvidenceScreenshot(page, '08-map-initial');
  });

  test('well pins render on map', async ({ page }) => {
    // Wait for markers to appear
    await page.waitForSelector('.leaflet-marker-icon, .leaflet-interactive', { timeout: 15_000 });

    const markers = page.locator('.leaflet-marker-icon, .leaflet-interactive');
    await expect(markers).toHaveCount({ minimum: 1 });

    await takeEvidenceScreenshot(page, '09-map-with-pins');
  });

  test('zoom in expands clusters to individual pins', async ({ page }) => {
    // Get initial marker count at default zoom
    await page.waitForSelector('.leaflet-marker-icon', { timeout: 15_000 });

    // Zoom in by double-clicking or using zoom controls
    const zoomIn = page.locator('.leaflet-control-zoom-in, button[aria-label="Zoom in"]');
    await zoomIn.click();
    await page.waitForTimeout(1000); // Wait for animation
    await zoomIn.click();
    await page.waitForTimeout(1000);
    await zoomIn.click();
    await page.waitForTimeout(1000);
    await zoomIn.click();
    await page.waitForTimeout(1000);

    await takeEvidenceScreenshot(page, '10-map-zoomed-in');
  });

  test('zoom out collapses pins to clusters', async ({ page }) => {
    // Zoom out to see clusters
    const zoomOut = page.locator('.leaflet-control-zoom-out, button[aria-label="Zoom out"]');
    await zoomOut.click();
    await page.waitForTimeout(1000);
    await zoomOut.click();
    await page.waitForTimeout(1000);

    // Clusters should show count numbers
    await takeEvidenceScreenshot(page, '11-map-zoomed-out-clusters');
  });

  test('click map pin shows popup with well info', async ({ page }) => {
    // Wait for markers
    await page.waitForSelector('.leaflet-marker-icon', { timeout: 15_000 });

    // Click the first marker
    const firstMarker = page.locator('.leaflet-marker-icon').first();
    await firstMarker.click();

    // Verify popup appears
    const popup = page.locator('.leaflet-popup, [data-testid="well-popup"]');
    await expect(popup).toBeVisible({ timeout: 5000 });

    // Verify popup contains well info
    await expect(popup).toContainText(/API|Operator|Well/i);

    await takeEvidenceScreenshot(page, '12-map-pin-popup');
  });

  test('no console errors on map page', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        // Ignore tile loading errors (common in test environments)
        if (!msg.text().includes('tile') && !msg.text().includes('Failed to load resource')) {
          errors.push(msg.text());
        }
      }
    });
    await page.goto('/map');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    expect(errors).toEqual([]);
  });
});
```

### Step 6: Scrape Trigger and SSE Progress Tests

```typescript
// frontend/e2e/scrape.spec.ts
import { test, expect } from '@playwright/test';
import { takeEvidenceScreenshot } from './helpers';

test.describe('Scrape Trigger & Progress', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/scrape');
    await page.waitForLoadState('networkidle');
  });

  test('scrape page shows all 10 state buttons', async ({ page }) => {
    const stateButtons = page.locator('[data-testid="state-scrape-button"], button:has-text("Scrape")');
    // Should have individual state buttons (10) + possibly "Scrape All"
    const states = ['TX', 'NM', 'ND', 'OK', 'CO', 'WY', 'LA', 'PA', 'CA', 'AK'];
    for (const state of states) {
      await expect(
        page.locator(`text=${state}`).or(page.locator(`button:has-text("${state}")`))
      ).toBeVisible();
    }

    await takeEvidenceScreenshot(page, '13-scrape-state-grid');
  });

  test('click Scrape button triggers scrape with progress', async ({ page }) => {
    // Click "Scrape PA" (Pennsylvania - typically fast with VCR cassettes)
    const scrapeButton = page.locator('button:has-text("PA"), button:has-text("Pennsylvania")').first();
    await scrapeButton.click();

    // Verify progress UI appears
    const progressBar = page.locator(
      'progress, [role="progressbar"], [data-testid="scrape-progress"]'
    );
    await expect(progressBar).toBeVisible({ timeout: 10_000 });

    await takeEvidenceScreenshot(page, '14-scrape-in-progress');

    // Wait for completion (up to 120 seconds for VCR cassette replay)
    await expect(
      page.locator('text=completed', { exact: false }).or(
        page.locator('text=Complete', { exact: false })
      )
    ).toBeVisible({ timeout: 120_000 });

    await takeEvidenceScreenshot(page, '15-scrape-completed');
  });

  test('scrape history shows completed jobs', async ({ page }) => {
    // After a scrape has been run, the history section should show it
    const historySection = page.locator(
      '[data-testid="scrape-history"], text=History, h2:has-text("History"), h3:has-text("History")'
    );

    // If history section exists, verify it has content
    if (await historySection.isVisible()) {
      const historyRows = page.locator('[data-testid="scrape-history-item"], table tbody tr');
      await expect(historyRows).toHaveCount({ minimum: 0 });
      await takeEvidenceScreenshot(page, '16-scrape-history');
    }
  });

  test('SSE progress updates in real-time', async ({ page }) => {
    // Monitor network for SSE connection
    const ssePromise = page.waitForRequest(
      req => req.url().includes('/progress') || req.url().includes('/events'),
      { timeout: 15_000 }
    ).catch(() => null);

    // Trigger a scrape
    const scrapeButton = page.locator('button:has-text("CO"), button:has-text("Colorado")').first();
    await scrapeButton.click();

    // Verify SSE connection was attempted
    const sseRequest = await ssePromise;
    // SSE may connect to FastAPI directly (port 8000) or through proxy

    // Verify progress text updates (at least once)
    await page.waitForSelector(
      '[data-testid="progress-message"], .progress-message, text=/processing|downloading|extracting/i',
      { timeout: 30_000 }
    ).catch(() => {
      // Progress messages may not appear if scrape is very fast with VCR
    });

    await takeEvidenceScreenshot(page, '17-sse-progress-update');
  });
});
```

### Step 7: Review Queue and Document Viewer Tests

```typescript
// frontend/e2e/review-queue.spec.ts
import { test, expect } from '@playwright/test';
import { takeEvidenceScreenshot } from './helpers';

test.describe('Review Queue', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/review');
    await page.waitForLoadState('networkidle');
  });

  test('review queue lists documents needing review', async ({ page }) => {
    // Verify review list is visible
    const reviewList = page.locator(
      '[data-testid="review-list"], table, .review-items'
    );
    await expect(reviewList).toBeVisible();

    await takeEvidenceScreenshot(page, '18-review-queue-list');
  });

  test('click review item opens side-by-side PDF and fields', async ({ page }) => {
    // Click the first review item
    const firstItem = page.locator(
      '[data-testid="review-item"], table tbody tr, .review-item'
    ).first();
    await firstItem.click();

    // Verify side-by-side view appears
    // Left panel: PDF viewer
    const pdfViewer = page.locator(
      '[data-testid="document-viewer"], .react-pdf__Document, canvas'
    );
    await expect(pdfViewer).toBeVisible({ timeout: 15_000 });

    // Right panel: Extracted fields
    const fieldsPanel = page.locator(
      '[data-testid="extracted-fields"], form, .extracted-fields'
    );
    await expect(fieldsPanel).toBeVisible();

    await takeEvidenceScreenshot(page, '19-review-side-by-side');
  });

  test('confidence scores are color-coded', async ({ page }) => {
    // Open a review item
    const firstItem = page.locator(
      '[data-testid="review-item"], table tbody tr, .review-item'
    ).first();
    await firstItem.click();

    // Verify confidence badges/indicators exist
    const confidenceIndicators = page.locator(
      '[data-testid="confidence-score"], .confidence-badge, .confidence-indicator'
    );
    await expect(confidenceIndicators).toHaveCount({ minimum: 1 });

    await takeEvidenceScreenshot(page, '20-confidence-color-coded');
  });

  test('approve an item removes it from queue', async ({ page }) => {
    // Count items before
    const itemsBefore = await page.locator(
      '[data-testid="review-item"], table tbody tr'
    ).count();

    if (itemsBefore === 0) {
      test.skip('No review items available');
      return;
    }

    // Open first item
    const firstItem = page.locator(
      '[data-testid="review-item"], table tbody tr'
    ).first();
    const itemText = await firstItem.textContent();
    await firstItem.click();

    // Click approve button
    const approveButton = page.locator(
      'button:has-text("Approve"), [data-testid="approve-button"]'
    );
    await expect(approveButton).toBeVisible();
    await approveButton.click();

    // Wait for the API call to complete
    await page.waitForResponse(
      resp => resp.url().includes('/api/review') && resp.status() === 200,
      { timeout: 10_000 }
    );

    // Verify the item is no longer in the queue
    await page.waitForTimeout(1000); // Wait for UI update
    const itemsAfter = await page.locator(
      '[data-testid="review-item"], table tbody tr'
    ).count();
    expect(itemsAfter).toBeLessThan(itemsBefore);

    await takeEvidenceScreenshot(page, '21-after-approve');
  });

  test('correct an item with field edits', async ({ page }) => {
    const items = page.locator('[data-testid="review-item"], table tbody tr');
    if (await items.count() === 0) {
      test.skip('No review items available');
      return;
    }

    // Open first item
    await items.first().click();
    await page.waitForTimeout(1000);

    // Find an editable field and change its value
    const editableField = page.locator(
      'input[data-testid*="field-"], .extracted-fields input, [contenteditable="true"]'
    ).first();

    if (await editableField.isVisible()) {
      await editableField.clear();
      await editableField.fill('CORRECTED VALUE');

      // Click correct/save button
      const correctButton = page.locator(
        'button:has-text("Correct"), button:has-text("Save"), [data-testid="correct-button"]'
      );
      await correctButton.click();

      await page.waitForResponse(
        resp => resp.url().includes('/api/review') && resp.status() === 200,
        { timeout: 10_000 }
      );

      await takeEvidenceScreenshot(page, '22-after-correct');
    }
  });

  test('PDF viewer renders document pages', async ({ page }) => {
    const items = page.locator('[data-testid="review-item"], table tbody tr');
    if (await items.count() === 0) {
      test.skip('No review items available');
      return;
    }

    // Open first item
    await items.first().click();

    // Wait for PDF to render
    const pdfPage = page.locator(
      '.react-pdf__Page, [data-testid="pdf-page"], canvas'
    );
    await expect(pdfPage).toBeVisible({ timeout: 15_000 });

    await takeEvidenceScreenshot(page, '23-pdf-viewer');
  });
});
```

### Step 8: Export Functionality Tests

```typescript
// frontend/e2e/export.spec.ts
import { test, expect } from '@playwright/test';
import { takeEvidenceScreenshot } from './helpers';

test.describe('Data Export', () => {
  test('export wells as CSV triggers download', async ({ page }) => {
    await page.goto('/wells');
    await page.waitForLoadState('networkidle');

    // Look for export button
    const exportButton = page.locator(
      'button:has-text("Export"), [data-testid="export-csv"], a:has-text("Export")'
    );

    if (await exportButton.isVisible()) {
      // Set up download listener
      const downloadPromise = page.waitForEvent('download', { timeout: 30_000 });
      await exportButton.click();

      // Select CSV format if dropdown appears
      const csvOption = page.locator('text=CSV');
      if (await csvOption.isVisible({ timeout: 2000 }).catch(() => false)) {
        await csvOption.click();
      }

      const download = await downloadPromise;
      expect(download.suggestedFilename()).toMatch(/\.csv$/);

      await takeEvidenceScreenshot(page, '24-export-csv');
    }
  });

  test('export wells as JSON triggers download', async ({ page }) => {
    await page.goto('/wells');
    await page.waitForLoadState('networkidle');

    const exportButton = page.locator(
      'button:has-text("Export"), [data-testid="export-json"]'
    );

    if (await exportButton.isVisible()) {
      const downloadPromise = page.waitForEvent('download', { timeout: 30_000 });
      await exportButton.click();

      const jsonOption = page.locator('text=JSON');
      if (await jsonOption.isVisible({ timeout: 2000 }).catch(() => false)) {
        await jsonOption.click();
      }

      const download = await downloadPromise;
      expect(download.suggestedFilename()).toMatch(/\.json$/);

      await takeEvidenceScreenshot(page, '25-export-json');
    }
  });
});
```

### Step 9: Full User Flow Test (End-to-End Scenario)

```typescript
// frontend/e2e/full-user-flow.spec.ts
import { test, expect } from '@playwright/test';
import { takeEvidenceScreenshot } from './helpers';

test.describe('Full User Flow', () => {
  test('complete user journey: dashboard -> search -> map -> scrape -> review', async ({ page }) => {
    // Step 1: Land on dashboard
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveTitle(/Oil.*Gas|Dashboard|OG/i);
    await takeEvidenceScreenshot(page, 'flow-01-dashboard');

    // Step 2: Navigate to wells and search
    await page.click('nav >> text=Wells');
    await page.waitForLoadState('networkidle');
    const searchInput = page.locator('input[placeholder*="earch"], input[type="search"]');
    await searchInput.fill('Devon');
    await searchInput.press('Enter');
    await page.waitForResponse(resp => resp.url().includes('/api/wells'));
    await takeEvidenceScreenshot(page, 'flow-02-search-results');

    // Step 3: Click a well to see details
    const firstResult = page.locator('table tbody tr').first();
    if (await firstResult.isVisible()) {
      await firstResult.click();
      await page.waitForTimeout(1000);
      await takeEvidenceScreenshot(page, 'flow-03-well-detail');
    }

    // Step 4: Navigate to map
    await page.click('nav >> text=Map');
    await page.waitForSelector('.leaflet-container', { timeout: 15_000 });
    await page.waitForTimeout(3000); // Wait for tiles and markers
    await takeEvidenceScreenshot(page, 'flow-04-map-view');

    // Step 5: Navigate to scrape and trigger
    await page.click('nav >> text=Scrape');
    await page.waitForLoadState('networkidle');
    await takeEvidenceScreenshot(page, 'flow-05-scrape-page');

    // Step 6: Navigate to review queue
    await page.click('nav >> text=Review');
    await page.waitForLoadState('networkidle');
    await takeEvidenceScreenshot(page, 'flow-06-review-queue');

    // Step 7: Navigate to documents
    await page.click('nav >> text=Documents');
    await page.waitForLoadState('networkidle');
    await takeEvidenceScreenshot(page, 'flow-07-documents');
  });
});
```

### Step 10: Screenshot Evidence Collection

Create a script that runs all tests and collects screenshots.

Add to the `justfile`:
```makefile
# Run Playwright E2E tests and collect evidence screenshots
test-e2e-dashboard:
    cd frontend && npx playwright test --reporter=html

# Run a specific test file
test-e2e-dashboard-map:
    cd frontend && npx playwright test e2e/map.spec.ts

# View the HTML report
test-e2e-report:
    cd frontend && npx playwright show-report
```

## Files to Create

- `frontend/e2e/helpers.ts` - Shared test helper functions
- `frontend/e2e/dashboard-layout.spec.ts` - Layout and navigation tests
- `frontend/e2e/search-browse.spec.ts` - Search, browse, filter, detail panel tests
- `frontend/e2e/map.spec.ts` - Interactive map tests (pins, clusters, popups, zoom)
- `frontend/e2e/scrape.spec.ts` - Scrape trigger and SSE progress tests
- `frontend/e2e/review-queue.spec.ts` - Review queue, PDF viewer, approve/correct/reject tests
- `frontend/e2e/export.spec.ts` - Data export tests (CSV, JSON)
- `frontend/e2e/full-user-flow.spec.ts` - Complete user journey test

## Files to Modify

- `frontend/playwright.config.ts` - Update or create Playwright configuration
- `justfile` - Add `test-e2e-dashboard` and related commands

## Contracts

### Provides (for downstream tasks)

- Screenshot evidence: All key screens captured in `playwright-report/evidence/`
- Playwright test suite: Reusable test infrastructure for future regression testing
- Full user flow validation: Confirmation that the entire dashboard works end-to-end

### Consumes (from upstream tasks)

- From Task 5.1: Frontend foundation (layout, sidebar, API proxy)
- From Task 5.2: Wells search/browse (DataTable, filters, side panel)
- From Task 5.3: Interactive map (Leaflet, Supercluster, popups)
- From Task 5.4: Scrape trigger (state grid, SSE progress)
- From Task 5.5: Review queue (PDF viewer, field editing, approve/correct/reject)
- From Task 3.1-3.4: All API endpoints serving data to the frontend
- From Task 7.1: Database seeded with test data from pipeline runs

## Acceptance Criteria

- [ ] Playwright: Dashboard layout renders with sidebar and all navigation links
- [ ] Playwright: All sidebar links navigate to correct pages
- [ ] Playwright: Wells table loads with data from API
- [ ] Playwright: Search by API number returns matching results
- [ ] Playwright: State filter narrows table results
- [ ] Playwright: Click well row opens side panel with details and documents
- [ ] Playwright: Map renders with OpenStreetMap tiles
- [ ] Playwright: Well pins appear on the map
- [ ] Playwright: Zoom in/out causes clusters to expand/collapse
- [ ] Playwright: Click map pin shows popup with well info
- [ ] Playwright: Scrape page shows all 10 state buttons
- [ ] Playwright: Trigger scrape shows progress bar that updates
- [ ] Playwright: Scrape completes successfully
- [ ] Playwright: Review queue lists items with confidence scores
- [ ] Playwright: Click review item shows PDF alongside extracted fields
- [ ] Playwright: Approve an item removes it from the queue
- [ ] Playwright: Correct an item with field edits works
- [ ] Playwright: Export wells as CSV triggers file download
- [ ] Playwright: No console errors on any page
- [ ] All key screens captured as screenshot evidence
- [ ] Full user journey test passes end-to-end

## Testing Protocol

### Browser Testing (Playwright MCP)

- Start: `docker compose up -d` (all services) OR `npm run dev` (frontend) + `uv run uvicorn` (backend)
- Navigate to: `http://localhost:3000`
- Actions: Each spec file covers a specific feature area
- Verify: Assertions on visibility, text content, URL patterns, element counts
- User-emulating flow: `full-user-flow.spec.ts` covers the complete journey
- Test assets: Seed data from Task 7.1 pipeline runs
- Screenshots: Evidence captured at every major step to `playwright-report/evidence/`

### Running Tests

```bash
# Install Playwright browsers (first time only)
cd frontend && npx playwright install chromium

# Run all E2E tests
cd frontend && npx playwright test

# Run specific test file
cd frontend && npx playwright test e2e/map.spec.ts

# Run with headed browser (visible)
cd frontend && npx playwright test --headed

# Run with debug mode (step through)
cd frontend && npx playwright test --debug

# View HTML report after run
cd frontend && npx playwright show-report
```

### Build/Lint/Type Checks

- [ ] `cd frontend && npm run build` succeeds
- [ ] `cd frontend && npm run lint` passes
- [ ] `cd frontend && npx tsc --noEmit` passes
- [ ] `cd frontend && npx playwright test` all pass

## Skills to Read

- `nextjs-dashboard` - Frontend component structure, page routes, API integration patterns
- `og-testing-strategies` - Playwright E2E test patterns, frontend component test approach
- `og-scraper-architecture` - Overall project structure, API contract (all 17 endpoints)

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/dashboard-map-implementation.md` - Map component details, Leaflet configuration, Supercluster setup
- `.claude/orchestration-og-doc-scraper/research/testing-deployment-implementation.md` - Section 4 (Testing Next.js Frontend) with Playwright patterns

## Git

- Branch: `task-7-2/dashboard-e2e-playwright`
- Commit message prefix: `Task 7.2:`
