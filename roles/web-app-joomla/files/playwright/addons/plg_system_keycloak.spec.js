const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const { skipUnlessServiceEnabled } = require("../service-gating");
const {
  decodeDotenvQuotedValue,
  normalizeBaseUrl,
  performKeycloakLoginForm,
} = require("../personas");

// plg_system_keycloak is Joomla's native OIDC SSO plugin: it has no
// dedicated in-app user page. Its observable surface is that visiting the
// site root while gated by the plugin redirects to Keycloak, and after the
// Keycloak login the browser lands back on Joomla authenticated. We REUSE
// the role's OIDC login idiom (see test-oidc-login.js) rather than
// reimplement OIDC mechanics, gating behind the addon flag and sso service.
const joomlaBaseUrl = normalizeBaseUrl(process.env.JOOMLA_BASE_URL || "");
const oidcIssuerUrl = normalizeBaseUrl(process.env.OIDC_ISSUER_URL || "");
const adminUsername = decodeDotenvQuotedValue(process.env.ADMIN_USERNAME);
const adminPassword = decodeDotenvQuotedValue(process.env.ADMIN_PASSWORD);

test.use({ ignoreHTTPSErrors: true });

test("addon plg_system_keycloak: OIDC redirect to Keycloak and back logs the administrator into Joomla", async ({ page }) => {
  skipUnlessAddonEnabled("plg_system_keycloak");
  skipUnlessServiceEnabled("sso");

  expect(joomlaBaseUrl, "JOOMLA_BASE_URL must be set").toBeTruthy();
  expect(adminUsername, "ADMIN_USERNAME must be set").toBeTruthy();
  expect(adminPassword, "ADMIN_PASSWORD must be set").toBeTruthy();
  expect(oidcIssuerUrl, "OIDC_ISSUER_URL must be set when OIDC is enabled").toBeTruthy();

  await page.context().clearCookies();

  const expectedOidcAuthUrl = `${oidcIssuerUrl}/protocol/openid-connect/auth`;
  const expectedJoomlaBaseUrl = joomlaBaseUrl.replace(/\/$/, "");

  await page.goto(`${expectedJoomlaBaseUrl}/`);

  await expect
    .poll(() => page.url(), {
      timeout: 60_000,
      message: `expected redirect to Keycloak OIDC auth (${expectedOidcAuthUrl})`,
    })
    .toContain(expectedOidcAuthUrl);

  await performKeycloakLoginForm(page, adminUsername, adminPassword);

  await expect
    .poll(() => page.url(), {
      timeout: 60_000,
      message: `expected redirect back to Joomla at ${expectedJoomlaBaseUrl}`,
    })
    .toContain(expectedJoomlaBaseUrl);

  await expect(
    page.locator("body"),
    "Expected the Joomla front-end to render after the plg_system_keycloak OIDC handshake"
  ).toBeVisible({ timeout: 60_000 });
});
