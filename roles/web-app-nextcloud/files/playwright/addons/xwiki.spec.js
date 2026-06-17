const { test } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");

test.use({ ignoreHTTPSErrors: true });

test("xwiki addon: bridged XWiki partner has no in-app Nextcloud surface", async () => {
  skipUnlessAddonEnabled("xwiki");
  test.skip(
    true,
    "xwiki: bridged XWiki partner, no in-app web surface (covered by the partner web-app-xwiki role spec)"
  );
});
