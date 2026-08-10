const { test, expect } = require("@playwright/test");

const { decodeDotenvQuotedValue, normalizeBaseUrl } = require("./personas");
const { performKeycloakLoginForm } = require("./personas/utils/keycloak");

const appBaseUrl = normalizeBaseUrl(process.env.APP_BASE_URL || "");
const canonicalDomain = decodeDotenvQuotedValue(process.env.CANONICAL_DOMAIN || "");
const ldapEnabled = (process.env.LDAP_SERVICE_ENABLED || "").toLowerCase() === "true";
const ssoEnabled = (process.env.SSO_SERVICE_ENABLED || "").toLowerCase() === "true";

const PERSONAS = [
  {
    label: "biber",
    username: decodeDotenvQuotedValue(process.env.BIBER_USERNAME || ""),
    password: decodeDotenvQuotedValue(process.env.BIBER_PASSWORD || ""),
  },
  {
    label: "administrator",
    username: decodeDotenvQuotedValue(process.env.ADMIN_USERNAME || ""),
    password: decodeDotenvQuotedValue(process.env.ADMIN_PASSWORD || ""),
  },
];

const signInAffordance = (page) => page.getByText(/^\s*(log\s?in|sign\s?in)\s*$/i).first();

for (const persona of PERSONAS) {
  test(`${persona.label}: native sign-in → authenticated surface → sign-out`, async ({ page }) => {
    test.skip(
      !ldapEnabled,
      "LDAP_SERVICE_ENABLED=false: tasks/main.yml provisions no local Funkwhale account, so no persona can sign in.",
    );
    test.setTimeout(180_000);

    expect(persona.username, `${persona.label} username must be set`).toBeTruthy();
    expect(persona.password, `${persona.label} password must be set`).toBeTruthy();

    await page.context().clearCookies();
    await page.goto(`${appBaseUrl}/login`, { waitUntil: "domcontentloaded" });

    if (ssoEnabled) {
      await expect
        .poll(() => page.url(), {
          timeout: 60_000,
          message: "the oauth2 ACL protects /login, so the proxy must hand the persona to Keycloak",
        })
        .not.toContain(canonicalDomain);
      await performKeycloakLoginForm(page, persona.username, persona.password);
      await expect
        .poll(() => page.url(), {
          timeout: 60_000,
          message: `the oauth2 proxy gates /login, so Keycloak must hand back to ${canonicalDomain}`,
        })
        .toContain(canonicalDomain);
    }

    const password = page.locator("input[type='password']:visible").first();
    await expect(
      password,
      "Funkwhale serves its own sign-in form on /login; the proxy only gates the route, it does not create an application session",
    ).toBeVisible({ timeout: 60_000 });

    await page
      .locator("input[type='text']:visible, input[type='email']:visible")
      .first()
      .fill(persona.username);
    await password.fill(persona.password);
    await password.press("Enter");

    await expect(
      signInAffordance(page),
      `the sidebar must stop offering sign-in once ${persona.label} holds a Funkwhale session`,
    ).toBeHidden({ timeout: 60_000 });

    await expect(page.locator("body")).toContainText(/library|playlist|artist|album|track|channel/i, {
      timeout: 60_000,
    });

    const signOut = page
      .getByRole("link", { name: /log\s?out|sign\s?out/i })
      .or(page.getByRole("button", { name: /log\s?out|sign\s?out/i }))
      .first();
    const signOutReachable = await signOut
      .waitFor({ state: "visible", timeout: 10_000 })
      .then(() => true)
      .catch(() => false);
    if (signOutReachable) {
      await signOut.click();
    } else {
      await page.goto(`${appBaseUrl}/logout`, { waitUntil: "domcontentloaded" });
    }

    await expect(
      signInAffordance(page),
      `after sign-out Funkwhale must offer sign-in to ${persona.label} again`,
    ).toBeVisible({ timeout: 60_000 });
  });
}
