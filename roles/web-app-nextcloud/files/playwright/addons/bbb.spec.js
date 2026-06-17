const { test } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");

test.use({ ignoreHTTPSErrors: true });

test("bbb addon: bridged BigBlueButton partner has no in-app Nextcloud surface", async () => {
  skipUnlessAddonEnabled("bbb");
  test.skip(
    true,
    "bbb: bridged BigBlueButton partner, no in-app web surface (room launch handled by the partner web-app-bigbluebutton role spec)"
  );
});
