const { test } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");

test("ublock-origin addon: browser extension, no in-app web surface", async () => {
  skipUnlessAddonEnabled("ublock-origin");
  test.skip(true, "ublock-origin: desktop/browser extension, no in-app web surface");
});
