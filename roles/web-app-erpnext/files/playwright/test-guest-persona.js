const { test } = require("@playwright/test");

const { runGuestFlow } = require("./personas");

exports.register = function (_shared) {
  test("guest: public-landing → auth chain → never authenticated", async ({ page }) => {
    await runGuestFlow(page);
  });
};
