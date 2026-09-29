/**
 * Keycloak user provisioning through the admin console.
 *
 *   `MAPACHE`
 *     The OIDC-only persona: a person the administrator onboards in Keycloak
 *     after the deploy, whom no application pre-provisions. Keycloak's spec
 *     provisions it once; consumers prove they create the account on first
 *     OIDC login.
 *
 *   `mapachePassword(secret)`
 *     The password mapache carries, derived from the generated
 *     `secrets.credentials.mapache_password` both specs receive, so the
 *     provisioning spec and every consumer compute the same value.
 *
 *     Args:
 *       secret: the rendered credential (64 hex characters).
 *
 *     Returns: the credential extended to satisfy the realm password policy.
 *
 *   `provisionKeycloakUser(browser, options)`
 *     Signs the master-realm administrator into the admin console, creates
 *     `options.user` in `options.realm` when it is missing, and sets
 *     `options.password` as its permanent password either way: the matrix
 *     rotates every credential between its two passes, so an existing user
 *     must take the current value.
 *
 *     Args:
 *       browser: Playwright `Browser`; the flow runs in its own context.
 *       options.baseUrl: Keycloak base URL (no trailing slash).
 *       options.realm: realm the user belongs to.
 *       options.adminUsername / options.adminPassword: master-realm admin.
 *       options.user: `{ username, firstName, lastName, email }`.
 *       options.password: password to set on the user.
 */

const { expect } = require("@playwright/test");
const { resolveTimeout } = require("../../timeouts");
const { performKeycloakLoginForm } = require("./keycloak");
const { gotoOnion } = require("./env");

const MAPACHE = {
  username: "mapache",
  firstName: "Infinito",
  lastName: "Mapache",
};

function mapachePassword(secret) {
  return `${secret}Aa1!`;
}

async function openUser(page, username) {
  const search = page.getByPlaceholder(/search user/i).first();
  await search.waitFor({ state: "visible", timeout: resolveTimeout(60_000) });
  await search.fill(username);
  await search.press("Enter");
  const link = page.getByRole("link", { name: username, exact: true }).first();
  const exists = await link
    .waitFor({ state: "visible", timeout: resolveTimeout(10_000) })
    .then(() => true)
    .catch(() => false);
  if (exists) {
    await link.click({ timeout: resolveTimeout(30_000) });
  }
  return exists;
}

async function createUser(page, user) {
  await page
    .getByRole("button", { name: /add user|create new user/i })
    .or(page.getByRole("link", { name: /add user|create new user/i }))
    .first()
    .click({ timeout: resolveTimeout(30_000) });
  await page.getByLabel(/^username/i).first().fill(user.username);
  await page.getByLabel(/^email$/i).first().fill(user.email);
  await page.getByLabel(/^first name/i).first().fill(user.firstName);
  await page.getByLabel(/^last name/i).first().fill(user.lastName);
  await page.getByRole("button", { name: /^create$/i }).click({ timeout: resolveTimeout(30_000) });
  await expect(
    page.getByText(/the user has been created/i).first(),
    `Keycloak must confirm that ${user.username} was created`,
  ).toBeVisible({ timeout: resolveTimeout(60_000) });
}

async function setPassword(page, username, password) {
  await page.getByRole("tab", { name: /credentials/i }).click({ timeout: resolveTimeout(30_000) });
  await page
    .getByRole("button", { name: /^(set|reset) password$/i })
    .first()
    .click({ timeout: resolveTimeout(30_000) });
  const dialog = page.getByRole("dialog");
  const passwordFields = dialog.locator("input[type='password']");
  await passwordFields.first().waitFor({ state: "visible", timeout: resolveTimeout(30_000) });
  await passwordFields.nth(0).fill(password);
  await passwordFields.nth(1).fill(password);
  await dialog
    .locator("input[type='checkbox']")
    .first()
    .setChecked(false, { force: true, timeout: resolveTimeout(30_000) });
  await dialog.getByRole("button", { name: /^save$/i }).click({ timeout: resolveTimeout(30_000) });
  const confirm = page.getByRole("dialog").getByRole("button", { name: /^(save|reset) password$/i });
  const confirmShown = await confirm
    .waitFor({ state: "visible", timeout: resolveTimeout(5_000) })
    .then(() => true)
    .catch(() => false);
  if (confirmShown) {
    await confirm.click({ timeout: resolveTimeout(30_000) });
  }
  await expect(
    page.getByText(/password has been (set|reset) successfully/i).first(),
    `Keycloak must confirm the new password of ${username}`,
  ).toBeVisible({ timeout: resolveTimeout(60_000) });
}

async function provisionKeycloakUser(browser, options) {
  const { baseUrl, realm, adminUsername, adminPassword, user, password } = options;
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();
  try {
    await gotoOnion(page, `${baseUrl}/admin/master/console/#/${realm}/users`);
    await performKeycloakLoginForm(page, adminUsername, adminPassword);
    if (!(await openUser(page, user.username))) {
      await createUser(page, user);
    }
    await setPassword(page, user.username, password);
    await page
      .goto(`${baseUrl}/realms/master/protocol/openid-connect/logout`, { waitUntil: "commit" })
      .catch(() => {});
  } finally {
    await context.close();
  }
}

module.exports = {
  MAPACHE,
  mapachePassword,
  provisionKeycloakUser,
};
