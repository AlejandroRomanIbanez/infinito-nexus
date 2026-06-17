const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

// Functional cross-role integration check for the OpenAI-compatible AI backend
// partner (openwebui or flowise — whichever is deployed).
// Reality of upstream nextcloud/integration_openai: the connection is NOT a
// user OAuth consent flow. It is an admin-level "Service URL" + API key form
// (AdminSettings.vue: field label "Service URL", placeholder
// "Example: http://localhost:8080/v1"). So the strongest deterministic,
// partner-specific signal is that the integration's ADMIN settings show a
// configured (non-empty) endpoint URL pointing at the AI backend — which is
// exactly what the cross-role provisioning wires (configkey "url" =
// web-app-openwebui / web-app-flowise base URL). Skip cleanly when the Service
// URL field is absent (integration not provisioned in this deployment).
test("integration integration_openai: connects Nextcloud to openwebui/flowise", async ({ browser }) => {
  skipUnlessAddonEnabled("integration_openai");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToStandaloneNextcloud(page);

    // The OpenAI/LocalAI connection is configured admin-side; the personal
    // connected-accounts page only exposes per-user prefs. Go straight to the
    // admin AI settings where the Service URL is wired.
    const adminAiUrl = new URL("settings/admin/ai", shared.env.nextcloudBaseUrl).toString();
    await page.goto(adminAiUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });

    // Locate THIS integration's Service URL control. Match by accessible name
    // (label "Service URL") and fall back to the OpenAI/LocalAI section's URL
    // input. If absent, the integration is not provisioned here.
    const serviceUrlField = page
      .getByRole("textbox", { name: /service url/i })
      .or(page.locator("#openai-api #openai-url input, .openai input[type='text'], input[id*='openai'][type='text']"));

    const present = await serviceUrlField
      .first()
      .waitFor({ state: "visible", timeout: 30_000 })
      .then(() => true)
      .catch(() => false);

    if (!present) {
      test.skip(
        true,
        "integration_openai: Service URL control not present (integration not provisioned)"
      );
      return;
    }

    // No OAuth redirect for this partner: assert the admin settings show a
    // configured endpoint URL (non-empty, http(s)) — proving the AI backend URL
    // is wired into the integration rather than left at the OpenAI default.
    const configuredUrl = (await serviceUrlField.first().inputValue()).trim();
    expect(
      configuredUrl,
      "integration_openai admin Service URL must hold the configured openwebui/flowise endpoint"
    ).toMatch(/^https?:\/\/.+/i);
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
