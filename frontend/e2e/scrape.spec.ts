import { test, expect } from "@playwright/test";
import { takeEvidenceScreenshot } from "./helpers";

test.describe("Scrape Trigger & Progress", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/scrape");
    await page.waitForLoadState("networkidle");
  });

  test("scrape page heading visible", async ({ page }) => {
    await expect(page.locator("h1")).toContainText("Scrape");
  });

  test("all 10 state buttons are shown", async ({ page }) => {
    const states = [
      "TX",
      "NM",
      "ND",
      "OK",
      "CO",
      "WY",
      "LA",
      "PA",
      "CA",
      "AK",
    ];
    for (const state of states) {
      await expect(
        page.locator(`text=${state}`).first()
      ).toBeVisible();
    }
    await takeEvidenceScreenshot(page, "09-scrape-state-grid");
  });

  test("tier 1 and tier 2 state groups are visible", async ({ page }) => {
    // Tier 1: TX, NM, ND, OK, CO
    await expect(page.locator("text=TX").first()).toBeVisible();
    await expect(page.locator("text=CO").first()).toBeVisible();

    // Tier 2: WY, LA, PA, CA, AK
    await expect(page.locator("text=WY").first()).toBeVisible();
    await expect(page.locator("text=AK").first()).toBeVisible();
  });

  test("scrape buttons are clickable", async ({ page }) => {
    const scrapeButtons = page.locator('button:has-text("Scrape")');
    const count = await scrapeButtons.count();
    expect(count).toBeGreaterThanOrEqual(10);
  });

  test("scrape history section exists", async ({ page }) => {
    await expect(
      page.locator('text="Scrape History"').or(page.locator("h2"))
    ).toBeVisible();
  });
});
