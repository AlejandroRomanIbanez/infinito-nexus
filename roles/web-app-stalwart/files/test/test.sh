#!/usr/bin/env bash
# Mailu → Stalwart migration state machine (see the role README):
#   the leg deploys the final-state topology (Stalwart current, Mailu legacy);
#   this test rewinds to the initial state (Mailu active), stores mail there,
#   cuts over with the migration switch on, and proves continuity.
# nocheck: raw-docker — storage assertions read the maildir volume via the container wrapper
set -euo pipefail

: "${STALWART_MIGRATION_E2E:?missing STALWART_MIGRATION_E2E}"
if [[ "${STALWART_MIGRATION_E2E}" != "true" ]]; then
	echo "SKIP: web-app-mailu is not co-deployed; nothing to migrate."
	exit 0
fi

: "${TEST_INVENTORY_DIR:?missing TEST_INVENTORY_DIR}"
: "${PYTHON_BIN:?missing PYTHON_BIN}"
: "${REPO_SRC_DIR:?missing REPO_SRC_DIR}"
: "${ADMIN_EMAIL:?missing ADMIN_EMAIL}"
: "${ADMIN_IMAP_PASSWORD:?missing ADMIN_IMAP_PASSWORD}"
: "${BIBER_EMAIL:?missing BIBER_EMAIL}"
: "${BIBER_IMAP_PASSWORD:?missing BIBER_IMAP_PASSWORD}"
: "${MAILU_MAILDIR_VOLUME:?missing MAILU_MAILDIR_VOLUME}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_ID="$(date +%s)"
SUBJ_A="infinito-mig-A-${RUN_ID}"
SUBJ_B="infinito-mig-B-${RUN_ID}"
SUBJ_C="infinito-mig-C-${RUN_ID}"
SUBJ_D="infinito-mig-D-${RUN_ID}"

WORKDIR="$(mktemp -d)"
INV_COPY="${WORKDIR}/inventory"
cleanup() { rm -rf "${WORKDIR}"; }
trap cleanup EXIT

send_mail() {
	local from="$1" rcpt="$2" subject="$3"
	printf 'From: %s\r\nTo: %s\r\nSubject: %s\r\nDate: %s\r\n\r\n%s\r\n' \
		"${from}" "${rcpt}" "${subject}" "$(date -R)" "migration e2e body ${subject}" \
		>"${WORKDIR}/mail.eml"
	local attempt
	for attempt in 1 2 3 4 5 6; do
		if curl -sS --connect-timeout 10 --max-time 60 --url "smtp://127.0.0.1:25" \
			--mail-from "${from}" --mail-rcpt "${rcpt}" \
			--upload-file "${WORKDIR}/mail.eml"; then
			echo "sent: ${subject} (${from} -> ${rcpt})"
			return 0
		fi
		echo "retry ${attempt}: SMTP submission of ${subject} failed; waiting 10s"
		sleep 10
	done
	echo "FAIL: could not submit ${subject} to port 25" >&2
	return 1
}

wait_stored_in_maildir() {
	local subject="$1" mountpoint="$2"
	local attempt
	for attempt in $(seq 1 30); do
		if grep -rqF "Subject: ${subject}" "${mountpoint}" 2>/dev/null; then
			echo "stored: ${subject} under ${mountpoint}"
			return 0
		fi
		sleep 5
	done
	echo "FAIL: ${subject} never appeared under ${mountpoint}" >&2
	return 1
}

imap_search() {
	local user="$1" password="$2" mailbox="$3" subject="$4"
	curl -sS --connect-timeout 10 --max-time 60 --insecure \
		--url "imaps://127.0.0.1:993/${mailbox}" \
		--user "${user}:${password}" \
		--request "SEARCH SUBJECT \"${subject}\"" 2>/dev/null |
		grep -qE 'SEARCH [0-9]'
}

wait_in_imap() {
	local user="$1" password="$2" subject="$3"
	local attempt mailbox
	for attempt in $(seq 1 30); do
		for mailbox in INBOX Junk "Junk Mail" Spam; do
			if imap_search "${user}" "${password}" "${mailbox// /%20}" "${subject}"; then
				echo "found: ${subject} in ${user}'s '${mailbox}'"
				return 0
			fi
		done
		sleep 5
	done
	echo "FAIL: ${subject} not found over IMAP for ${user}" >&2
	return 1
}

nested_deploy() {
	local provider="$1" import_mailu="$2"
	(
		cd "${REPO_SRC_DIR}"
		"${PYTHON_BIN}" "${SCRIPT_DIR}/patch_inventory.py" "${INV_COPY}" \
			--mail-provider "${provider}" --import-mailu "${import_mailu}"
	)
	(
		cd "${REPO_SRC_DIR}"
		"${PYTHON_BIN}" -m cli.administration.deploy.dedicated \
			"${INV_COPY}/devices.yml" -p "${INV_COPY}/.password" \
			-vv --assert true --diff \
			--id web-app-stalwart,web-app-mailu \
			-e 'TEST_E2E_ENABLED=false' \
			-- --skip-backup --skip-cleanup
	)
}

echo "=== [1/5] Rewind to the initial state: Mailu as the active provider ==="
cp -a "${TEST_INVENTORY_DIR}" "${INV_COPY}"
nested_deploy "web-app-mailu" "false"

echo "=== [2/5] Store mail in the initial state (A: biber->admin, B: admin->biber) ==="
send_mail "${BIBER_EMAIL}" "${ADMIN_EMAIL}" "${SUBJ_A}"
send_mail "${ADMIN_EMAIL}" "${BIBER_EMAIL}" "${SUBJ_B}"
MAILDIR_MOUNT="$(container volume inspect --format '{{ .Mountpoint }}' "${MAILU_MAILDIR_VOLUME}")"
wait_stored_in_maildir "${SUBJ_A}" "${MAILDIR_MOUNT}/${ADMIN_EMAIL}"
wait_stored_in_maildir "${SUBJ_B}" "${MAILDIR_MOUNT}/${BIBER_EMAIL}"

echo "=== [3/5] Cut over: Stalwart current, Mailu legacy, migration switch on ==="
nested_deploy "web-app-stalwart" "true"

echo "=== [4/5] Continuity: the stored mail survived the migration ==="
wait_in_imap "${ADMIN_EMAIL}" "${ADMIN_IMAP_PASSWORD}" "${SUBJ_A}"
wait_in_imap "${BIBER_EMAIL}" "${BIBER_IMAP_PASSWORD}" "${SUBJ_B}"

echo "=== [5/5] Live flow on the final state (C: biber->admin, D: admin->biber) ==="
send_mail "${BIBER_EMAIL}" "${ADMIN_EMAIL}" "${SUBJ_C}"
send_mail "${ADMIN_EMAIL}" "${BIBER_EMAIL}" "${SUBJ_D}"
wait_in_imap "${ADMIN_EMAIL}" "${ADMIN_IMAP_PASSWORD}" "${SUBJ_C}"
wait_in_imap "${BIBER_EMAIL}" "${BIBER_IMAP_PASSWORD}" "${SUBJ_D}"

echo "MIGRATION STATE MACHINE COMPLETE"
