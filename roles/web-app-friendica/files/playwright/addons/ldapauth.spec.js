const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const { skipUnlessServiceEnabled } = require("../service-gating");
const shared = require("../_shared");

// ldapauth is Friendica's LDAP authentication addon: it has no dedicated
// in-app page. Its observable surface is that the role's existing LDAP
// login idiom succeeds and lands the administrator on an authenticated
// Friendica surface. We REUSE that idiom rather than reimplement LDAP
// mechanics, and gate behind both the addon flag and the ldap service.
test("addon ldapauth: LDAP login lands the administrator on an authenticated surface", async ({ browser }) => {
  skipUnlessAddonEnabled("ldapauth");
  skipUnlessServiceEnabled("ldap");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    const login = shared.pickLoginPath();
    await login(page, shared.env.adminUsername, shared.env.adminPassword);

    await page
      .goto(`${shared.trimmedBaseUrl()}/network`, { waitUntil: "domcontentloaded" })
      .catch(() => {});

    const authenticatedSurface = page
      .locator("#topbar-first, #navbar-apps-menu, a[href*='/logout']")
      .first();
    await expect(
      authenticatedSurface,
      "Expected an authenticated Friendica surface after the ldapauth-backed login"
    ).toBeVisible({ timeout: 60_000 });

    await shared.friendicaLogout(page);
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
