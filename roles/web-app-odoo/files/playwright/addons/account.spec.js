const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");
const shared = require("../_shared");

test("addon account: invoicing module UI renders", async ({ browser }) => {
  skipUnlessAddonEnabled("account");

  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    await shared.loginToOdoo(page);
    await shared.openModule(page, "odoo/accounting");

    const surface = page.locator(
      ".o_web_client, .o_action_manager, .o_main_navbar, .o_content, .o_list_view, .o_kanban_view"
    );
    await expect(surface.first()).toBeVisible({ timeout: 60_000 });
  } finally {
    await page.close().catch(() => {});
    await context.close().catch(() => {});
  }
});
