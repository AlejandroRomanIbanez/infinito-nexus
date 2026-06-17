const { test } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");

test("dash-to-dock addon: GNOME shell extension, no in-app web surface", async () => {
  skipUnlessAddonEnabled("dash-to-dock");
  test.skip(true, "dash-to-dock: desktop/browser extension, no in-app web surface");
});
