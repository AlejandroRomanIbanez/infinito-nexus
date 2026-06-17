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

test("OpenIDConnect: SSO login reaches an authenticated MediaWiki surface", async ({ page }) => {
  skipUnlessAddonEnabled("OpenIDConnect");
  skipUnlessServiceEnabled("sso");

  expect(appBaseUrl, "APP_BASE_URL must be set").toBeTruthy();
  expect(canonicalDomain, "CANONICAL_DOMAIN must be set").toBeTruthy();

  await page.context().clearCookies();

  await runAdminFlow(page, {
    adminInteraction: async (interactivePage) => {
      await expect(interactivePage.locator("body")).toContainText(
        /wiki|edit|page|main page|history|mediawiki|logout|profile/i,
        { timeout: 60_000 },
      );
    },
  });
});
