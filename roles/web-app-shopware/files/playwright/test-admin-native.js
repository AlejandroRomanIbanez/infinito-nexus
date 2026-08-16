const { test, expect } = require("@playwright/test");
const { resolveTimeout } = require("./timeouts");

const { decodeDotenvQuotedValue, normalizeBaseUrl , gotoOnion } = require("./personas");
const { performKeycloakLogin } = require("./personas/utils/keycloak");

const appBaseUrl = normalizeBaseUrl(process.env.APP_BASE_URL || "");
const adminUsername = decodeDotenvQuotedValue(process.env.ADMIN_USERNAME || "");
const adminPassword = decodeDotenvQuotedValue(process.env.ADMIN_PASSWORD || "");
const canonicalDomain = decodeDotenvQuotedValue(process.env.CANONICAL_DOMAIN || "");
const ssoEnabled = (process.env.SSO_SERVICE_ENABLED || "").toLowerCase() === "true";

test("administrator: admin login → catalogue → in-app logout", async ({ page }) => {
  test.setTimeout(resolveTimeout(180_000));

  expect(adminUsername, "ADMIN_USERNAME must be set").toBeTruthy();
  expect(adminPassword, "ADMIN_PASSWORD must be set").toBeTruthy();

  await page.context().clearCookies();
  await gotoOnion(page, `${appBaseUrl}/admin`, { waitUntil: "domcontentloaded" });

  if (ssoEnabled) {
    expect(canonicalDomain, "CANONICAL_DOMAIN must be set").toBeTruthy();

    const ssoButton = page
      .locator("a.heptacom-admin-open-auth--button")
      .filter({ hasText: /keycloak/i })
      .first();
    await expect(
      ssoButton,
      "AdminOpenAuth appends its provider link into .sw-login__content; a missing link means the plugin is inactive or the client row is not active",
    ).toBeVisible({ timeout: resolveTimeout(60_000) });

    await ssoButton.click();
    await performKeycloakLogin(page, adminUsername, adminPassword, canonicalDomain);
  } else {
    const password = page.locator("input[type='password']:visible").first();
    await expect(
      password,
      "the administration SPA must paint its login form; a blank shell here means the admin bundle never booted",
    ).toBeVisible({ timeout: resolveTimeout(60_000) });

    await page.locator("input[name$='username']:visible").first().fill(adminUsername);
    await password.fill(adminPassword);
    await password.press("Enter");
  }

  const userActions = page.locator(".sw-admin-menu__user-actions-toggle");
  await expect(
    userActions,
    "the admin menu must render after login; still on the login form means the credentials were rejected",
  ).toBeVisible({ timeout: resolveTimeout(60_000) });

  await expect(page.locator("body")).toContainText(/dashboard|catalogue|catalog|order|product/i, {
    timeout: resolveTimeout(60_000),
  });

  const wizard = page.locator(".sw-first-run-wizard-modal");
  const wizardShown = await wizard
    .waitFor({ state: "visible", timeout: resolveTimeout(15_000) })
    .then(() => true)
    .catch(() => false);
  if (wizardShown) {
    await gotoOnion(page, `${appBaseUrl}/admin#/sw/dashboard/index`);
    await expect(
      wizard,
      "the first-run wizard renders :closable=false on its first step, so leaving its route is the only exit",
    ).toBeHidden({ timeout: resolveTimeout(30_000) });
  }

  await userActions.click();
  const logout = page.locator(".sw-admin-menu__logout-action");
  await expect(logout, "Shopware's logout lives behind the user-actions toggle").toBeVisible({
    timeout: resolveTimeout(15_000),
  });
  await logout.click();

  await expect(
    page.locator("input[type='password']:visible").first(),
    "after logout the administration must fall back to its login form",
  ).toBeVisible({ timeout: resolveTimeout(60_000) });
});
