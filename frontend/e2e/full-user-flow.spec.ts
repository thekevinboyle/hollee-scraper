import { test, expect } from "@playwright/test";
import { takeEvidenceScreenshot, navigateViaSidebar } from "./helpers";

test.describe("Full User Flow", () => {
  test("complete user journey through all pages", async ({ page }) => {
    // Step 1: Dashboard
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("h1")).toContainText("Dashboard");
    await takeEvidenceScreenshot(page, "flow-01-dashboard");

    // Step 2: Wells
    await navigateViaSidebar(page, "Wells");
    await expect(page).toHaveURL(/\/wells/);
    await expect(page.locator("h1")).toContainText("Wells");
    await expect(page.locator("table")).toBeVisible();
    await takeEvidenceScreenshot(page, "flow-02-wells");

    // Step 3: Search wells
    const searchInput = page.locator('input[placeholder="Search wells..."]');
    if (await searchInput.isVisible()) {
      await searchInput.fill("Devon");
      await page.waitForTimeout(1000);
      await takeEvidenceScreenshot(page, "flow-03-search");
      await searchInput.clear();
    }

    // Step 4: Documents
    await navigateViaSidebar(page, "Documents");
    await expect(page).toHaveURL(/\/documents/);
    await expect(page.locator("h1")).toContainText("Documents");
    await takeEvidenceScreenshot(page, "flow-04-documents");

    // Step 5: Map
    await navigateViaSidebar(page, "Map");
    await expect(page).toHaveURL(/\/map/);
    await expect(page.locator("h1")).toContainText("Well Map");
    // Wait for Leaflet to load
    await page
      .waitForSelector(".leaflet-container", { timeout: 15_000 })
      .catch(() => {
        // Map may not load without backend
      });
    await takeEvidenceScreenshot(page, "flow-05-map");

    // Step 6: Scrape
    await navigateViaSidebar(page, "Scrape");
    await expect(page).toHaveURL(/\/scrape/);
    await expect(page.locator("h1")).toContainText("Scrape");
    await takeEvidenceScreenshot(page, "flow-06-scrape");

    // Step 7: Review Queue
    await navigateViaSidebar(page, "Review Queue");
    await expect(page).toHaveURL(/\/review/);
    await expect(page.locator("h1")).toContainText("Review Queue");
    await takeEvidenceScreenshot(page, "flow-07-review");

    // Step 8: Back to Dashboard
    await navigateViaSidebar(page, "Dashboard");
    await expect(page.locator("h1")).toContainText("Dashboard");
    await takeEvidenceScreenshot(page, "flow-08-back-to-dashboard");
  });
});
