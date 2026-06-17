const { test } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");

test("dash-to-panel addon: GNOME shell extension, no in-app web surface", async () => {
  skipUnlessAddonEnabled("dash-to-panel");
  test.skip(true, "dash-to-panel: desktop/browser extension, no in-app web surface");
});
