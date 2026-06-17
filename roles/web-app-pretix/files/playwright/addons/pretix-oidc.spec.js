const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const { skipUnlessServiceEnabled } = require("../service-gating");
const { runAdminFlow } = require("../personas");

// pretix-oidc is Pretix's OIDC SSO plugin: it has no dedicated in-app
// user page. Its observable surface is that the role's existing admin
// OIDC login idiom (runAdminFlow → Keycloak round-trip → authenticated
// Pretix) succeeds. We REUSE that idiom rather than reimplement OIDC
// mechanics, gating behind the addon flag and the sso service.
test.use({ ignoreHTTPSErrors: true });

test("addon pretix-oidc: administrator OIDC login round-trip succeeds", async ({ page }) => {
  skipUnlessAddonEnabled("pretix-oidc");
  skipUnlessServiceEnabled("sso");

  await runAdminFlow(page, {
    adminInteraction: async (interactivePage) => {
      const link = interactivePage
        .getByRole("link", { name: /^(events|orders|control|admin)$/i })
        .first();
      if (await link.isVisible({ timeout: 10_000 }).catch(() => false)) {
        await link.click().catch(() => {});
        await interactivePage
          .waitForLoadState("domcontentloaded", { timeout: 30_000 })
          .catch(() => {});
        await expect(interactivePage.locator("body")).toContainText(
          /event|order|ticket|control|pretix/i,
          { timeout: 30_000 }
        );
      }
    },
  });
});
