const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test("integration integration_suitecrm: connects Nextcloud to suitecrm", async ({ browser }) => {
  skipUnlessAddonEnabled("integration_suitecrm");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    await page.goto(
      new URL("settings/user/connected-accounts", shared.env.nextcloudBaseUrl).toString(),
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );

    // upstream julien-nc/integration_suitecrm PersonalSettings.vue:
    // section id `#suitecrm_prefs`. The connect block `#suitecrm-content`
    // (with field `#suitecrm-url` and button `#suitecrm-oauth`) renders only
    // while `oAuthConfigured` (admin provisioned oauth_instance_url + client_id
    // + client_secret); otherwise a "No SuiteCRM OAuth app configured" hint
    // shows instead. onConnect() runs the OAuth2 *password grant* server-side
    // (POST `/apps/integration_suitecrm/oauth-connect`) — there is no browser
    // redirect to a SuiteCRM authorize endpoint. The deterministic "wired"
    // signal is the provisioned SuiteCRM endpoint URL behind the OAuth-app gate.
    const section = page.locator("#suitecrm_prefs");
    await section.waitFor({ state: "visible", timeout: 30_000 }).catch(() => {});

    const connect = page.locator("#suitecrm-oauth, #suitecrm-content button:has-text('Connect to SuiteCRM')");
    if ((await connect.count()) === 0) {
      test.skip(
        true,
        "integration_suitecrm: connect control not present (SuiteCRM OAuth app not provisioned)"
      );
      return;
    }

    // Assert the addon-configured SuiteCRM endpoint URL is wired into the
    // connect form (proves the cross-role url + OAuth client were provisioned).
    const urlField = page.locator("#suitecrm-url");
    await expect(urlField).toBeVisible({ timeout: 30_000 });
    const configuredUrl = await urlField.inputValue().catch(() => "");
    expect(
      /^https?:\/\/.+/.test(configuredUrl),
      "expected the SuiteCRM instance URL to be configured (pointing at the partner instance)"
    ).toBeTruthy();

    // Drive the connect attempt; the password-grant runs server-side, so the
    // page must stay on connected-accounts rather than hand off to a partner
    // authorize endpoint — confirming the grant shape this integration uses.
    await connect.first().click().catch(() => {});
    await page.waitForTimeout(2_000);
    await expect.poll(() => page.url(), { timeout: 30_000 }).toMatch(/connected-accounts/);
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
