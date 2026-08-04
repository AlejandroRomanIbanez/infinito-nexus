#!/usr/bin/env bash
# Resolve which filesystem one matrix entry runs its docker data root on and
# record the decision for the steps that follow.
#
# A random pick draws from what this kernel serves, measured here. Every distro
# image carries the userland for all three, the zfs one baked by
# scripts/install/zfs.sh, so the pool depends on the kernel alone. A stated pick
# is honoured even where it is unsupported, and the applying step then fails.
# The choice goes to the step summary, since reproducing a red run means
# re-stating it verbatim.
#
# Arguments:
#   $1 STATED   ext4 | btrfs | zfs; 'auto' or empty for a random pick
#   $2 LABEL    matrix entry the pick belongs to, e.g. compose/web-app-gitea
#   $3 DISTROS  space-separated distributions the entry deploys on, recorded
#               with the decision so a red run can be restated verbatim
#   $4 SCOPE    runner | node; names where the pick gets applied. The kernel
#               measured here is the runner's either way, because the node
#               containers share it.
set -euo pipefail

STATED="${1:-}"
LABEL="${2:?usage: resolve.sh STATED LABEL DISTROS SCOPE}"
DISTROS="${3:-}"
SCOPE="${4:?usage: resolve.sh STATED LABEL DISTROS SCOPE}"

POOL="ext4 btrfs zfs"

note() {
	echo "filesystem: $*" >&2
	[ -n "${GITHUB_STEP_SUMMARY:-}" ] || return 0
	echo "- \`${LABEL}\` filesystem: $*" >>"${GITHUB_STEP_SUMMARY}"
}

kernel_serves() {
	local fs="$1"
	[ "${fs}" != zfs ] || [ ! -c /dev/zfs ] || return 0
	if [ "${fs}" != zfs ] && grep -qw "${fs}" /proc/filesystems 2>/dev/null; then
		return 0
	fi
	if ! command -v modinfo >/dev/null; then
		note "${fs} left out: not loaded and modinfo is unavailable to ask for the module"
		return 1
	fi
	modinfo "${fs}" >/dev/null 2>&1 && return 0
	note "${fs} left out: this kernel carries no module for it"
	return 1
}

candidates() {
	local kept="" fs
	for fs in ${POOL}; do
		if ! kernel_serves "${fs}"; then
			continue
		fi
		kept="${kept} ${fs}"
	done
	kept="${kept# }"
	echo "${kept:-ext4}"
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

echo "filesystem for ${LABEL} on '${DISTROS}': ${PICKED} (${ORIGIN})"

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
