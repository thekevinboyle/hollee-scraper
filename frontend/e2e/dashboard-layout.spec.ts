import { test, expect } from "@playwright/test";
import { takeEvidenceScreenshot, navigateViaSidebar } from "./helpers";

test.describe("Dashboard Layout & Navigation", () => {
  test("renders sidebar with all navigation links", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    const sidebar = page.locator("nav");
    await expect(sidebar).toBeVisible();

    const navItems = [
      "Dashboard",
      "Wells",
      "Documents",
      "Map",
      "Scrape",
      "Review Queue",
    ];
    for (const item of navItems) {
      await expect(sidebar.locator(`text=${item}`)).toBeVisible();
    }

    await takeEvidenceScreenshot(page, "01-dashboard-layout");
  });

  test("sidebar navigation routes to correct pages", async ({ page }) => {
    await page.goto("/");

    const routes = [
      { name: "Wells", urlPattern: /\/wells/ },
      { name: "Documents", urlPattern: /\/documents/ },
      { name: "Map", urlPattern: /\/map/ },
      { name: "Scrape", urlPattern: /\/scrape/ },
      { name: "Review Queue", urlPattern: /\/review/ },
    ];

    for (const route of routes) {
      await navigateViaSidebar(page, route.name);
      await expect(page).toHaveURL(route.urlPattern);
    }
  });

  test("dashboard home shows statistics cards", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("h1")).toContainText("Dashboard");

    const cardTitles = [
      "Total Wells",
      "Total Documents",
      "Pending Review",
      "Avg Confidence",
    ];
    for (const title of cardTitles) {
      await expect(
        page.locator(`text=${title}`).first()
      ).toBeVisible();
    }

    await takeEvidenceScreenshot(page, "02-dashboard-home");
  });

  test("no console errors on dashboard home", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        const text = msg.text();
        // Ignore common non-critical errors
        if (
          !text.includes("Failed to load resource") &&
          !text.includes("favicon")
        ) {
          errors.push(text);
        }
      }
    });
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    expect(errors).toEqual([]);
  });
});
