#!/usr/bin/env bash
# Snapshot the pre-deploy NFS export state through the backup unit the
# PREVIOUS deploy installed, before this deploy mutates anything. A missing
# unit or an empty export means a fresh host with nothing to save yet.
# Unit names embed the project version, so after a version bump the previous
# deploy's unit differs from the requested name; fall back to a same-base
# glob and start the newest installed version.
set -euo pipefail

UNIT="${1:?usage: pre_deploy_snapshot.sh <backup-unit-name> <export-dir>}"
EXPORT_DIR="${2:?usage: pre_deploy_snapshot.sh <backup-unit-name> <export-dir>}"

if ! systemctl cat "${UNIT}" >/dev/null 2>&1; then
    BASE="${UNIT%%.*}"
    UNIT="$(systemctl list-unit-files --no-legend "${BASE}.*.service" 2>/dev/null | awk '{print $1}' | sort | tail -n1)"
    if [[ -z "${UNIT}" ]]; then
        echo "SKIP: no ${BASE}.* unit installed yet (fresh host)"
        exit 0
    fi
fi

if [[ -z "$(find "${EXPORT_DIR}" -mindepth 1 -print -quit 2>/dev/null)" ]]; then
    echo "SKIP: ${EXPORT_DIR} missing or empty (nothing exported yet)"
    exit 0
fi

echo "Starting ${UNIT} for the pre-deploy snapshot..."
systemctl start "${UNIT}"
echo "OK: pre-deploy snapshot finished"
