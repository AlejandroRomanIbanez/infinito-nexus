const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test.use({ ignoreHTTPSErrors: true });

// groupfolders is an admin-managed app: admins define group folders under the
// admin settings section, and end users only see the resulting folders inside
// the Files app. Its dedicated browser-observable surface is the admin
// groupfolders settings page, so log in as administrator and assert it renders.
test("groupfolders addon: admin group-folders settings page renders", async ({ browser }) => {
  skipUnlessAddonEnabled("groupfolders");
  test.setTimeout(120_000);

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    const settingsUrl = new URL("settings/admin/groupfolders", shared.env.nextcloudBaseUrl).toString();
    await page.goto(settingsUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await shared.dismissBlockingNextcloudModals(page, page);

    await expect(
      page.locator("#app-content, #app-content-vue, #content, #content-vue").first(),
      "the Nextcloud admin group-folders settings page must be visible",
    ).toBeVisible({ timeout: 60_000 });
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
