const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test.use({ ignoreHTTPSErrors: true });

// files_bpm registers an in-Files audio/video player; it has no standalone
// route, it only augments the Files app. Log in, open Files, and assert the
// Files app content renders with the player app registered.
test("files_bpm addon: Files app loads with the media player registered", async ({ browser }) => {
  skipUnlessAddonEnabled("files_bpm");
  test.setTimeout(120_000);

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    const filesUrl = new URL("apps/files/", shared.env.nextcloudBaseUrl).toString();
    await page.goto(filesUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await shared.dismissBlockingNextcloudModals(page, page);

    await expect(
      page.locator("#app-content, #app-content-vue, #app-navigation-vue").first(),
      "the Nextcloud Files app content must be visible with the files_bpm media player registered",
    ).toBeVisible({ timeout: 60_000 });
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
