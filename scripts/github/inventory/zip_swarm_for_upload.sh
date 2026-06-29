#!/usr/bin/env bash
set -euo pipefail

# Collect the swarm test inventories for the debug artifact. The matrix
# orchestrator (cli.administration.deploy.swarm.matrix) runs as root and writes
# a per-round inventory to /tmp/inv-<n> (plus the /tmp/inv base), so this must
# gather every /tmp/inv* dir -- not the single /tmp/inv the old version checked,
# which the planner never populates -- and de-root them so the unprivileged
# upload step can read the zip.
#
# Hard fail when there is nothing to copy: a silently-missing inventory hides a
# real provisioning/path bug rather than being ignored at upload time.

: "${APP_ID:?APP_ID is required (matrix.apps)}"

out="/tmp/inventory-swarm-${APP_ID}.zip"
stage="/tmp/inventory-swarm-${APP_ID}"
sudo rm -rf "${stage}" 2>/dev/null || rm -rf "${stage}" 2>/dev/null || true
mkdir -p "${stage}"

shopt -s nullglob
found=0
for d in /tmp/inv /tmp/inv-*; do
	[[ -d "${d}" ]] || continue
	sudo cp -a "${d}" "${stage}/$(basename "${d}")"
	found=1
done

if [[ "${found}" -eq 0 ]]; then
	echo "::error::No swarm inventory found to copy (expected /tmp/inv or /tmp/inv-*)." >&2
	exit 1
fi

sudo chown -R "$(id -u):$(id -g)" "${stage}"
(cd /tmp && zip -r "${out}" "inventory-swarm-${APP_ID}")
