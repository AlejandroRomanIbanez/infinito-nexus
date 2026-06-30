const { test, expect } = require("@playwright/test");

const {
  decodeDotenvQuotedValue,
  performKeycloakLoginForm,
  runAdminFlow,
  runBiberFlow,
  runGuestFlow,
  safeSkipUnlessEnabled,
} = require("./personas");

// Stalwart e2e — mirrors web-app-mailu's scenario set:
//   smoke (WebAdmin TLS), SSO login -> admin -> logout, biber -> administrator
//   send/receive (via Roundcube webmail), plus the shared guest/biber/admin
//   persona flows. SSO scenarios run only when the OIDC chain is wired
//   (SSO_SERVICE_ENABLED); the persona flows are gated by PERSONA_*_BLOCKED in
//   templates/playwright.env.j2 (see TODO.md).
test.use({ ignoreHTTPSErrors: true });

const appBaseUrl = decodeDotenvQuotedValue(process.env.APP_BASE_URL || "").replace(/\/+$/, "");
const webmailBaseUrl = decodeDotenvQuotedValue(process.env.WEBMAIL_BASE_URL || "").replace(/\/+$/, "");
const canonicalDomain = decodeDotenvQuotedValue(process.env.CANONICAL_DOMAIN || "");
const oidcIssuerUrl = decodeDotenvQuotedValue(process.env.OIDC_ISSUER_URL || "");
const adminEmail = decodeDotenvQuotedValue(process.env.ADMIN_EMAIL || "");
const adminUsername = decodeDotenvQuotedValue(process.env.ADMIN_USERNAME || "");
const adminPassword = decodeDotenvQuotedValue(process.env.ADMIN_PASSWORD || "");
const biberEmail = decodeDotenvQuotedValue(process.env.BIBER_EMAIL || "");
const biberUsername = decodeDotenvQuotedValue(process.env.BIBER_USERNAME || "");
const biberPassword = decodeDotenvQuotedValue(process.env.BIBER_PASSWORD || "");

async function roundcubeLogin(page, user, pass) {
  await page.goto(`${webmailBaseUrl}/`);
  const userField = page.locator("#rcmloginuser, input[name='_user']").first();
  await userField.waitFor({ state: "visible", timeout: 30_000 });
  await userField.fill(user);
  await page.locator("#rcmloginpwd, input[name='_pass']").first().fill(pass);
  await page.locator("#rcmloginsubmit, button[type='submit'], input[type='submit']").first().click();
  await page.locator("#messagelist, .compose, a[href*='_action=compose'], .toolbar").first()
    .waitFor({ state: "visible", timeout: 30_000 });
}

async function roundcubeLogout(page) {
  const logout = page.locator("a[href*='_task=logout'], a[href*='logout'], a.logout")
    .or(page.getByRole("link", { name: /logout|sign out/i }));
  if (await logout.first().isVisible({ timeout: 5_000 }).catch(() => false)) {
    await logout.first().click();
  }
}

async function waitForEmailInInbox(page, subjectText, timeout = 60_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const row = page.locator("#messagelist tbody tr, table.messagelist tbody tr").filter({ hasText: subjectText });
    if (await row.first().isVisible().catch(() => false)) return row.first();
    await page.getByRole("link", { name: "Inbox" }).first().click().catch(() => {});
    await page.waitForTimeout(3_000);
  }
  throw new Error(`Timed out waiting for email with subject "${subjectText}"`);
}

test.beforeEach(() => {
  expect(appBaseUrl, "APP_BASE_URL must be set").toBeTruthy();
  expect(canonicalDomain, "CANONICAL_DOMAIN must be set").toBeTruthy();
});

// Baseline: WebAdmin is served on the canonical domain with TLS.
test("stalwart: WebAdmin is served under canonical domain with TLS", async ({ page }) => {
  const response = await page.goto(`${appBaseUrl}/`);
  expect(response, "Expected Stalwart response").toBeTruthy();
  expect(response.status(), "Expected status < 400").toBeLessThan(400);
  expect(response.url().includes(canonicalDomain), `Expected canonical domain "${canonicalDomain}"`).toBe(true);
  expect(response.headers()["strict-transport-security"], "Stalwart must emit HSTS").toBeTruthy();
});

// Scenario I: SSO login -> WebAdmin -> logout (runs once the OIDC chain is wired).
test("stalwart: sso login, open WebAdmin, logout", async ({ page }) => {
  safeSkipUnlessEnabled("sso");
  const expectedOidcAuthUrl = `${oidcIssuerUrl.replace(/\/$/, "")}/protocol/openid-connect/auth`;

  await page.goto(`${appBaseUrl}/`);
  const ssoLink = page.locator("a[href*='openid-connect/auth'], a[href*='/auth/oauth'], button:has-text('OpenID')").first();
  if (await ssoLink.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await ssoLink.click();
  }
  await expect.poll(() => page.url(), { timeout: 60_000 }).toContain(expectedOidcAuthUrl);
  await performKeycloakLoginForm(page, adminUsername, adminPassword);
  await expect.poll(() => page.url(), { timeout: 60_000 }).toContain(canonicalDomain);

  // WebAdmin chrome confirms the authenticated admin session.
  await expect(
    page.locator("nav, .sidebar, [class*='menu'], h1, h2").filter({ hasText: /dashboard|domains|account|settings|directory/i }).first()
  ).toBeVisible({ timeout: 30_000 });

  const logout = page.locator("a[href*='logout'], button:has-text('Logout')").or(page.getByRole("link", { name: /logout/i }));
  if (await logout.first().isVisible({ timeout: 5_000 }).catch(() => false)) {
    await logout.first().click();
  }
});

// Scenario II: biber -> administrator send/receive through the Roundcube webmail UI.
// biber and the administrator are separate people: isolated browser contexts.
test("stalwart: biber sends to administrator, administrator receives it", async ({ browser }) => {
  test.skip(!webmailBaseUrl || !biberPassword || !adminPassword,
    "Requires WEBMAIL_BASE_URL + provisioned biber/administrator accounts");

  const testSubject = `Playwright stalwart ${Date.now()}`;
  const biberContext = await browser.newContext({ ignoreHTTPSErrors: true });
  const adminContext = await browser.newContext({ ignoreHTTPSErrors: true });

  try {
    const biberPage = await biberContext.newPage();
    await roundcubeLogin(biberPage, biberUsername || biberEmail, biberPassword);
    await biberPage.goto(`${webmailBaseUrl}/?_task=mail&_action=compose`);
    await biberPage.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
    await biberPage.locator("#_to, input[name='_to']").first().fill(adminEmail);
    await biberPage.locator("#compose-subject, input[name='_subject']").first().fill(testSubject);
    await biberPage.locator("#composebody, textarea[name='_message'], [contenteditable='true']").first()
      .fill("Hello Administrator, this is an automated Playwright test email.");
    await biberPage.locator(".formbuttons .send, button.send, a.send").first().click();
    await expect.poll(() => biberPage.url(), { timeout: 30_000 }).not.toContain("_action=compose");
    await roundcubeLogout(biberPage);

    const adminPage = await adminContext.newPage();
    await roundcubeLogin(adminPage, adminUsername || adminEmail, adminPassword);
    await adminPage.getByRole("link", { name: "Inbox" }).first().click().catch(() => {});
    const emailRow = await waitForEmailInInbox(adminPage, testSubject, 60_000);
    await expect(emailRow).toBeVisible();
    await emailRow.click();
    await expect(
      adminPage.locator("#messagecontframe, #mailview-right, .message-part").first()
    ).toBeVisible({ timeout: 15_000 });
    await roundcubeLogout(adminPage);
  } finally {
    await biberContext.close().catch(() => {});
    await adminContext.close().catch(() => {});
  }
});

// Shared persona flows (gated by PERSONA_*_BLOCKED in templates/playwright.env.j2).
test("guest: public-landing → auth chain → never authenticated", async ({ page }) => {
  await runGuestFlow(page);
});

test("biber: app → universal logout", async ({ page }) => {
  await runBiberFlow(page);
});

test("administrator: app → universal logout", async ({ page }) => {
  await runAdminFlow(page, {
    adminInteraction: async (interactivePage) => {
      const link = interactivePage
        .getByRole("link", { name: /^(domains|accounts|directory|settings|dashboard)$/i })
        .first();
      if (await link.isVisible({ timeout: 10_000 }).catch(() => false)) {
        await link.click().catch(() => {});
        await interactivePage.waitForLoadState("domcontentloaded", { timeout: 30_000 }).catch(() => {});
        await expect(interactivePage.locator("body")).toContainText(
          /domains|accounts|directory|settings|dashboard/i,
          { timeout: 30_000 },
        );
      }
    },
  });
});
