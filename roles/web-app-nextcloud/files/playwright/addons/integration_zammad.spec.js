const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test("integration integration_zammad: connects Nextcloud to zammad", async ({ browser }) => {
  skipUnlessAddonEnabled("integration_zammad");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    await page.goto(
      new URL("settings/user/connected-accounts", shared.env.nextcloudBaseUrl).toString(),
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );

    // upstream nextcloud/integration_zammad PersonalSettings.vue:
    // section id `#zammad_prefs`. The OAuth button `#zammad-oauth` ("Connect to
    // Zammad") renders only while `showOAuth` (the addon-configured url equals
    // the admin oauth_instance_url AND a client_id is set). onOAuthClick()
    // redirects the page to `<zammad_url>/oauth/authorize?client_id=...`.
    // Without that OAuth provisioning the section only exposes a personal-token
    // field (no connect button) — skip cleanly.
    const section = page.locator("#zammad_prefs");
    await section.waitFor({ state: "visible", timeout: 30_000 }).catch(() => {});

    const connect = page.locator("#zammad-oauth");
    if ((await connect.count()) === 0) {
      test.skip(true, "integration_zammad: OAuth connect control not present (integration not provisioned)");
      return;
    }

    await Promise.all([
      page.waitForEvent("framenavigated", { timeout: 60_000 }).catch(() => {}),
      connect.first().click(),
    ]);

    // Assert the flow reached the Zammad OAuth authorize endpoint
    // (`<zammad_url>/oauth/authorize`) — strongest signal the URL + client are
    // wired — or that the account shows connected back in Nextcloud.
    await expect
      .poll(() => page.url(), { timeout: 60_000 })
      .toMatch(/\/oauth\/authorize|connected-accounts/);

    const reachedAuthorize = /\/oauth\/authorize/.test(page.url());
    const connectedBack = await page
      .locator(".zammad-connected, #zammad_prefs >> text=Connected as")
      .first()
      .isVisible()
      .catch(() => false);
    expect(
      reachedAuthorize || connectedBack,
      "expected the Zammad /oauth/authorize endpoint or a connected account"
    ).toBeTruthy();
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
