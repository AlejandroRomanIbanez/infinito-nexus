const { test } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");

test.use({ ignoreHTTPSErrors: true });

test("mautrix-slack addon: enabled", async () => {
  skipUnlessAddonEnabled("mautrix-slack");
  test.skip(true, "mautrix bridge: no in-app web surface; bridge wiring covered by web-app-matrix test-bridge-roster.js");
});
