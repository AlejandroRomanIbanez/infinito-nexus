const { test } = require("@playwright/test");

const { skipUnlessAddonEnabled } = require("../addon-gating");
const { skipUnlessServiceEnabled } = require("../service-gating");

test("PluggableAuth: auth framework, no in-app web surface", async () => {
  skipUnlessAddonEnabled("PluggableAuth");
  skipUnlessServiceEnabled("sso");

  test.skip(
    true,
    "PluggableAuth: authentication framework extension with no dedicated web surface (verified via the role's OpenIDConnect SSO login spec).",
  );
});
