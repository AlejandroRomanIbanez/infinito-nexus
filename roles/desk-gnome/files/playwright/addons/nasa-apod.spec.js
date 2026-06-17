const { test } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");

test("nasa-apod addon: GNOME shell extension, no in-app web surface", async () => {
  skipUnlessAddonEnabled("nasa-apod");
  test.skip(true, "nasa-apod: desktop/browser extension, no in-app web surface");
});
