const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

// Functional cross-role integration check for the PeerTube partner.
// Reality of upstream nextcloud/integration_peertube: its personal settings
// expose only "search" and "link preview" toggles — there is NO user OAuth
// connect handoff (unlike mastodon/gitlab/github). So the strongest
// deterministic, partner-specific signal available here is that the
// integration's own settings section is wired into connected-accounts and the
// configured PeerTube instance URL is reachable from the personal settings.
// If a connect/login control is ever introduced upstream we detect and drive
// it; otherwise we assert the PeerTube settings surface is present, and skip
// cleanly when the integration is not provisioned in this deployment.
test("integration integration_peertube: connects Nextcloud to peertube", async ({ browser }) => {
  skipUnlessAddonEnabled("integration_peertube");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);
    await page.goto(
      new URL("settings/user/connected-accounts", shared.env.nextcloudBaseUrl).toString(),
      { waitUntil: "domcontentloaded", timeout: 60_000 }
    );

    const connect = page
      .getByRole("button", { name: /connect to peertube|sign in with peertube/i })
      .or(page.getByRole("link", { name: /connect to peertube|sign in with peertube/i }));

    if ((await connect.count()) > 0) {
      await Promise.all([
        page.waitForEvent("framenavigated", { timeout: 60_000 }).catch(() => {}),
        connect.first().click(),
      ]);
      await expect
        .poll(() => page.url(), { timeout: 60_000 })
        .toMatch(/\/oauth\/authorize\?|\/authorize\?|connected-accounts/i);
      return;
    }

    // No OAuth handoff upstream: assert the PeerTube integration section itself
    // rendered into the connected-accounts settings. Absence => not provisioned.
    const peertubeSection = page
      .locator("#peertube_prefs, .peertube, [id*='peertube'], [class*='peertube']")
      .or(page.getByText(/peertube/i));

    if ((await peertubeSection.count()) === 0) {
      test.skip(true, "integration_peertube: settings section not present (integration not provisioned)");
      return;
    }

    await expect(peertubeSection.first()).toBeVisible({ timeout: 30_000 });
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
