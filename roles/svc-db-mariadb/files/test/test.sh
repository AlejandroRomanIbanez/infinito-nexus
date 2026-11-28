#!/usr/bin/env bash
# shellcheck shell=bash
#
# svc-db-mariadb credential test. Authenticate to the database with real
# credentials and run a trivial query (SELECT 1). The transport depends on the
# variant:
#   tor enabled  (variant 0, exposed) -> over the Tor network: connect to
#                <node-onion>:<port> through the SOCKS proxy (PyMySQL via a
#                local SOCKS5 forward) and authenticate.
#   tor disabled (variant 1)          -> local: authenticate inside the DB
#                container over TCP (forces password auth).
#
# Env (rendered into test.env from templates/test.env.j2):
#   TOR_ENABLED     true|false        (lookup('tor_reachable', application_id))
#   TOR_SOCKS       SOCKS proxy       (set in test.env.j2)
#   ONION_HOST      node onion host   (svc-net-tor services.tor.node)
#   DB_PORT         onion-forwarded database port
#   DB_CONTAINER    database container name
#   DB_USER         database user     (root)
#   DB_PASSWORD_B64 base64 password   (avoids shell-quoting issues)
#   RETRIES         attempts          (default 20)
#   SLEEP_SECONDS   wait between      (default 15)

set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RETRIES="${RETRIES:-20}"
SLEEP_SECONDS="${SLEEP_SECONDS:-15}"

DB_PASSWORD="$(printf '%s' "${DB_PASSWORD_B64}" | base64 -d 2>/dev/null)"
[ -n "${DB_PASSWORD}" ] || { echo "[FATAL] DB_PASSWORD_B64 missing or undecodable" >&2; exit 2; }
export MYSQL_PWD="${DB_PASSWORD}"

# Local: authenticate inside the container over TCP (127.0.0.1) so the server
# enforces password auth — a genuine credential check.
auth_local() {
	container exec -e MYSQL_PWD "${DB_CONTAINER}" \
		mariadb -h 127.0.0.1 -u "${DB_USER}" -N -B -e 'SELECT 1' 2>/dev/null |
		grep -qx 1
}

# Over Tor: PyMySQL (on this controller) connects through a local SOCKS5 -> onion
# forward and authenticates with the credentials.
auth_tor() {
	DB_USER="${DB_USER}" DB_PW="${DB_PASSWORD}" \
		PYTHONPATH="${here}/shared/tor" python3 "${here}/tor_auth.py" "${TOR_SOCKS}" "${ONION_HOST}" "${DB_PORT}"
}

run_auth() {
	if [ "${TOR_ENABLED}" = "true" ]; then
		auth_tor
	else
		auth_local
	fi
}

if [ "${TOR_ENABLED}" = "true" ]; then
	[ -n "${ONION_HOST}" ] || { echo "[FATAL] ONION_HOST unset but tor enabled" >&2; exit 2; }
	mode="over Tor"
else
	[ -n "${DB_CONTAINER}" ] || { echo "[FATAL] DB_CONTAINER unset for local auth" >&2; exit 2; }
	mode="local"
fi

attempt=1
while [ "${attempt}" -le "${RETRIES}" ]; do
	if run_auth; then
		echo "[OK]   mariadb credential auth ${mode} succeeded (SELECT 1)"
		exit 0
	fi
	attempt=$((attempt + 1))
	[ "${attempt}" -le "${RETRIES}" ] && sleep "${SLEEP_SECONDS}"
done

echo "[FAIL] mariadb credential auth ${mode} failed after ${RETRIES} attempts" >&2
exit 1
