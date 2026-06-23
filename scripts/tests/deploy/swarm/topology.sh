#!/usr/bin/env bash
# shellcheck disable=SC2034  # variables are consumed by callers that source this file

# Mandatory cluster-id prefix so every swarm-test cluster gets distinct container +
# network names and never reuses a shared default. Callers (Makefile targets, the
# workflow) must set SWARM_NAME. SOURCE this file (not literal-dump) so it expands.
: "${SWARM_NAME:?SWARM_NAME is required (cluster id) - pass name= to the make target}"
SWARM_PREFIX="${SWARM_NAME}-"

# Manager-node container name in the simulated swarm.
MGR="${SWARM_PREFIX}swarm-mgr-01"

# Base export path on the NFS server that backs swarm-shared volumes.
NFS_EXPORT_BASE=/srv/nfs

# NFS-server container name in the simulated swarm.
NFS_SERVER="${SWARM_PREFIX}nfs-server"

# Docker bridge network that links every simulated swarm container.
SWARM_LAB_NETWORK="${SWARM_PREFIX}swarm-lab"

# Worker-node-1 container name in the simulated swarm.
WRK1="${SWARM_PREFIX}swarm-wrk-01"

# Worker-node-2 container name in the simulated swarm.
WRK2="${SWARM_PREFIX}swarm-wrk-02"
