const { test } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");

test.use({ ignoreHTTPSErrors: true });

test("mautrix-signal addon: enabled", async () => {
  skipUnlessAddonEnabled("mautrix-signal");
  test.skip(true, "mautrix bridge: no in-app web surface; bridge wiring covered by web-app-matrix test-bridge-roster.js");
});
