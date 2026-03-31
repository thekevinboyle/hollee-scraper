import { Page } from "@playwright/test";

export async function waitForPageLoad(page: Page) {
  await page.waitForLoadState("networkidle");
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
