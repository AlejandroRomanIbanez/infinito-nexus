const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test("addon activitypub: settings page reachable in wp-admin", async ({ browser }) => {
  skipUnlessAddonEnabled("activitypub");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.wpAdminLoginViaOidc(
      page,
      shared.env.wpBaseUrl,
      shared.env.adminUsername,
      shared.env.adminPassword
    );

    await page.goto(
      `${shared.env.wpBaseUrl}/wp-admin/options-general.php?page=activitypub`,
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );

    const settingsSurface = page
      .locator(
        "form#activitypub-settings, .activitypub-settings-page, .activitypub_settings_page, #wpbody-content .wrap"
      )
      .filter({ hasText: /activitypub|fediverse|federation/i })
      .first();

    await expect(
      settingsSurface,
      "Expected the ActivityPub settings surface in wp-admin"
    ).toBeVisible({ timeout: 30_000 });
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
