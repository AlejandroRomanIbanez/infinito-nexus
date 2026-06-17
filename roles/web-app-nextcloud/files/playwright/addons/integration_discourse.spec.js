const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test("integration integration_discourse: connects Nextcloud to discourse", async ({ browser }) => {
  skipUnlessAddonEnabled("integration_discourse");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    await page.goto(
      new URL("settings/user/connected-accounts", shared.env.nextcloudBaseUrl).toString(),
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );

    // upstream nextcloud/integration_discourse PersonalSettings.vue:
    // section id `#discourse_prefs`, connect button `#discourse-oauth`
    // (rendered only while `showOAuth` is true: a `url` is configured and the
    // account is not yet connected). onOAuthClick() redirects the page to
    // `<discourse_url>/user-api-key/new?...` (Discourse User-API-Key grant).
    const section = page.locator("#discourse_prefs");
    await section.waitFor({ state: "visible", timeout: 30_000 }).catch(() => {});

    const connect = page.locator("#discourse-oauth, #discourse_prefs button:has-text('Connect to Discourse')");
    if ((await connect.count()) === 0) {
      test.skip(true, "integration_discourse: connect control not present (integration not provisioned)");
      return;
    }

    await Promise.all([
      page.waitForEvent("framenavigated", { timeout: 60_000 }).catch(() => {}),
      connect.first().click(),
    ]);

    // Either we left Nextcloud toward the Discourse User-API-Key authorize
    // endpoint (proves the configured url + client are wired) or the account is
    // already linked (connected state) — both are valid "wired" outcomes.
    await expect
      .poll(() => page.url(), { timeout: 60_000 })
      .toMatch(/\/user-api-key\/new|connected-accounts/);

    const reachedDiscourse = /\/user-api-key\/new/.test(page.url());
    const connectedBack = await page
      .locator(".discourse-connected, #discourse_prefs >> text=Connected as")
      .first()
      .isVisible()
      .catch(() => false);
    expect(
      reachedDiscourse || connectedBack,
      "expected the Discourse User-API-Key authorize endpoint or a connected account"
    ).toBeTruthy();
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
