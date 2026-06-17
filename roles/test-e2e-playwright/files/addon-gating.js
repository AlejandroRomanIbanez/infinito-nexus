const { test } = require("@playwright/test");

const SUFFIX = "_ADDON_ENABLED";

function envKey(id) {
  return id.toUpperCase().replace(/[^A-Z0-9]+/g, "_") + SUFFIX;
}

function isAddonEnabled(id) {
  const raw = process.env[envKey(id)];
  if (raw === undefined) return false;
  return String(raw).toLowerCase() === "true";
}

function addonDisabledReason(id) {
  if (isAddonEnabled(id)) return null;
  return `${envKey(id)} is not "true" (addon "${id}" disabled or not deployed)`;
}

function skipUnlessAddonEnabled(id) {
  const reason = addonDisabledReason(id);
  if (reason !== null) {
    test.skip(true, reason);
  }
}

module.exports = { envKey, isAddonEnabled, addonDisabledReason, skipUnlessAddonEnabled };
