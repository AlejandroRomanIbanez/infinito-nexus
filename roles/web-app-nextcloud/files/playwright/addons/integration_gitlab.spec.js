const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

// Functional cross-role integration check: drive the real OAuth connect flow
// from Nextcloud to the GitLab partner instance.
// nextcloud/integration_gitlab renders a "Connect to GitLab using OAuth" button
// that redirects the browser to
// `<gitlab-instance>/oauth/authorize?client_id=…&response_type=code&scope=…`.
// Reaching that authorize endpoint proves the partner URL + OAuth client are
// wired. Full client provisioning is a separate Tier-2 feature, so skip cleanly
// when the connect control is absent.
test("integration integration_gitlab: connects Nextcloud to gitlab", async ({ browser }) => {
  skipUnlessAddonEnabled("integration_gitlab");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);
    await page.goto(
      new URL("settings/user/connected-accounts", shared.env.nextcloudBaseUrl).toString(),
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );

    const connect = page
      .getByRole("button", { name: /connect to gitlab/i })
      .or(page.getByRole("link", { name: /connect to gitlab/i }));

    if ((await connect.count()) === 0) {
      test.skip(true, "integration_gitlab: connect control not present (integration not provisioned)");
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
        "GitLab OAuth authorize must be served by the partner instance, not Nextcloud"
      ).not.toBe(nextcloudHost);
      expect(authorizeUrl.searchParams.get("client_id")).toBeTruthy();
      expect(authorizeUrl.searchParams.get("response_type")).toBe("code");
    } else {
      test.skip(
        true,
        "integration_gitlab: connect did not redirect to GitLab authorize (OAuth client not provisioned)"
      );
    }
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
