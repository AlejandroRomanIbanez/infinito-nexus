const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test("integration integration_mattermost: connects Nextcloud to mattermost", async ({ browser }) => {
  skipUnlessAddonEnabled("integration_mattermost");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    await page.goto(
      new URL("settings/user/connected-accounts", shared.env.nextcloudBaseUrl).toString(),
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );

    // upstream nextcloud/integration_mattermost PersonalSettings.vue:
    // section id `#mattermost_prefs`, connect button `#mattermost-connect`.
    // onConnectClick() only performs an OAuth handoff to
    // `<mattermost_url>/oauth/authorize` when `showOAuth` is true (the admin
    // configured client_id + client_secret for the same instance url). Without
    // that Tier-2 OAuth provisioning the same button connects via a personal
    // token / login+password and never leaves Nextcloud. The OAuth-only block
    // `#mattermost-connect-block .oauth` is the deterministic marker of a wired
    // OAuth client; absent it, skip rather than asserting a non-OAuth connect.
    const section = page.locator("#mattermost_prefs");
    await section.waitFor({ state: "visible", timeout: 30_000 }).catch(() => {});

    const connect = page.locator("#mattermost-connect");
    if ((await connect.count()) === 0) {
      test.skip(true, "integration_mattermost: connect control not present (integration not provisioned)");
      return;
    }

    // The OAuth-specific copy ("...with OAuth") only renders when
    // client_id/secret are set (showOAuth). Without it the same button performs
    // a personal-token / login+password connect that never leaves Nextcloud, so
    // there is no partner authorize redirect to drive — skip instead.
    const oauthActive = await page
      .locator("#mattermost_prefs >> text=/OAuth/i")
      .first()
      .isVisible()
      .catch(() => false);
    if (!oauthActive) {
      test.skip(
        true,
        "integration_mattermost: OAuth client not provisioned (token/password connect only, no authorize redirect)"
      );
      return;
    }

    await Promise.all([
      page.waitForEvent("framenavigated", { timeout: 60_000 }).catch(() => {}),
      connect.first().click(),
    ]);

    // Assert the flow reached the Mattermost OAuth authorize endpoint
    // (`<mattermost_url>/oauth/authorize`) — strongest signal the URL + client
    // are wired — or that the account already shows connected back in Nextcloud.
    await expect
      .poll(() => page.url(), { timeout: 60_000 })
      .toMatch(/\/oauth\/authorize|connected-accounts/);

    const reachedAuthorize = /\/oauth\/authorize/.test(page.url());
    const connectedBack = await page
      .locator(".mattermost-connected, #mattermost_prefs >> text=Connected as")
      .first()
      .isVisible()
      .catch(() => false);
    expect(
      reachedAuthorize || connectedBack,
      "expected the Mattermost /oauth/authorize endpoint or a connected account"
    ).toBeTruthy();
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
