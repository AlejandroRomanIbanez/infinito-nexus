const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const { skipUnlessServiceEnabled } = require("../service-gating");
const shared = require("../_shared");

// infinito-oidc-rbac-mapper is a vendored mu-plugin: it maps Keycloak
// `groups` claims to WordPress roles at OIDC login time and has no
// dedicated configuration page. Its observable browser surface is the
// wp-admin users list, where mapped roles are rendered in the Role
// column (the full mapping correctness is exercised end-to-end by
// test-rbac-roles.js). We log in as administrator via the role's OIDC
// idiom and assert that the role-bearing users surface renders, gating
// behind the addon flag plus the sso and ldap services that supply the
// group claims.
test("addon infinito-oidc-rbac-mapper: wp-admin users list exposes the role-mapping surface", async ({ browser }) => {
  skipUnlessAddonEnabled("infinito-oidc-rbac-mapper");
  skipUnlessServiceEnabled("sso");
  skipUnlessServiceEnabled("ldap");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.wpAdminLoginViaOidc(
      page,
      shared.env.wpBaseUrl,
      shared.env.adminUsername,
      shared.env.adminPassword
    );

    await page.goto(`${shared.env.wpBaseUrl}/wp-admin/users.php`, {
      waitUntil: "domcontentloaded",
      timeout: 60_000,
    });

    const roleSurface = page
      .locator("#the-list tr, table.users th#role, #wpbody-content .wrap")
      .first();
    await expect(
      roleSurface,
      "Expected the wp-admin users list (RBAC role-mapping surface) to render"
    ).toBeVisible({ timeout: 30_000 });
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
