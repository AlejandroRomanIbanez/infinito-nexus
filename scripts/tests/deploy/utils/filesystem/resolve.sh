#!/usr/bin/env bash
# Resolve which filesystem one matrix entry runs its docker data root on and
# record the decision for the steps that follow.
#
# A random pick draws only from what the target can deliver; a stated one is
# honoured even where it is unsupported, and the applying step then fails. The
# choice goes to the step summary, since reproducing a red run means re-stating
# it verbatim.
#
# Arguments:
#   $1 STATED   ext4 | btrfs | zfs; 'auto' or empty for a random pick
#   $2 LABEL    matrix entry the pick belongs to, e.g. compose/web-app-gitea
#   $3 DISTROS  space-separated distributions the entry deploys on
#   $4 SCOPE    node   the pick must satisfy every entry in DISTROS
#               runner DISTROS is ignored; the runner's own pool applies
set -euo pipefail

STATED="${1:-}"
LABEL="${2:?usage: resolve.sh STATED LABEL DISTROS SCOPE}"
DISTROS="${3:-}"
SCOPE="${4:?usage: resolve.sh STATED LABEL DISTROS SCOPE}"

NODE_POOL="ext4 btrfs zfs"
RUNNER_POOL="ext4 btrfs"

supported_by() {
	case "$1" in
	centos | arch | fedora) echo "ext4 btrfs" ;;
	*) echo "ext4 btrfs zfs" ;;
	esac
}

candidates() {
	local pool="${NODE_POOL}" distro kept fs
	[ "${SCOPE}" = node ] || {
		echo "${RUNNER_POOL}"
		return 0
	}
	for distro in ${DISTROS}; do
		kept=""
		for fs in ${pool}; do
			case " $(supported_by "${distro}") " in
			*" ${fs} "*) kept="${kept} ${fs}" ;;
			esac
		done
		pool="${kept# }"
	done
	echo "${pool:-ext4}"
}

if [ -n "${STATED}" ] && [ "${STATED}" != auto ]; then
	PICKED="${STATED}"
	ORIGIN="stated"
	REQUIRED=true
else
	POOL="$(candidates)"
	read -ra POOL_ENTRIES <<<"${POOL}"
	PICKED="$(printf '%s\n' "${POOL_ENTRIES[@]}" | shuf -n1)"
	ORIGIN="random out of '${POOL}' on the ${SCOPE}; re-state it to reproduce this run"
	REQUIRED=false
fi

echo "filesystem for ${LABEL}: ${PICKED} (${ORIGIN})"

if [ -n "${GITHUB_ENV:-}" ]; then
	{
		echo "INFINITO_DOCKER_FILESYSTEM=${PICKED}"
		echo "INFINITO_DOCKER_FILESYSTEM_REQUIRED=${REQUIRED}"
	} >>"${GITHUB_ENV}"
fi

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
	echo "- \`${LABEL}\` runs its docker data root on \`${PICKED}\` (${ORIGIN})" \
		>>"${GITHUB_STEP_SUMMARY}"
fi
