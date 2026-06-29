#!/usr/bin/env bash
set -euo pipefail

# Collect each running infinito_nexus_* container's /root/inventories into one
# zip for the debug artifact. Hard fail when nothing is captured: a missing
# inventory hides a real deploy/path bug rather than being ignored at upload.

: "${APP_ID:?APP_ID is required (matrix.apps)}"

out="/tmp/inventory-compose-${APP_ID}.zip"
stage="/tmp/inventory-compose-${APP_ID}"
rm -rf "${stage}"
mkdir -p "${stage}"

mapfile -t containers < <(docker ps --format '{{.Names}}' | grep '^infinito_nexus_' || true)
for c in "${containers[@]}"; do
	docker cp "${c}:/root/inventories" "${stage}/${c}-inventories" 2>/dev/null || true
done

if [[ -d "${stage}" && -n "$(ls -A "${stage}" 2>/dev/null)" ]]; then
	(cd /tmp && zip -r "${out}" "inventory-compose-${APP_ID}")
else
	echo "::error::No inventories captured from compose containers (no /root/inventories in any infinito_nexus_* container)." >&2
	exit 1
fi
