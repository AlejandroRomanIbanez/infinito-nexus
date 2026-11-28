#!/usr/bin/env bash
# Param: BIN_RESOLVE_CONTAINER_ID (env) - path of the resolve-container-id helper
# Param: BIN_WRITER_COUNT (env)         - path of the installed writer_count.py
# Param: $1     - swarm stack name
# Param: $2     - service key of the local MariaDB or OpenLDAP instance that runs the probe
# Param: $3...  - writer URLs of every elector; exits 0 when exactly one answers
set -euo pipefail
stack="${1:?stack name required}"
service_key="${2:?service key required}"
shift 2
container exec -i "$("${BIN_RESOLVE_CONTAINER_ID:?resolver path required}" "$stack" "$service_key")" \
	python3 - "$@" <"${BIN_WRITER_COUNT:?writer count path required}"
