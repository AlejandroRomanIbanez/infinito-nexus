const { test } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");

test("keepassxc-browser addon: browser extension, no in-app web surface", async () => {
  skipUnlessAddonEnabled("keepassxc-browser");
  test.skip(true, "keepassxc-browser: desktop/browser extension, no in-app web surface");
});
