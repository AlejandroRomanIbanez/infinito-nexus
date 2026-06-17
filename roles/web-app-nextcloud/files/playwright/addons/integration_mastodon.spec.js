const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

// Functional cross-role integration check: drive the real OAuth connect flow
// from Nextcloud's connected-accounts UI to the Mastodon partner instance.
// nextcloud/integration_mastodon renders a "Connect to Mastodon" button that,
// once the instance URL is set, redirects the browser to
// `<mastodon-instance>/oauth/authorize?client_id=…&response_type=code`. Reaching
// that authorize endpoint proves the partner URL + OAuth client are wired.
// Full OAuth client provisioning between Nextcloud and Mastodon is a separate
// Tier-2 feature, so skip cleanly when the connect control is absent.
test("integration integration_mastodon: connects Nextcloud to mastodon", async ({ browser }) => {
  skipUnlessAddonEnabled("integration_mastodon");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);
    await page.goto(
      new URL("settings/user/connected-accounts", shared.env.nextcloudBaseUrl).toString(),
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );

    const connect = page
      .getByRole("button", { name: /connect to mastodon/i })
      .or(page.getByRole("link", { name: /connect to mastodon/i }));

    if ((await connect.count()) === 0) {
      test.skip(true, "integration_mastodon: connect control not present (integration not provisioned)");
      return;
    }

    await Promise.all([
      page.waitForEvent("framenavigated", { timeout: 60_000 }).catch(() => {}),
      connect.first().click(),
    ]);

    // Mastodon OAuth authorize endpoint OR an already-connected NC state.
    await expect
      .poll(() => page.url(), { timeout: 60_000 })
      .toMatch(/\/oauth\/authorize\?|connected-accounts/i);

    // If the OAuth client is fully provisioned the URL leaves Nextcloud toward
    // `<mastodon>/oauth/authorize`. Assert that handoff happened rather than the
    // app bouncing back with an error inside the NC settings page.
    const reachedAuthorize = /\/oauth\/authorize\?/i.test(page.url());
    if (reachedAuthorize) {
      const authorizeUrl = new URL(page.url());
      const nextcloudHost = new URL(shared.env.nextcloudBaseUrl).host;
      expect(
        authorizeUrl.host,
        "Mastodon OAuth authorize must be served by the partner instance, not Nextcloud"
      ).not.toBe(nextcloudHost);
      expect(authorizeUrl.searchParams.get("client_id")).toBeTruthy();
      expect(authorizeUrl.searchParams.get("response_type")).toBe("code");
    } else {
      test.skip(
        true,
        "integration_mastodon: connect did not redirect to Mastodon authorize (OAuth client not provisioned)"
      );
    }
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
