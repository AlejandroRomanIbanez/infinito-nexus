const { test, expect } = require("@playwright/test");

// Baseline smoke test: WebAdmin is served under the canonical domain with TLS.
test.use({ ignoreHTTPSErrors: true });

function decodeDotenvQuotedValue(value) {
  if (typeof value !== "string") return "";
  const trimmed = value.trim();
  if (trimmed.length >= 2 && trimmed.startsWith('"') && trimmed.endsWith('"')) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

const appBaseUrl = decodeDotenvQuotedValue(process.env.APP_BASE_URL || "").replace(/\/+$/, "");
const canonicalDomain = decodeDotenvQuotedValue(process.env.CANONICAL_DOMAIN || "");

test.beforeEach(async ({ page }) => {
  expect(appBaseUrl, "APP_BASE_URL must be set").toBeTruthy();
  expect(canonicalDomain, "CANONICAL_DOMAIN must be set").toBeTruthy();
  await page.context().clearCookies();
});

test("Stalwart WebAdmin is served under canonical domain with TLS", async ({ page }) => {
  const response = await page.goto(`${appBaseUrl}/`);
  expect(response, "Expected Stalwart response").toBeTruthy();
  expect(response.status(), "Expected Stalwart front page status < 400").toBeLessThan(400);
  expect(
    response.url().includes(canonicalDomain),
    `Expected canonical domain "${canonicalDomain}" to back the Stalwart URL`
  ).toBe(true);
  const headers = response.headers();
  expect(headers["strict-transport-security"], "Stalwart must emit HSTS").toBeTruthy();
});
