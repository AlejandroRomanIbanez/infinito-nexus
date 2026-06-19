const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test("integration integration_openproject: two-way OAuth coupling provisioned and connectable to partner OpenProject", async ({ browser }) => {
  skipUnlessAddonEnabled("integration_openproject");
  test.setTimeout(120_000);

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    await page.goto(
      new URL("settings/admin/openproject", shared.env.nextcloudBaseUrl).toString(),
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );
    await shared.dismissBlockingNextcloudModals(page, page);

    const adminSection = page
      .locator("#openproject_prefs, #openproject-server-host, #openproject-prefs")
      .or(page.getByText(/openproject/i))
      .first();
    await expect(
      adminSection,
      "the OpenProject integration admin settings section must render when the addon is enabled"
    ).toBeVisible({ timeout: 60_000 });

    const oauthConfigured = page
      .locator('input[id*="openproject-oauth-client-id"], input[id*="client-id"], input[id*="client-secret"]')
      .or(page.getByText(/reset oauth|replace oauth|nextcloud oauth (client|values)/i))
      .or(page.getByText(/oauth client id|client secret/i))
      .first();
    await expect(
      oauthConfigured,
      "the admin panel must show the provisioned OAuth client (proves the two-way OAuth pair is registered on BOTH sides). When integration_openproject is enabled but this is absent, the coupling failed to provision — the test MUST fail here, not skip."
    ).toBeVisible({ timeout: 60_000 });

    const instanceUrlField = page.locator(
      'input[id*="openproject-oauth-instance"], input[id*="server-host"], input[type="url"], input[name*="instance"]'
    );
    const fieldCount = await instanceUrlField.count();
    const nextcloudHost = new URL(shared.env.nextcloudBaseUrl).host;
    let instanceHost = null;
    for (let i = 0; i < fieldCount; i += 1) {
      const value = (await instanceUrlField.nth(i).inputValue().catch(() => "")) || "";
      if (/^https?:\/\//i.test(value)) {
        instanceHost = new URL(value).host;
        break;
      }
    }
    expect(instanceHost, "the OpenProject instance URL must be configured on the admin panel").toBeTruthy();
    expect(
      instanceHost,
      "the configured OpenProject instance URL must be the partner host, not the Nextcloud host"
    ).not.toBe(nextcloudHost);

    await page.goto(
      new URL("settings/user/connected-accounts", shared.env.nextcloudBaseUrl).toString(),
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );
    await shared.dismissBlockingNextcloudModals(page, page);

    const connect = page
      .getByRole("button", { name: /connect to openproject/i })
      .or(page.getByRole("link", { name: /connect to openproject/i }))
      .first();
    await expect(
      connect,
      "the 'Connect to OpenProject' control must render once the OAuth client is provisioned — its absence means the coupling failed to land"
    ).toBeVisible({ timeout: 60_000 });

    const popupPromise = page.waitForEvent("popup", { timeout: 15_000 }).catch(() => null);
    await Promise.all([
      page.waitForEvent("framenavigated", { timeout: 60_000 }).catch(() => {}),
      connect.click(),
    ]);

    const popup = await popupPromise;
    const currentUrl = () => (popup ? popup.url() : page.url());

    await expect.poll(currentUrl, { timeout: 60_000 }).toMatch(/\/oauth\/authorize\?/i);

    const finalUrl = new URL(currentUrl());
    expect(
      finalUrl.host,
      "the OpenProject OAuth authorize must be served by the partner instance, not Nextcloud"
    ).not.toBe(nextcloudHost);
    expect(
      finalUrl.searchParams.get("client_id"),
      "the authorize redirect must carry the provisioned OpenProject OAuth client_id"
    ).toBeTruthy();
    expect(finalUrl.searchParams.get("response_type")).toBe("code");

    if (popup) await popup.close().catch(() => {});
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
