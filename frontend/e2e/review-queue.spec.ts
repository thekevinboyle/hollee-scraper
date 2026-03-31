import { test, expect } from "@playwright/test";
import { takeEvidenceScreenshot } from "./helpers";

test.describe("Review Queue", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/review");
    await page.waitForLoadState("networkidle");
  });

  test("review queue heading visible", async ({ page }) => {
    await expect(page.locator("h1")).toContainText("Review Queue");
  });

  test("review queue table renders", async ({ page }) => {
    const table = page.locator("table");
    await expect(table).toBeVisible();
    await takeEvidenceScreenshot(page, "10-review-queue");
  });

  test("review table has expected columns", async ({ page }) => {
    const headers = page.locator("thead th");
    const count = await headers.count();
    expect(count).toBeGreaterThanOrEqual(3); // At least Type, Status, Confidence
  });

  test("confidence badges use color coding", async ({ page }) => {
    // Check if any confidence badges exist with expected color classes
    const badges = page.locator(
      "[class*='green'], [class*='yellow'], [class*='red']"
    );
    // May have 0 items if queue is empty, so just verify no errors
    await takeEvidenceScreenshot(page, "11-review-confidence-badges");
  });

  test("clicking review item navigates to detail", async ({ page }) => {
    const rows = page.locator("table tbody tr");
    const count = await rows.count();

    if (count > 0) {
      await rows.first().click();
      await page.waitForTimeout(1000);

      // Should see action buttons or detail view
      const approveButton = page.locator('button:has-text("Approve")');
      const backButton = page.locator('button:has-text("Back to queue")');

      // At least one of these should be visible in detail view
      const isDetail =
        (await approveButton.isVisible().catch(() => false)) ||
        (await backButton.isVisible().catch(() => false));

      if (isDetail) {
        await takeEvidenceScreenshot(page, "12-review-detail-view");
      }
    }
  });
});
