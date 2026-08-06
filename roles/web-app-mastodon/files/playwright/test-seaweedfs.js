// SeaweedFS object-store scenario for Mastodon.
//
// templates/env.j2 renders S3_ENABLED / S3_BUCKET / S3_ENDPOINT whenever the
// role's objstore is enabled, so Paperclip writes every attachment straight to
// the consumer bucket instead of public/system. The action signs the
// administrator in through Keycloak (OMNIAUTH_ONLY=true, so /auth/sign_in
// redirects into the OIDC chain) and saves a new avatar on /settings/profile;
// the avatar derivatives land as fresh bucket objects and the shared check
// proves the bucket grew via the Filer UI.
//
// Required env (rendered by templates/playwright.env.j2):
//   APP_BASE_URL, CANONICAL_DOMAIN, ADMIN_USERNAME, ADMIN_PASSWORD and the
//   SEAWEEDFS_* keys consumed by runSeaweedfsStorageCheck.

const { test, expect } = require("@playwright/test");
const { skipUnlessServiceEnabled } = require("./service-gating");
const { normalizeUrl, readEnv, performKeycloakLogin, runSeaweedfsStorageCheck } = require("./personas");

const AVATAR_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);

test.use({ ignoreHTTPSErrors: true });

test("seaweedfs: a saved Mastodon avatar is stored in the SeaweedFS bucket", async ({ page, browser }) => {
  skipUnlessServiceEnabled("seaweedfs");
  test.skip(
    (process.env.PERSONA_ADMINISTRATOR_BLOCKED || "").toLowerCase() === "true",
    "administrator persona is blocked by the role contract (PERSONA_ADMINISTRATOR_BLOCKED=true); this scenario drives the same admin journey.",
  );
  test.setTimeout(300_000);

  const appBaseUrl = normalizeUrl(process.env.APP_BASE_URL);
  const canonicalDomain = readEnv("CANONICAL_DOMAIN");
  const adminUsername = readEnv("ADMIN_USERNAME");
  const adminPassword = readEnv("ADMIN_PASSWORD");

  await runSeaweedfsStorageCheck(page, browser, {
    label: "a Mastodon profile avatar upload",
    action: async (appPage) => {
      const base = appBaseUrl.replace(/\/$/, "");
      await appPage.goto(`${base}/auth/sign_in`, { waitUntil: "domcontentloaded" });
      if (appPage.url().includes("openid-connect/auth")) {
        await performKeycloakLogin(appPage, adminUsername, adminPassword, canonicalDomain);
      }

      await appPage.goto(`${base}/settings/profile`, { waitUntil: "domcontentloaded" });

      const fileInput = appPage
        .locator('input#account_avatar, input[type="file"][name*="avatar" i], input[type="file"]')
        .first();
      await expect(
        fileInput,
        "the Mastodon profile settings page must expose an avatar file input",
      ).toBeAttached({ timeout: 60_000 });

      await fileInput.setInputFiles({
        name: `infinito-storage-check-${Date.now()}.png`,
        mimeType: "image/png",
        buffer: AVATAR_PNG,
      });

      await appPage
        .getByRole("button", { name: /save changes|save|speichern/i })
        .or(appPage.locator('button[type="submit"], input[type="submit"]'))
        .first()
        .click();
      await appPage.waitForLoadState("networkidle", { timeout: 60_000 }).catch(() => {});
    },
  });
});
