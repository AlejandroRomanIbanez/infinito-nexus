const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test.use({ ignoreHTTPSErrors: true });

// external (nextcloud/external) injects admin-configured external links/sites
// into the top menu and is configured under the admin "Additional settings"
// page; it has no dedicated per-user app route. Log in as administrator and
// assert the admin additional-settings page renders as its observable surface.
test("external addon: admin additional-settings page renders", async ({ browser }) => {
  skipUnlessAddonEnabled("external");
  test.setTimeout(120_000);

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    const settingsUrl = new URL("settings/admin/additional", shared.env.nextcloudBaseUrl).toString();
    await page.goto(settingsUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await shared.dismissBlockingNextcloudModals(page, page);

    await expect(
      page.locator("#app-content, #app-content-vue, #content, #content-vue").first(),
      "the Nextcloud admin additional-settings page must be visible (external sites are admin-configured, no dedicated user route)",
    ).toBeVisible({ timeout: 60_000 });
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
