#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/tests/deploy/swarm/00_topology.sh
. "${SCRIPT_DIR}/00_topology.sh"
# shellcheck source=/dev/null
source <(grep -E '^INFINITO_PLAYWRIGHT_REPORTS_BASE_DIR=' "${SCRIPT_DIR}/../../../../.env")

: "${APP_ID:?APP_ID required}"

dest="/tmp/playwright-artifacts/${APP_ID}"
mkdir -p "${dest}"

set +e
timeout 900 docker exec "${MGR}" \
	tar -C "${INFINITO_PLAYWRIGHT_REPORTS_BASE_DIR}" -cf - . 2>/dev/null |
	tar -C "${dest}" -xf - 2>/dev/null
producer_rc=${PIPESTATUS[0]}
consumer_rc=${PIPESTATUS[1]}
set -e

if [ "${producer_rc}" -eq 124 ]; then
	echo "collect_playwright_reports: docker exec timed out after 900s (manager hung)" >&2
	exit 124
fi

if [ "${producer_rc}" -ne 0 ] || [ "${consumer_rc}" -ne 0 ]; then
	echo "collect_playwright_reports: collection failed (producer=${producer_rc} consumer=${consumer_rc}); reports may be partial" >&2
fi
