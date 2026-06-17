const { test } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");

test("privacy-badger addon: browser extension, no in-app web surface", async () => {
  skipUnlessAddonEnabled("privacy-badger");
  test.skip(true, "privacy-badger: desktop/browser extension, no in-app web surface");
});
