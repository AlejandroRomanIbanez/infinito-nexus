const { test, expect } = require("@playwright/test");

const { skipUnlessAddonEnabled } = require("../addon-gating");
const { skipUnlessServiceEnabled } = require("../service-gating");
const {
  decodeDotenvQuotedValue,
  normalizeBaseUrl,
  runAdminFlow,
} = require("../personas");

test.use({ ignoreHTTPSErrors: true });

const appBaseUrl = normalizeBaseUrl(process.env.APP_BASE_URL || "");
const canonicalDomain = decodeDotenvQuotedValue(process.env.CANONICAL_DOMAIN || "");

test("ldap-authenticator: LDAP-backed login reaches an authenticated XWiki surface", async ({ page }) => {
  skipUnlessAddonEnabled("ldap-authenticator");
  skipUnlessServiceEnabled("ldap");

  expect(appBaseUrl, "APP_BASE_URL must be set").toBeTruthy();
  expect(canonicalDomain, "CANONICAL_DOMAIN must be set").toBeTruthy();

  await page.context().clearCookies();

  await runAdminFlow(page, {
    adminInteraction: async (interactivePage) => {
      await expect(interactivePage.locator("body")).toContainText(
        /wiki|edit|page|administration|xwiki|logout|profile/i,
        { timeout: 60_000 },
      );
    },
  });
});
