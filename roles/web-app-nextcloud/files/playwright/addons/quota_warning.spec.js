const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test.use({ ignoreHTTPSErrors: true });

// quota_warning emails/notifies users approaching their storage quota and is
// configured under its admin settings section; it has no per-user app route.
// Log in as administrator and assert the admin quota-warning settings page
// renders as its observable surface.
test("quota_warning addon: admin quota-warning settings page renders", async ({ browser }) => {
  skipUnlessAddonEnabled("quota_warning");
  test.setTimeout(120_000);

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    const settingsUrl = new URL("settings/admin/quota_warning", shared.env.nextcloudBaseUrl).toString();
    await page.goto(settingsUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await shared.dismissBlockingNextcloudModals(page, page);

    await expect(
      page.locator("#app-content, #app-content-vue, #content, #content-vue").first(),
      "the Nextcloud admin quota-warning settings page must be visible (quota_warning has no per-user route)",
    ).toBeVisible({ timeout: 60_000 });
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
