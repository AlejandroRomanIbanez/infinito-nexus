<?php

define("OC_CONSOLE", 1);

require_once "/var/www/html/lib/base.php";

$appId = getenv("NC_APP_ID");
$payload = getenv("NC_ENC_B64");

if ($appId === false || $appId === "" || $payload === false || $payload === "") {
    fwrite(STDERR, "NC_APP_ID and NC_ENC_B64 are required\n");
    exit(1);
}

$entries = json_decode(base64_decode($payload), true);
if (!is_array($entries)) {
    fwrite(STDERR, "NC_ENC_JSON must decode to a JSON object\n");
    exit(1);
}

// icrypto: store an ICrypto ciphertext that the app reads back via $crypto->decrypt()
// (integration_gitlab/mattermost getClearAppValue). sensitive: store the plaintext as an
// IAppConfig sensitive value that getValueString() auto-decrypts (integration_zammad).
$mode = getenv("NC_ENC_MODE") ?: "icrypto";
$crypto = \OC::$server->get(\OCP\Security\ICrypto::class);
$appConfig = \OC::$server->get(\OCP\IAppConfig::class);

foreach ($entries as $key => $value) {
    $value = (string) $value;
    if ($value === "") {
        $appConfig->setValueString($appId, (string) $key, "", lazy: true);
    } elseif ($mode === "sensitive") {
        $appConfig->setValueString($appId, (string) $key, $value, lazy: true, sensitive: true);
    } else {
        $appConfig->setValueString($appId, (string) $key, $crypto->encrypt($value), lazy: true);
    }
}

echo "OK\n";
