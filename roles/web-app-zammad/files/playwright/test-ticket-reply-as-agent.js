const { test, expect, request } = require("@playwright/test");

async function seedTicketViaApi(baseUrl, adminApiUsername, adminApiPassword, subject) {
  const api = await request.newContext({
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: {
      Authorization: `Basic ${Buffer.from(`${adminApiUsername}:${adminApiPassword}`).toString("base64")}`,
      "Content-Type": "application/json",
    },
  });

  const resp = await api.post(`${baseUrl}/api/v1/tickets`, {
    data: {
      title: subject,
      group: "Users",
      customer: adminApiUsername,
      article: {
        subject,
        body: "Seed article for the agent-reply Playwright scenario.",
        type: "note",
        internal: false,
      },
    },
  });

  if (resp.status() >= 300) {
    throw new Error(`Seed POST /api/v1/tickets failed: ${resp.status()} ${await resp.text()}`);
  }
  const ticket = await resp.json();
  await api.dispose();
  return ticket;
}

exports.register = function (shared) {
  test("administrator (agent): replies to an API-seeded ticket via the SPA", async ({ page }) => {
    // TODO: SPA session-cookie seeding via /api/v1/signin fails because
    // page.goto(zammadBaseUrl) auto-redirects unauthenticated SPA visits to
    // Keycloak, so the page.evaluate fires cross-origin against an empty
    // Keycloak cookie jar. The OIDC fallback flakes when the same Playwright
    // file ran an admin OIDC logout earlier in the run (Keycloak SSO state
    // not fully cleared). Tracked in roles/web-app-zammad/TODO.md.
    test.skip(true, "SPA agent reply scenario blocked by SPA-OIDC interlock; see TODO.md");
    expect(shared.env.adminApiUsername, "ADMIN_API_USERNAME must be set").toBeTruthy();
    expect(shared.env.adminApiPassword, "ADMIN_API_PASSWORD must be set").toBeTruthy();

    const subject = `playwright-agent-reply-${Date.now()}`;
    const ticket = await seedTicketViaApi(
      shared.env.zammadBaseUrl,
      shared.env.adminApiUsername,
      shared.env.adminApiPassword,
      subject
    );

    // Authenticate the SPA via the api-bot Zammad session endpoint instead of
    // a second OIDC login; the latter is flaky when the same Playwright file
    // also exercises an OIDC logout earlier in the run.
    await shared.signInAsApiBot(page);

    await page.goto(`${shared.env.zammadBaseUrl}/#ticket/zoom/${ticket.id}`, { waitUntil: "domcontentloaded" });
    await expect(page.locator("body")).toContainText(subject, { timeout: 60_000 });

    const replyBody = page
      .locator("div[contenteditable='true']")
      .or(page.locator("textarea[name='body']"))
      .first();
    await replyBody.waitFor({ state: "visible", timeout: 60_000 });

    const replyText = `agent-reply ${Date.now()}`;
    await replyBody.click();
    await page.keyboard.type(replyText);

    const updateButton = page
      .getByRole("button", { name: /update|aktualisieren/i })
      .first();
    await updateButton.click();

    await expect(page.locator("body")).toContainText(replyText, { timeout: 60_000 });

    await shared.zammadLogout(page);
  });
};
