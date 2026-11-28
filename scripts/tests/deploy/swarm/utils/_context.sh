#!/usr/bin/env bash
set -euo pipefail

_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)"
# shellcheck source=scripts/meta/env/load.sh
source "${_REPO_ROOT}/scripts/meta/env/load.sh"

if [ -s "${SWARM_DRILL_ENV:-}" ]; then
	set -a
	# shellcheck source=/dev/null
	source "${SWARM_DRILL_ENV}"
	set +a
fi

: "${APP_ID:?APP_ID required}"

ENTITY="$(PYTHONPATH="${_REPO_ROOT}" "${PYTHON}" -c "from utils.roles.entity.name import entity_name; print(entity_name('${APP_ID}'))")"

STACK_NAME="${ENTITY}"
CUSTOM_IMAGE_REPO="${ENTITY}_custom"

ROLE_DIR="${_REPO_ROOT}/roles/${APP_ID}"

_role_fact() {
	PYTHONPATH="${_REPO_ROOT}" "${PYTHON}" "${_REPO_ROOT}/scripts/tests/deploy/swarm/utils/_context.py" "$1" "${ROLE_DIR}" "$2"
}

PRIMARY_SERVICE_KEY="$(_role_fact primary-service-key "${ENTITY}")"
SERVICE_NAME="${STACK_NAME}_${PRIMARY_SERVICE_KEY}"

DB_DEP=none
if [ -f "${ROLE_DIR}/meta/services.yml" ]; then
	if grep -qE '^mariadb:' "${ROLE_DIR}/meta/services.yml"; then
		DB_DEP=mariadb
	elif grep -qE '^postgres:' "${ROLE_DIR}/meta/services.yml"; then
		DB_DEP=postgres
	fi
fi

HA_DEPS=""
if [ -f "${ROLE_DIR}/meta/services.yml" ]; then
	HA_DEPS="$(awk '
		/^postgres:/ { print "postgres" }
		/^mariadb:/ { print "mariadb" }
		/^redis:/ { print "redis" }
		/^ldap:/ { print "openldap" }
	' "${ROLE_DIR}/meta/services.yml" | paste -sd' ' -)"
fi

DEFAULT_PLACEMENT_MANAGER="$(_role_fact placement-manager "${APP_ID}")"

PROBE_PORT="$(_role_fact probe-port "${ENTITY}")"

NFS_VOLUMES="$(_role_fact nfs-volumes all)"
BACKUP_NFS_VOLUMES="$(_role_fact nfs-volumes backed-up)"

PRIMARY_NFS_VOLUME="${NFS_VOLUMES%%$'\n'*}"
BACKUP_NFS_VOLUME="${BACKUP_NFS_VOLUMES%%$'\n'*}"

NFS_CHECK_MOUNTPOINT="/mnt/nfs-check"

FAILOVER_SAVE=""
if [ -f "${ROLE_DIR}/files/shell/failover_save.sh" ]; then
	FAILOVER_SAVE="${ROLE_DIR}/files/shell/failover_save.sh"
fi

export APP_ID ENTITY STACK_NAME SERVICE_NAME PRIMARY_SERVICE_KEY CUSTOM_IMAGE_REPO DB_DEP HA_DEPS NFS_VOLUMES PRIMARY_NFS_VOLUME BACKUP_NFS_VOLUME DEFAULT_PLACEMENT_MANAGER PROBE_PORT NFS_CHECK_MOUNTPOINT FAILOVER_SAVE

# Exits the calling chaos step (09/10/11) with success when the role is
# manager-pinned (no worker task exists to drain).
skip_chaos_if_manager_pinned() {
	if [ "${DEFAULT_PLACEMENT_MANAGER}" = true ]; then
		echo "SKIP: ${ENTITY} declares placement: manager (single-node on the swarm manager) — drain-a-worker reschedule chaos does not apply"
		exit 0
	fi
}

has_swarm_service() {
	local _names=""
	[ -n "${MGR:-}" ] || return 1
	if ! _names="$(docker exec "${MGR}" docker stack services \
		--format '{{.Name}}' "${STACK_NAME}" 2>/dev/null)"; then
		_names=""
	fi
	grep -qxF "${SERVICE_NAME}" <<<"${_names}"
}

# Prints the swarm service carrying APP_ID's database. A role that pins its own
# engine runs it as <entity>_database inside its own stack, a central provider
# as <dep>_<dep> in its own (plugins/lookup/database.py).
resolve_db_service() {
	local _names=""
	[ "${DB_DEP}" != "none" ] || return 0
	[ -n "${MGR:-}" ] || return 0
	if ! _names="$(timeout 30 docker exec "${MGR}" docker service ls --format '{{.Name}}' 2>/dev/null)"; then
		return 0
	fi
	if grep -qxF "${STACK_NAME}_database" <<<"${_names}"; then
		printf '%s\n' "${STACK_NAME}_database"
	elif grep -qxF "${DB_DEP}_${DB_DEP}" <<<"${_names}"; then
		printf '%s\n' "${DB_DEP}_${DB_DEP}"
	fi
}

# Exits the calling gate (03/05/06/07) with success when the role deploys no
# swarm service to converge or drain.
skip_if_no_swarm_service() {
	if ! has_swarm_service; then
		echo "SKIP: ${ENTITY} (${APP_ID}) deployed no swarm service — converge/chaos gate does not apply"
		exit 0
	fi
}

# A stack whose sidecar is named after its app (<app>mcp) makes every
# `--filter name=<app>` a two-hit match, so both helpers below match exactly.
# Param: $1 node container, $2 swarm service name
service_container_id() {
	docker exec "$1" docker ps \
		--filter "label=com.docker.swarm.service.name=$2" \
		--format '{{.ID}}' | head -1
}

# Param: $1 manager container, $2 swarm service name
service_replicas() {
	docker exec "$1" docker service ls \
		--filter "name=$2" --format '{{.Name}} {{.Replicas}}' |
		awk -v svc="$2" '$1 == svc { print $2 }'
}

# Param: $1 node container, $2 app container id, $3 port
# Succeeds when http://localhost:$3/ inside $2 answers with a status from 200 to 499.
# Exits 2 when $2 has neither curl nor wget.
probe_app_http() {
	docker exec "$1" docker exec "$2" sh -c '
		if command -v curl >/dev/null 2>&1; then
			code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 "http://localhost:$1/") || exit 1
		elif command -v wget >/dev/null 2>&1; then
			code=$(wget -S -O - -T 10 "http://localhost:$1/" 2>&1 >/dev/null |
				sed -n "s/^ *HTTP\/[0-9.]* \([0-9][0-9][0-9]\).*/\1/p" | tail -n 1)
		else
			exit 2
		fi
		echo "HTTP ${code:-none}"
		[ -n "${code}" ] && [ "${code}" -ge 200 ] && [ "${code}" -lt 500 ]' _ "$3"
}

# Param: $1 node container, $2 app container id, $3 port
probe_app_reachable() {
	docker exec "$1" docker exec "$2" sh -c \
		"curl -sS http://localhost:$3/ || wget -qO- http://localhost:$3/ || nc -z localhost $3" >/dev/null 2>&1 ||
		docker exec "$1" docker exec "$2" bash -c "exec 3<>/dev/tcp/localhost/$3" >/dev/null 2>&1 ||
		docker exec "$1" sh -c "docker inspect -f '{{.State.Health.Status}}' $2 | grep -qx healthy" >/dev/null 2>&1
}

if [ "${SWARM_NFS_PILOT_VERBOSE:-0}" = "1" ]; then
	echo "==> APP_ID=${APP_ID}"
	echo "    ENTITY=${ENTITY}"
	echo "    STACK_NAME=${STACK_NAME}"
	echo "    SERVICE_NAME=${SERVICE_NAME}"
	echo "    CUSTOM_IMAGE_REPO=${CUSTOM_IMAGE_REPO}"
	echo "    DB_DEP=${DB_DEP}"
	echo "    PRIMARY_NFS_VOLUME=${PRIMARY_NFS_VOLUME}"
	echo "    BACKUP_NFS_VOLUME=${BACKUP_NFS_VOLUME}"
	echo "    DEFAULT_PLACEMENT_MANAGER=${DEFAULT_PLACEMENT_MANAGER}"
	echo "    PROBE_PORT=${PROBE_PORT}"
fi
