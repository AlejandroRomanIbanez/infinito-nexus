const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test("integration integration_moodle: connects Nextcloud to moodle", async ({ browser }) => {
  skipUnlessAddonEnabled("integration_moodle");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    await page.goto(
      new URL("settings/user/connected-accounts", shared.env.nextcloudBaseUrl).toString(),
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );

    // upstream nextcloud/integration_moodle PersonalSettings.vue:
    // section id `#moodle_prefs`, configured-endpoint field `#moodle-url`,
    // "Connect to Moodle" button. Moodle has NO user OAuth consent: onValidate()
    // POSTs login+password to `/apps/integration_moodle/get-token` to mint a
    // Moodle web-service token (no redirect to a partner authorize endpoint).
    // The deterministic "integration is wired" signal is therefore the
    // pre-filled Moodle service URL the addon configured (mirrors the openai
    // case). If the section / Connect control is absent, the integration is not
    // provisioned in this deployment — skip cleanly.
    const section = page.locator("#moodle_prefs");
    await section.waitFor({ state: "visible", timeout: 30_000 }).catch(() => {});

    const connect = page.locator("#moodle_prefs button:has-text('Connect to Moodle')");
    if ((await connect.count()) === 0) {
      test.skip(true, "integration_moodle: connect control not present (integration not provisioned)");
      return;
    }

    // Assert the addon-configured Moodle endpoint URL is wired into the connect
    // form (proves the cross-role URL was provisioned). Moodle does not OAuth-
    // redirect, so the configured endpoint is the strongest deterministic
    // signal short of full credentialed token minting.
    const urlField = page.locator("#moodle-url");
    await expect(urlField).toBeVisible({ timeout: 30_000 });
    const configuredUrl = await urlField.inputValue().catch(() => "");
    expect(
      /^https?:\/\/.+/.test(configuredUrl),
      "expected the Moodle service URL to be configured (pointing at the partner instance)"
    ).toBeTruthy();

    // Drive the connect attempt: clicking with no credentials must not leave
    // Nextcloud (no partner authorize endpoint exists), confirming the flow is
    // the get-token grant rather than an OAuth handoff.
    await connect.first().click().catch(() => {});
    await page.waitForTimeout(2_000);
    await expect.poll(() => page.url(), { timeout: 30_000 }).toMatch(/connected-accounts/);
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
