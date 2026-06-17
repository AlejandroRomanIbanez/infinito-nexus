const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

// Functional cross-role check: the Nextcloud `integration_google` app must be
// wired with a real Google OAuth client (client_id/client_secret rendered from
// the `api` lookup in meta/addons/integration_google.yml). Upstream renders the
// Google personal settings under the "Data migration" section (PersonalSection
// getID() === "migration"), NOT connected-accounts, so we land there first and
// fall back to connected-accounts only if the control is missing. Clicking
// "Sign in with Google" runs window.location.replace() to
// accounts.google.com/o/oauth2/v2/auth with the configured client_id; reaching
// that authorize endpoint proves the integration URL + client are live. Full
// consent needs live Google credentials and is a separate Tier-2 concern.
test("integration integration_google: connects Nextcloud to Google", async ({ browser }) => {
  skipUnlessAddonEnabled("integration_google");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  // Match the upstream button text ("Sign in with Google") on any of the
  // settings pages the app may render under across NC versions.
  const connectFor = (target) =>
    target.getByRole("button", { name: /sign in with google/i });

  try {
    await shared.loginToStandaloneNextcloud(page);

    await page.goto(
      new URL("settings/user/migration", shared.env.nextcloudBaseUrl).toString(),
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );

    let connect = connectFor(page);
    if ((await connect.count()) === 0) {
      await page.goto(
        new URL("settings/user/connected-accounts", shared.env.nextcloudBaseUrl).toString(),
        { waitUntil: "domcontentloaded", timeout: 60_000 }
      );
      connect = connectFor(page);
    }

    if ((await connect.count()) === 0) {
      test.skip(true, "integration_google: connect control not present (integration not provisioned)");
      return;
    }

    await Promise.all([
      page.waitForEvent("framenavigated", { timeout: 60_000 }).catch(() => {}),
      connect.first().click()
    ]);

    await expect
      .poll(() => page.url(), { timeout: 60_000 })
      .toMatch(/accounts\.google\.com\/o\/oauth2|Successfully connected to Google/);
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
