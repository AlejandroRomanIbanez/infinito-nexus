#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_context.sh"

# Verifies the swarm routing-mesh is functional for the just-deployed
# service. TCP-connect probe (protocol-agnostic) via the manager's
# published port confirms the mesh accepts and forwards requests to a
# live task. With multiple replicas, additionally probe each worker
# node's local routing-mesh entry to confirm the mesh works on every
# node that hosts a task.

mapfile -t PORTS < <(
	docker exec "${MGR}" docker service inspect "${SERVICE_NAME}" \
		--format '{{ range .Endpoint.Ports }}{{ .PublishedPort }}{{ "\n" }}{{ end }}' 2>/dev/null |
		grep -v '^$' || true
)

if [ "${#PORTS[@]}" -eq 0 ]; then
	echo "${SERVICE_NAME}: no published ports, skipping reachability probe"
	exit 0
fi

REPLICA_COUNT=$(docker exec "${MGR}" docker service inspect "${SERVICE_NAME}" \
	--format '{{ if .Spec.Mode.Replicated }}{{ .Spec.Mode.Replicated.Replicas }}{{ else }}1{{ end }}')

echo "${SERVICE_NAME}: replicas=${REPLICA_COUNT}, ports=[${PORTS[*]}]"

fail=0

# Probe via the manager (routing-mesh entry that every CI matrix uses)
for port in "${PORTS[@]}"; do
	if docker exec "${MGR}" timeout 5 bash -c "</dev/tcp/127.0.0.1/${port}" 2>/dev/null; then
		echo "OK manager port ${port}/tcp reachable"
	else
		echo "FAIL manager port ${port}/tcp unreachable"
		fail=1
	fi
done

# Multi-replica: every node hosting a task must accept incoming traffic
# locally (routing-mesh on each node forwards to a healthy backend).
if [ "${REPLICA_COUNT}" -gt 1 ]; then
	mapfile -t NODES < <(
		docker exec "${MGR}" docker service ps "${SERVICE_NAME}" \
			--filter desired-state=Running \
			--format '{{.Node}}' |
			sort -u
	)
	for node in "${NODES[@]}"; do
		[ -z "${node}" ] && continue
		for port in "${PORTS[@]}"; do
			if docker exec "${node}" timeout 5 bash -c "</dev/tcp/127.0.0.1/${port}" 2>/dev/null; then
				echo "OK node=${node} port=${port}/tcp reachable"
			else
				echo "FAIL node=${node} port=${port}/tcp unreachable"
				fail=1
			fi
		done
	done
fi

if [ "${fail}" -ne 0 ]; then
	exit 1
fi
