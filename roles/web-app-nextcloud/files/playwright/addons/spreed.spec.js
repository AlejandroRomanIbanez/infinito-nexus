const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const { skipUnlessServiceEnabled } = require("../service-gating");
const shared = require("../_shared");

test.use({ ignoreHTTPSErrors: true });

test("spreed addon: Talk app loads", async ({ browser }) => {
  skipUnlessAddonEnabled("spreed");
  skipUnlessServiceEnabled("talk");
  test.setTimeout(120_000);

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    const spreedUrl = new URL("apps/spreed/", shared.env.nextcloudBaseUrl).toString();
    await page.goto(spreedUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await shared.dismissBlockingNextcloudModals(page, page);

    await expect(
      page.locator("#app-content, #content-vue").first(),
      "the Nextcloud Talk (spreed) app content must be visible",
    ).toBeVisible({ timeout: 60_000 });
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
