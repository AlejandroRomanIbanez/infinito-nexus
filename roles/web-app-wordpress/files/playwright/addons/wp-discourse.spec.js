const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test("addon wp-discourse: settings page reachable in wp-admin", async ({ browser }) => {
  skipUnlessAddonEnabled("wp-discourse");

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
      `${shared.env.wpBaseUrl}/wp-admin/admin.php?page=wp_discourse_options`,
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );

    const settingsSurface = page
      .locator(
        "form#wp-discourse-form, .wp-discourse-options, #wpbody-content .wrap, .nav-tab-wrapper"
      )
      .filter({ hasText: /discourse/i })
      .first();

    await expect(
      settingsSurface,
      "Expected the WP Discourse settings surface in wp-admin"
    ).toBeVisible({ timeout: 30_000 });
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
