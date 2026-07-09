#!/usr/bin/env bash
# Snapshot the pre-deploy state through the backup unit the PREVIOUS deploy
# installed, before this deploy mutates anything. A missing unit or an empty
# databases.csv means a fresh/unseeded host with nothing to save yet.
set -euo pipefail

UNIT="${1:?usage: pre_deploy_snapshot.sh <backup-unit-name> <databases-csv>}"
DATABASES_CSV="${2:?usage: pre_deploy_snapshot.sh <backup-unit-name> <databases-csv>}"

if ! systemctl cat "${UNIT}" >/dev/null 2>&1; then
    echo "SKIP: ${UNIT} not installed yet (fresh host)"
    exit 0
fi

if [[ ! -s "${DATABASES_CSV}" ]]; then
    echo "SKIP: ${DATABASES_CSV} missing or empty (nothing seeded yet)"
    exit 0
fi

echo "Starting ${UNIT} for the pre-deploy snapshot..."
systemctl start "${UNIT}"
echo "OK: pre-deploy snapshot finished"
