import { test, expect } from "@playwright/test";
import { takeEvidenceScreenshot } from "./helpers";

test.describe("Wells Search & Browse", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/wells");
    await page.waitForLoadState("networkidle");
  });

  test("wells page heading visible", async ({ page }) => {
    await expect(page.locator("h1")).toContainText("Wells");
  });

  test("wells table renders", async ({ page }) => {
    const table = page.locator("table");
    await expect(table).toBeVisible();
    await takeEvidenceScreenshot(page, "03-wells-table");
  });

  test("search input exists and accepts text", async ({ page }) => {
    const searchInput = page.locator('input[placeholder="Search wells..."]');
    await expect(searchInput).toBeVisible();
    await searchInput.fill("Devon");
    await expect(searchInput).toHaveValue("Devon");
  });

  test("state filter dropdown works", async ({ page }) => {
    const stateSelect = page.locator("select").first();
    await expect(stateSelect).toBeVisible();
    await stateSelect.selectOption("TX");
    await takeEvidenceScreenshot(page, "04-wells-state-filter");
  });

  test("pagination controls are present", async ({ page }) => {
    const prevButton = page.locator('button:has-text("Previous")');
    const nextButton = page.locator('button:has-text("Next")');
    await expect(prevButton).toBeVisible();
    await expect(nextButton).toBeVisible();
  });
});

test.describe("Documents Browse", () => {
  test("documents page loads with table", async ({ page }) => {
    await page.goto("/documents");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("Documents");
    const table = page.locator("table");
    await expect(table).toBeVisible();
    await takeEvidenceScreenshot(page, "05-documents-table");
  });

  test("documents state filter works", async ({ page }) => {
    await page.goto("/documents");
    await page.waitForLoadState("networkidle");

    const stateSelect = page.locator("select").first();
    await expect(stateSelect).toBeVisible();
    await stateSelect.selectOption("TX");
  });
});
