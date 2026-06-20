const { test, expect } = require("@playwright/test");
const { skipUnlessAddonEnabled } = require("../addon-gating");

test.use({ ignoreHTTPSErrors: true });

const BRIDGE = "instagram";
const BOT_LOCALPART = "instagrambot";

test("mautrix-instagram addon: bridge appservice bot is provisioned and reachable on Synapse", async ({ request }) => {
  skipUnlessAddonEnabled("mautrix-instagram");
  test.setTimeout(60_000);

  const matrixBaseUrl = (process.env.MATRIX_BASE_URL || "").replace(/\/+$/, "");
  const matrixServerName = process.env.MATRIX_SERVER_NAME || "";
  expect(matrixBaseUrl, "MATRIX_BASE_URL must be set to probe the homeserver").toBeTruthy();
  expect(matrixServerName, "MATRIX_SERVER_NAME must be set to build the bridge bot MXID").toBeTruthy();

  const botMxid = `@${BOT_LOCALPART}:${matrixServerName}`;
  const profile = (mxid) =>
    `${matrixBaseUrl}/_matrix/client/v3/profile/${encodeURIComponent(mxid)}`;

  const botResponse = await request.get(profile(botMxid), { failOnStatusCode: false });
  expect(
    botResponse.status(),
    `the ${BRIDGE} bridge appservice bot ${botMxid} must not error on Synapse — a 5xx means the bridge's appservice registration failed to land`
  ).toBeLessThan(500);
  expect(
    botResponse.status(),
    `Synapse must recognize ${botMxid} as a provisioned user (the ${BRIDGE} bridge claims it via its appservice user namespace). A 404 means the mautrix-${BRIDGE} appservice did not register, so the bridge coupling is broken.`
  ).not.toBe(404);
  expect(
    botResponse.ok(),
    `Synapse must return the profile of the provisioned ${BRIDGE} bridge bot ${botMxid} (HTTP ${botResponse.status()})`
  ).toBeTruthy();

  const controlLocalpart = `definitely-not-a-bridge-bot-${Date.now()}`;
  const controlMxid = `@${controlLocalpart}:${matrixServerName}`;
  const controlResponse = await request.get(profile(controlMxid), { failOnStatusCode: false });
  expect(
    controlResponse.status(),
    `an un-bridged localpart ${controlMxid} must be unknown to Synapse (404); if it resolves, the probe is not actually testing the ${BRIDGE} appservice namespace`
  ).toBe(404);
});
