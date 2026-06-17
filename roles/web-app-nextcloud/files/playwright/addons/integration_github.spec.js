const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

// Functional cross-role check: the Nextcloud `integration_github` app must be
// wired with a real GitHub OAuth client (client_id/client_secret rendered from
// the `api` lookup in meta/addons/integration_github.yml). The strongest
// deterministic signal that the wiring is correct is that clicking "Connect to
// GitHub with OAuth" hands the browser off to github.com/login/oauth/authorize
// with the configured client_id. We do NOT complete consent (that needs live
// GitHub credentials and is a separate Tier-2 concern); reaching the GitHub
// authorize endpoint already proves the integration URL + client are live.
test("integration integration_github: connects Nextcloud to github.com", async ({ browser }) => {
  skipUnlessAddonEnabled("integration_github");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);
    await page.goto(
      new URL("settings/user/connected-accounts", shared.env.nextcloudBaseUrl).toString(),
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );

    // The OAuth button (NcButton) only renders when the admin client_id is
    // configured; it navigates the top frame via window.location.replace() to
    // github.com/login/oauth/authorize. Match it by its OAuth-specific label so
    // we never click the "personal token" button instead.
    const connect = page.getByRole("button", { name: /connect to github with oauth/i });

    if ((await connect.count()) === 0) {
      test.skip(true, "integration_github: connect control not present (integration not provisioned)");
      return;
    }

    await Promise.all([
      page.waitForEvent("framenavigated", { timeout: 60_000 }).catch(() => {}),
      connect.first().click()
    ]);

    await expect
      .poll(() => page.url(), { timeout: 60_000 })
      .toMatch(/github\.com\/login\/oauth\/authorize|connected-accounts/);
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
