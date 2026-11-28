#!/usr/bin/env bash
# shellcheck shell=bash
#
# svc-db-openldap credential test. Bind to the directory with the administrator
# DN + password (a real credential check) over the transport chosen by the
# variant:
#   tor enabled  (variant 0, exposed) -> over the Tor network: bind to
#                <node-onion>:<port> through the SOCKS proxy (ldap3 via a
#                local SOCKS5 forward).
#   tor disabled (variant 1)          -> local: bind inside the LDAP container
#                (ldapwhoami over TCP).
#
# Env (rendered into test.env from templates/test.env.j2):
#   TOR_ENABLED     true|false        (lookup('tor_reachable', application_id))
#   TOR_SOCKS       SOCKS proxy       (set in test.env.j2)
#   ONION_HOST      node onion host   (svc-net-tor services.tor.node)
#   DB_PORT         onion-forwarded LDAP port
#   DB_CONTAINER    LDAP container name (the primary's in HA form)
#   DB_LOCAL_PORT   LDAP port inside that container
#   BIND_DN_B64     base64 administrator bind DN
#   DB_PASSWORD_B64 base64 bind password
#   RETRIES         attempts          (default 20)
#   SLEEP_SECONDS   wait between      (default 15)

set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RETRIES="${RETRIES:-20}"
SLEEP_SECONDS="${SLEEP_SECONDS:-15}"

BIND_DN="$(printf '%s' "${BIND_DN_B64}" | base64 -d 2>/dev/null)"
DB_PASSWORD="$(printf '%s' "${DB_PASSWORD_B64}" | base64 -d 2>/dev/null)"
[ -n "${BIND_DN}" ] || { echo "[FATAL] BIND_DN_B64 missing or undecodable" >&2; exit 2; }
[ -n "${DB_PASSWORD}" ] || { echo "[FATAL] DB_PASSWORD_B64 missing or undecodable" >&2; exit 2; }

# Local: bind inside the container over TCP — a genuine credential check.
auth_local() {
	printf '%s' "${DB_PASSWORD}" | container exec -i "${DB_CONTAINER}" \
		ldapwhoami -x -H "ldap://127.0.0.1:${DB_LOCAL_PORT}" -D "${BIND_DN}" -y /dev/stdin \
		>/dev/null 2>&1
}

# Over Tor: ldap3 (on this controller) binds through a local SOCKS5 -> onion
# forward with the administrator credentials.
auth_tor() {
	BIND_DN="${BIND_DN}" DB_PW="${DB_PASSWORD}" \
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
	[ -n "${DB_LOCAL_PORT}" ] || { echo "[FATAL] DB_LOCAL_PORT unset for local auth" >&2; exit 2; }
	mode="local"
fi

attempt=1
while [ "${attempt}" -le "${RETRIES}" ]; do
	if run_auth; then
		echo "[OK]   openldap credential bind ${mode} succeeded"
		exit 0
	fi
	attempt=$((attempt + 1))
	[ "${attempt}" -le "${RETRIES}" ] && sleep "${SLEEP_SECONDS}"
done

echo "[FAIL] openldap credential bind ${mode} failed after ${RETRIES} attempts" >&2
exit 1
