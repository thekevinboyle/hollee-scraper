import { test, expect } from "@playwright/test";
import { takeEvidenceScreenshot } from "./helpers";

test.describe("Interactive Map", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/map");
    await page.waitForLoadState("networkidle");
  });

  test("map page heading visible", async ({ page }) => {
    await expect(page.locator("h1")).toContainText("Well Map");
  });

  test("leaflet map container renders", async ({ page }) => {
    const mapContainer = page.locator(".leaflet-container");
    await expect(mapContainer).toBeVisible({ timeout: 15_000 });
    await takeEvidenceScreenshot(page, "06-map-initial");
  });

  test("map tiles load", async ({ page }) => {
    await page.waitForSelector(".leaflet-container", { timeout: 15_000 });
    // Wait for at least one tile to load
    const tileCount = await page.locator(".leaflet-tile-loaded").count();
    expect(tileCount).toBeGreaterThanOrEqual(1);
    await takeEvidenceScreenshot(page, "07-map-tiles");
  });

  test("zoom controls are present", async ({ page }) => {
    await page.waitForSelector(".leaflet-container", { timeout: 15_000 });
    const zoomIn = page.locator(".leaflet-control-zoom-in");
    const zoomOut = page.locator(".leaflet-control-zoom-out");
    await expect(zoomIn).toBeVisible();
    await expect(zoomOut).toBeVisible();
  });

  test("zoom in works", async ({ page }) => {
    await page.waitForSelector(".leaflet-container", { timeout: 15_000 });
    const zoomIn = page.locator(".leaflet-control-zoom-in");
    await zoomIn.click();
    await page.waitForTimeout(500);
    await zoomIn.click();
    await page.waitForTimeout(500);
    await takeEvidenceScreenshot(page, "08-map-zoomed-in");
  });

  test("no critical console errors on map page", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        const text = msg.text();
        // Ignore tile loading errors and resource errors
        if (
          !text.includes("tile") &&
          !text.includes("Failed to load resource") &&
          !text.includes("favicon")
        ) {
          errors.push(text);
        }
      }
    });
    await page.goto("/map");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(3000);
    expect(errors).toEqual([]);
  });
});
