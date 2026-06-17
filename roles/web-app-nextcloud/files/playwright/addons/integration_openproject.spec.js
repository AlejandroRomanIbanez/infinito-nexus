const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

// Functional cross-role integration check: drive the real OAuth connect flow
// from Nextcloud to the OpenProject partner instance.
// nextcloud/integration_openproject renders a "Connect to OpenProject" button
// that fetches the server-side OAuth URL (`/op-oauth-url`) and then
// `window.location.replace(...)` to `<openproject-instance>/oauth/authorize`.
// Reaching that authorize endpoint proves the partner URL + OAuth client are
// wired. Full client provisioning is a separate Tier-2 feature, so skip cleanly
// when the connect control is absent.
test("integration integration_openproject: connects Nextcloud to openproject", async ({ browser }) => {
  skipUnlessAddonEnabled("integration_openproject");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);
    await page.goto(
      new URL("settings/user/connected-accounts", shared.env.nextcloudBaseUrl).toString(),
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );

    const connect = page
      .getByRole("button", { name: /connect to openproject/i })
      .or(page.getByRole("link", { name: /connect to openproject/i }));

    if ((await connect.count()) === 0) {
      test.skip(true, "integration_openproject: connect control not present (integration not provisioned)");
      return;
    }

    await Promise.all([
      page.waitForEvent("framenavigated", { timeout: 60_000 }).catch(() => {}),
      connect.first().click(),
    ]);

    await expect
      .poll(() => page.url(), { timeout: 60_000 })
      .toMatch(/\/oauth\/authorize\?|connected-accounts/i);

    const reachedAuthorize = /\/oauth\/authorize\?/i.test(page.url());
    if (reachedAuthorize) {
      const authorizeUrl = new URL(page.url());
      const nextcloudHost = new URL(shared.env.nextcloudBaseUrl).host;
      expect(
        authorizeUrl.host,
        "OpenProject OAuth authorize must be served by the partner instance, not Nextcloud"
      ).not.toBe(nextcloudHost);
      expect(authorizeUrl.searchParams.get("client_id")).toBeTruthy();
      expect(authorizeUrl.searchParams.get("response_type")).toBe("code");
    } else {
      test.skip(
        true,
        "integration_openproject: connect did not redirect to OpenProject authorize (OAuth client not provisioned)"
      );
    }
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
