const { test, expect } = require("@playwright/test");

const PLATFORM_FAVICON_URL = process.env.PLATFORM_FAVICON_URL || "";

exports.register = function (shared) {
  test("dashboard card icons resolve to the public Simple Icons URL when enabled, and to the platform favicon otherwise", async ({ page }) => {
    await page.goto("/");
    await shared.waitForDashboardReady(page);

    await expect(
      page.locator(".card-img-top").first(),
      "Expected at least one dashboard card with a rendered icon"
    ).toBeVisible({ timeout: 60_000 });

    // Regression guard for the original bug: no card may still reference the
    // internal Docker bridge IP that the buggy DASHBOARD_SIMPLEICONS_SYNC_URL_BASE
    // used to be rendered with.
    await expect(
      page.locator(".card-img-top img[src*='172.17.0.1']"),
      "No card icon may point at the internal Docker bridge IP"
    ).toHaveCount(0);

    if (shared.isServiceEnabled("simpleicons")) {
      const simpleiconsImg = page.locator(".card-img-top img[src*='//icon.']").first();
      await expect(
        simpleiconsImg,
        "Expected at least one card icon to load from the public Simple Icons domain (icon.<DOMAIN>)"
      ).toBeVisible({ timeout: 60_000 });

      const src = await simpleiconsImg.getAttribute("src");
      expect(
        src,
        "Expected the Simple Icons URL to be an absolute SVG under icon.<DOMAIN>"
      ).toMatch(/^https?:\/\/icon\.[^/]+\/[^/]+\.svg$/);
    } else {
      expect(
        PLATFORM_FAVICON_URL,
        "PLATFORM_FAVICON_URL must be rendered in the Playwright env so the fallback assertion can identify it"
      ).toBeTruthy();

      const faviconBasename = PLATFORM_FAVICON_URL.split("/").pop();
      await expect(
        page.locator(`.card-img-top img[src*='${faviconBasename}']`).first(),
        "Expected card icons to fall back to the platform favicon when the Simple Icons service is disabled"
      ).toBeVisible({ timeout: 60_000 });
    }
  });
};
