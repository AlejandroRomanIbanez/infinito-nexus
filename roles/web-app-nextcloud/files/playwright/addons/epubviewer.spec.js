const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test("addon epubviewer: nextcloud app route renders", async ({ browser }) => {
  skipUnlessAddonEnabled("epubviewer");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    const appUrl = new URL("apps/epubviewer/", shared.env.nextcloudBaseUrl).toString();
    await page.goto(appUrl, { waitUntil: "commit", timeout: 60_000 });

    const appContainer = page.locator(
      "#app-content, #app-content-vue, #content, #content-vue, .app-epubviewer"
    );
    await expect(appContainer.first()).toBeVisible({ timeout: 60_000 });
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
