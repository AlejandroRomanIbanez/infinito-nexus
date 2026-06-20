const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test("addon drawio: nextcloud app route renders its own drawio editor surface", async ({ browser }) => {
  skipUnlessAddonEnabled("drawio");
  test.setTimeout(120_000);

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloudWithRetry(page);

    const appUrl = new URL("apps/drawio/", shared.env.nextcloudBaseUrl).toString();
    const response = await page.goto(appUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });

    expect(
      response,
      "navigating to the drawio app route must yield an HTTP response",
    ).not.toBeNull();
    expect(
      response.status(),
      "the drawio app route must resolve (app installed + enabled), not 404",
    ).toBeLessThan(400);

    await shared.dismissBlockingNextcloudModals(page, page);

    const appContainer = page.locator(
      ".app-drawio, #drawio, #drawioframe, #app-content .drawio, #app-content-vue .drawio",
    );
    await expect(
      appContainer.first(),
      "the drawio Nextcloud app route must render its own drawio editor surface (disabled/broken app never mounts it)",
    ).toBeVisible({ timeout: 60_000 });
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
