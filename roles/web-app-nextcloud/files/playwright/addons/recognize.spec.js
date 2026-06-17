const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test.use({ ignoreHTTPSErrors: true });

// recognize runs background ML tagging of photos/audio/video and is configured
// under its admin settings section; it has no dedicated per-user route (its
// results surface inside Photos/Files tags). Log in as administrator and assert
// the admin recognize settings page renders as its observable surface.
test("recognize addon: admin recognize settings page renders", async ({ browser }) => {
  skipUnlessAddonEnabled("recognize");
  test.setTimeout(120_000);

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    const settingsUrl = new URL("settings/admin/recognize", shared.env.nextcloudBaseUrl).toString();
    await page.goto(settingsUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await shared.dismissBlockingNextcloudModals(page, page);

    await expect(
      page.locator("#app-content, #app-content-vue, #content, #content-vue").first(),
      "the Nextcloud admin recognize settings page must be visible (recognize is a background ML app, no per-user route)",
    ).toBeVisible({ timeout: 60_000 });
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
