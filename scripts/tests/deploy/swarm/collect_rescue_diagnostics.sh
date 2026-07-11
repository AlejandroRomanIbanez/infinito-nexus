#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
# shellcheck source=scripts/tests/deploy/swarm/00_topology.sh
. "${SCRIPT_DIR}/00_topology.sh"
# shellcheck source=/dev/null
source <(grep -E '^INFINITO_RESCUE_DIAGNOSTICS_DIR=' "${REPO_ROOT}/.env")

: "${APP_ID:?APP_ID required}"

RESCUE_SH="${REPO_ROOT}/scripts/system/diagnostics/rescue.sh"

# rescue.sh runs on the manager during the ansible rescue, where `docker service`
# sees swarm-wide state but `docker ps/logs/inspect` only sees manager-local
# containers; a worker's own containers and node-delegated role extras only exist
# on that worker. So capture the SPOT diagnostics on EVERY node (piped in over
# stdin, so no docker cp and no second copy of the logic) and pull each node's
# folder into a subfolder named after the node. rescue.sh always exits 1 and a
# worker without bash just yields whatever the failure-time delegation left, so
# the capture is best-effort; the tar is what actually collects.
capture_node() {
	local node="$1"
	local label="$2"
	local dest="/tmp/rescue-diagnostics/${APP_ID}/${label}"
	mkdir -p "${dest}"

	timeout 600 docker exec -i \
		-e "INFINITO_RESCUE_DIAGNOSTICS_DIR=${INFINITO_RESCUE_DIAGNOSTICS_DIR}" \
		"${node}" bash -s "${APP_ID}" "collect-time capture on ${label}" \
		<"${RESCUE_SH}" >/dev/null 2>&1 || true

	set +e
	timeout 300 docker exec "${node}" \
		tar -C "${INFINITO_RESCUE_DIAGNOSTICS_DIR}" -cf - . 2>/dev/null |
		tar -C "${dest}" -xf - 2>/dev/null
	local pipe_rc=("${PIPESTATUS[@]}")
	set -e
	if [ "${pipe_rc[0]}" -eq 124 ]; then
		echo "collect_rescue_diagnostics: docker exec on ${node} timed out" >&2
	fi
}

capture_node "${MGR}" "${INFINITO_SWARM_MGR_NAME}"
capture_node "${WRK1}" "${INFINITO_SWARM_WRK1_NAME}"
capture_node "${WRK2}" "${INFINITO_SWARM_WRK2_NAME}"

exit 0
