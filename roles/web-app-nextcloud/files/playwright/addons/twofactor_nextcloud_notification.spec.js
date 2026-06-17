const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test.use({ ignoreHTTPSErrors: true });

// twofactor_nextcloud_notification adds a push/notification-based 2FA provider.
// Its browser-observable surface is the per-user "Security" settings page, where
// the 2FA section lists the available providers. The addon is only enabled when
// SSO is disabled (see meta/addons/twofactor_nextcloud_notification.yml), so the
// native NC login flow applies. Log in and assert the security settings page
// renders.
test("twofactor_nextcloud_notification addon: user security settings page renders", async ({ browser }) => {
  skipUnlessAddonEnabled("twofactor_nextcloud_notification");
  test.setTimeout(120_000);

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    const securityUrl = new URL("settings/user/security", shared.env.nextcloudBaseUrl).toString();
    await page.goto(securityUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await shared.dismissBlockingNextcloudModals(page, page);

    await expect(
      page.locator("#app-content, #app-content-vue, #content, #content-vue").first(),
      "the Nextcloud user security settings page must be visible (twofactor_nextcloud_notification surfaces in its 2FA section)",
    ).toBeVisible({ timeout: 60_000 });
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
