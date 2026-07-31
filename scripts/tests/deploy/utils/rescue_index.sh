#!/usr/bin/env bash
# List the collected rescue tree and where to download it.
#
# Arguments:
#   $1 DIR    rescue directory to index; a missing directory is not an error
#   $2 LIMIT  max paths to list, default 400
set -euo pipefail

DIR="${1:?usage: rescue_index.sh DIR [LIMIT]}"
LIMIT="${2:-400}"

[ -d "${DIR}" ] || exit 0

FILES="$(find "${DIR}" -type f 2>/dev/null | wc -l)"
SIZE="$(du -sh "${DIR}" 2>/dev/null | cut -f1)"

echo "🩺 Rescue diagnostics: ${FILES} file(s), ${SIZE}, under ${DIR}"
echo "   Download them from the 'rescue-diagnostics-*' artifact on this run's summary page."
echo "   Paths below are relative to the artifact root; file contents are NOT printed here."

find "${DIR}" -mindepth 1 -printf '%y %10s %P\n' 2>/dev/null | sort -k3 | sed -n "1,${LIMIT}p"

ENTRIES="$(find "${DIR}" -mindepth 1 2>/dev/null | wc -l)"
if [ "${ENTRIES}" -gt "${LIMIT}" ]; then
	echo "   ... $((ENTRIES - LIMIT)) further path(s) not listed; all of them are in the artifact."
fi
