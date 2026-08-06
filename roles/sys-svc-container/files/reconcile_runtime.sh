#!/usr/bin/env bash
#
# Resync dockerd after containerd restarted underneath it.
#
# A containerd restart under a live dockerd orphans the container shims: the new
# containerd does not re-adopt them, dockerd keeps stale task handles and
# force-deletes the container records while the processes stay alive and keep
# their file locks, so replacement tasks are blocked by their own predecessors.
# Package versions do not reveal that state, because containerd restarts into
# the version it was upgraded to and dockerd is not upgraded at all; the signal
# is the unit start order.
#
# A package upgrade restarts containerd on every node of the cluster at once, so
# the caller runs this one node at a time: simultaneous dockerd restarts can cost
# the swarm managers their quorum.
#
# Prints RECONCILED when it acted, UNCHANGED when the runtime was consistent.
set -euo pipefail

started() {
	systemctl show --property=ActiveEnterTimestampMonotonic --value "$1"
}

containerd_started="$(started containerd.service)"
docker_started="$(started docker.service)"

if [ -z "${containerd_started}" ] || [ -z "${docker_started}" ] ||
	[ "${containerd_started}" -eq 0 ] || [ "${docker_started}" -eq 0 ] ||
	[ "${containerd_started}" -le "${docker_started}" ]; then
	echo "UNCHANGED: containerd did not restart under dockerd"
	exit 0
fi

known="$(docker ps -aq --no-trunc | sort -u)"

orphans=()
while read -r scope; do
	[ -n "${scope}" ] || continue
	id="${scope#docker-}"
	id="${id%.scope}"
	grep -qxF "${id}" <<<"${known}" || orphans+=("${scope}")
done < <(systemctl list-units 'docker-*.scope' --state=active --no-legend --plain | awk '{print $1}')

if [ "${#orphans[@]}" -gt 0 ]; then
	printf 'reaping orphaned scope %s\n' "${orphans[@]}"
	systemctl stop "${orphans[@]}"
fi

systemctl restart docker.service
echo "RECONCILED: ${#orphans[@]} orphaned container scope(s) reaped, dockerd restarted"
