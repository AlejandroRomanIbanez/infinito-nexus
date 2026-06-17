const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test.use({ ignoreHTTPSErrors: true });

// event_update_notification is a backend-only Calendar companion app: it emits
// notifications when an attendee updates an event and exposes no dedicated user
// route. Its only browser-observable surface is the admin "installed apps" list,
// so log in as administrator and assert that page renders.
test("event_update_notification addon: installed-apps settings page renders", async ({ browser }) => {
  skipUnlessAddonEnabled("event_update_notification");
  test.setTimeout(120_000);

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    const appsUrl = new URL("settings/apps/installed", shared.env.nextcloudBaseUrl).toString();
    await page.goto(appsUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await shared.dismissBlockingNextcloudModals(page, page);

    await expect(
      page.locator("#app-content, #app-content-vue, #content, #content-vue").first(),
      "the Nextcloud installed-apps settings page must be visible (event_update_notification has no dedicated user route)",
    ).toBeVisible({ timeout: 60_000 });
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
