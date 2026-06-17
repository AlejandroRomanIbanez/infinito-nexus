const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test("integration integration_matrix: connects Nextcloud to matrix", async ({ browser }) => {
  skipUnlessAddonEnabled("integration_matrix");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    await page.goto(
      new URL("settings/user/connected-accounts", shared.env.nextcloudBaseUrl).toString(),
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );

    // upstream nextcloud/integration_matrix PersonalSettings.vue:
    // section id `#matrix_prefs`. The "Connect with OAuth" button renders only
    // while `state.oauth_possible` (admin provisioned an OAuth client + server
    // url). connectWithOauth() POSTs to `/apps/integration_matrix/oauth-start`,
    // which returns the Matrix server's discovered `authorization_endpoint`,
    // then the page does window.location.replace(authorization_url). Without
    // OAuth provisioning the section only offers the manual access-token
    // connect (no authorize redirect) — skip in that case.
    const section = page.locator("#matrix_prefs");
    await section.waitFor({ state: "visible", timeout: 30_000 }).catch(() => {});

    const connect = page.getByRole("button", { name: /connect with oauth/i });
    if ((await connect.count()) === 0) {
      test.skip(true, "integration_matrix: OAuth connect control not present (integration not provisioned)");
      return;
    }

    await Promise.all([
      page.waitForEvent("framenavigated", { timeout: 60_000 }).catch(() => {}),
      connect.first().click(),
    ]);

    // Assert the flow reached the Matrix server's OAuth authorize endpoint (the
    // discovered authorization_endpoint always carries an `authorize` path +
    // the configured client_id) — strongest signal the URL + client are wired —
    // or that the account shows connected back in Nextcloud.
    await expect
      .poll(() => page.url(), { timeout: 60_000 })
      .toMatch(/authorize|connected-accounts/i);

    const reachedAuthorize = /authorize/i.test(page.url()) && !/connected-accounts/.test(page.url());
    const connectedBack = await page
      .locator(".matrix-connected, #matrix_prefs >> text=Connected as")
      .first()
      .isVisible()
      .catch(() => false);
    expect(
      reachedAuthorize || connectedBack,
      "expected the Matrix OAuth authorize endpoint or a connected account"
    ).toBeTruthy();
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
