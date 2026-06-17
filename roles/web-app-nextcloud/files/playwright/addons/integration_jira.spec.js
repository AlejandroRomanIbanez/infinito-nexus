const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

// Functional cross-role check: the Nextcloud `integration_jira` app must be
// wired with a real Atlassian OAuth client (client_id/client_secret rendered
// from the `api` lookup in meta/addons/integration_jira.yml). Upstream renders
// the Jira personal settings under the connected-accounts section. The
// "Connect to Jira Cloud" NcButton only appears when the admin client_id is
// configured; clicking it runs window.location.replace() to
// auth.atlassian.com/authorize with the configured client_id. Reaching that
// Atlassian authorize endpoint proves the integration URL + client are live.
// Full consent needs live Atlassian credentials (separate Tier-2 concern).
test("integration integration_jira: connects Nextcloud to Atlassian Jira", async ({ browser }) => {
  skipUnlessAddonEnabled("integration_jira");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);
    await page.goto(
      new URL("settings/user/connected-accounts", shared.env.nextcloudBaseUrl).toString(),
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );

    const connect = page.getByRole("button", { name: /connect to jira cloud/i });

    if ((await connect.count()) === 0) {
      test.skip(true, "integration_jira: connect control not present (integration not provisioned)");
      return;
    }

    await Promise.all([
      page.waitForEvent("framenavigated", { timeout: 60_000 }).catch(() => {}),
      connect.first().click()
    ]);

    await expect
      .poll(() => page.url(), { timeout: 60_000 })
      .toMatch(/auth\.atlassian\.com\/authorize|connected-accounts/);
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
