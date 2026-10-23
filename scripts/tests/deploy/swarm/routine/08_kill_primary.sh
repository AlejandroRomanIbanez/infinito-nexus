#!/usr/bin/env bash
# Param:
#   INFINITO_CI_KILL_PRIMARY     "true" runs the probe; anything else skips it
#   INFINITO_SWARM_DB_TOPOLOGY   must be "ha"; a standalone row is never touched
#   SWARM_LAB_MANAGERS           space-separated manager node containers
#   KILL_PRIMARY_TIMEOUT         seconds to wait for failover and the app (default 300)
set -euo pipefail

if [ "${INFINITO_CI_KILL_PRIMARY}" != "true" ] || [ "${INFINITO_SWARM_DB_TOPOLOGY}" != "ha" ]; then
	echo "SKIP: kill-primary probe runs only on HA rows with INFINITO_CI_KILL_PRIMARY=true"
	exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/../utils/_context.sh"

skip_if_no_swarm_service

if [ -z "${HA_DEPS}" ]; then
	echo "SKIP: ${APP_ID} uses no central HA engine"
	exit 0
fi

: "${SWARM_LAB_MANAGERS:?SWARM_LAB_MANAGERS required}"
KILL_PRIMARY_TIMEOUT="${KILL_PRIMARY_TIMEOUT:-300}"
read -r -a MANAGERS <<<"${SWARM_LAB_MANAGERS}"
CTL="${MGR}"

# Param: $1 node container to avoid
# Sets CTL to a manager other than $1.
pick_controller() {
	local _m
	for _m in "${MANAGERS[@]}"; do
		if [ "${_m}" != "$1" ]; then
			CTL="${_m}"
			return 0
		fi
	done
	echo "FAILURE: no manager left besides $1" >&2
	exit 1
}

# Param: $1 engine
# Prints the engine's per-host instance services, sentinels excluded.
instance_services() {
	docker exec "${CTL}" docker service ls --format '{{.Name}}' |
		grep -E "^$1_$1-" | grep -vE "^$1_$1-sentinel-" || [ "$?" -eq 1 ]
}

# Param: $1 instance swarm service name
# Prints "<node> <cid>" of the instance's running task, or nothing.
instance_location() {
	local _node _cid
	_node=$(docker exec "${CTL}" docker service ps --filter desired-state=running \
		--format '{{.Node}}' "$1" 2>/dev/null | head -1)
	[ -n "${_node}" ] || return 0
	_cid=$(service_container_id "${_node}" "$1" 2>/dev/null || true)
	if [ -n "${_cid}" ]; then
		echo "${_node} ${_cid}"
	fi
}

# Param: $1 engine, $2 node container, $3 instance container id
is_primary() {
	case "$1" in
	postgres)
		docker exec "$2" docker exec "$3" python3 -c \
			'import os,urllib.request;urllib.request.urlopen("http://127.0.0.1:%s/primary" % os.environ["DB_PATRONI_API_PORT"],timeout=3)' \
			>/dev/null 2>&1
		;;
	redis)
		docker exec "$2" docker exec "$3" sh -c '
			REDISCLI_AUTH=$(cat "$REDIS_HA_SENTINEL_PASSWORD_FILE")
			export REDISCLI_AUTH
			for s in $REDIS_HA_SENTINELS; do
				m=$(timeout 3 redis-cli -h "$s" -p "$REDIS_HA_SENTINEL_PORT" --raw \
					SENTINEL get-master-addr-by-name "$REDIS_HA_MASTER_NAME" 2>/dev/null | head -1)
				[ -n "$m" ] && break
			done
			[ "${m%%.*}" = "${REDIS_HA_SELF%%.*}" ]' >/dev/null 2>&1
		;;
	*)
		docker exec "$2" docker exec "$3" python3 -c \
			'import os,urllib.request;urllib.request.urlopen("http://127.0.0.1:%s/writer" % os.environ["ELECTOR_PORT"],timeout=3)' \
			>/dev/null 2>&1
		;;
	esac
}

# Param: $1 engine
# Prints "<node> <cid> <service>" of the current primary, or nothing.
find_primary() {
	local _svc _loc
	for _svc in $(instance_services "$1"); do
		_loc=$(instance_location "${_svc}")
		[ -n "${_loc}" ] || continue
		# shellcheck disable=SC2086  # _loc is "<node> <cid>", split into is_primary's args
		if is_primary "$1" ${_loc}; then
			echo "${_loc} ${_svc}"
			return 0
		fi
	done
}

# Param: $1 engine, $2 node container, $3 instance container id, $4 unique stamp
write_through_endpoint() {
	case "$1" in
	postgres)
		docker exec "$2" docker exec "$3" sh -c '
			PGPASSWORD="$POSTGRES_PASSWORD" psql -h postgres -U postgres -d postgres -qAt \
				-c "CREATE TABLE IF NOT EXISTS kill_primary_probe (stamp bigint PRIMARY KEY)" \
				-c "INSERT INTO kill_primary_probe VALUES ($1)"' _ "$4"
		;;
	mariadb)
		docker exec "$2" docker exec "$3" sh -c '
			MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb -h mariadb -u root \
				-e "CREATE DATABASE IF NOT EXISTS kill_primary_probe; CREATE TABLE IF NOT EXISTS kill_primary_probe.probe (stamp BIGINT PRIMARY KEY); INSERT INTO kill_primary_probe.probe VALUES ($1)"' _ "$4"
		;;
	redis)
		docker exec "$2" docker exec "$3" sh -c '
			[ "$(REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli -h redis SET "kill-primary-probe:$1" 1)" = OK ]' _ "$4"
		;;
	openldap)
		docker exec "$2" docker exec "$3" sh -c '
			f=$(mktemp)
			printf %s "$LDAP_ROOT_PW" >"$f"
			printf "dn: cn=kill-primary-probe-%s,%s\nobjectClass: device\ncn: kill-primary-probe-%s\n" "$1" "$LDAP_SUFFIX" "$1" |
				ldapadd -x -H ldap://openldap:389 -D "$LDAP_ROOT_DN" -y "$f"
			rc=$?
			rm -f "$f"
			exit "$rc"' _ "$4"
		;;
	esac
}

# Param: $1 node container
is_manager() {
	local _m
	for _m in "${MANAGERS[@]}"; do
		[ "${_m}" != "$1" ] || return 0
	done
	return 1
}

# Param: $1 node container about to be killed
# Succeeds when the managers left after killing $1 still hold the Raft quorum.
keeps_quorum() {
	local _total="${#MANAGERS[@]}" _left="${#MANAGERS[@]}"
	if is_manager "$1"; then
		_left=$((_total - 1))
	fi
	[ $((_left * 2)) -gt "${_total}" ]
}

# Param: $1 node container
restart_node() {
	local _deadline
	docker start "$1" >/dev/null
	_deadline=$(($(date +%s) + KILL_PRIMARY_TIMEOUT))
	while [ "$(date +%s)" -lt "${_deadline}" ]; do
		if docker exec "${CTL}" docker node ls --format '{{.Hostname}} {{.Status}}' |
			grep -qxF "$1 Ready"; then
			echo "==> $1 rejoined the swarm"
			return 0
		fi
		sleep 3
	done
	echo "FAILURE: $1 did not rejoin within ${KILL_PRIMARY_TIMEOUT}s"
	exit 1
}

# Param: $1 engine
kill_primary_of() {
	local _engine="$1" _old _old_node _old_cid _old_service _killed_node="" _new="" _deadline _stamp
	if [ -z "$(instance_services "${_engine}")" ]; then
		echo "SKIP: ${_engine} runs no HA instances for ${APP_ID}"
		return 0
	fi
	_old=$(find_primary "${_engine}")
	if [ -z "${_old}" ]; then
		echo "FAILURE: no ${_engine} primary found before the kill"
		exit 1
	fi
	read -r _old_node _old_cid _old_service <<<"${_old}"
	echo "==> ${_engine} primary is ${_old_service} on ${_old_node}"

	if keeps_quorum "${_old_node}"; then
		pick_controller "${_old_node}"
		docker kill "${_old_node}" >/dev/null
		_killed_node="${_old_node}"
		echo "==> killed node ${_old_node}"
	else
		docker exec "${_old_node}" docker kill "${_old_cid}" >/dev/null
		echo "==> killing ${_old_node} would lose the Raft quorum; killed the ${_engine} container instead"
	fi

	_deadline=$(($(date +%s) + KILL_PRIMARY_TIMEOUT))
	while [ "$(date +%s)" -lt "${_deadline}" ]; do
		_new=$(find_primary "${_engine}" || true)
		if [ -n "${_new}" ] && [ "${_new##* }" != "${_old_service}" ]; then
			echo "==> new ${_engine} primary: ${_new##* } on ${_new%% *}"
			break
		fi
		_new=""
		sleep 3
	done
	[ -n "${_new}" ] || {
		echo "FAILURE: no new ${_engine} primary within ${KILL_PRIMARY_TIMEOUT}s"
		exit 1
	}

	_stamp="$(date +%s%N)"
	# shellcheck disable=SC2086  # ${_new% *} is "<node> <cid>", split into write_through_endpoint's args
	while ! write_through_endpoint "${_engine}" ${_new% *} "${_stamp}" >/dev/null 2>&1; do
		if [ "$(date +%s)" -ge "${_deadline}" ]; then
			echo "FAILURE: no write through the ${_engine} endpoint within ${KILL_PRIMARY_TIMEOUT}s after the kill"
			exit 1
		fi
		sleep 3
	done
	echo "==> write through the ${_engine} endpoint succeeded after the kill"

	wait_app_reachable "${_old_node}" "${_engine}"

	if [ -n "${_killed_node}" ]; then
		restart_node "${_killed_node}"
	fi
}

# Param: $1 node container that was faulted, $2 engine
wait_app_reachable() {
	local _deadline _app_node _app_ctr
	_deadline=$(($(date +%s) + KILL_PRIMARY_TIMEOUT))
	while [ "$(date +%s)" -lt "${_deadline}" ]; do
		_app_node=$(docker exec "${CTL}" docker service ps --filter desired-state=running \
			--format '{{.Node}}' "${SERVICE_NAME}" 2>/dev/null | grep -vxF "$1" | head -1 || true)
		if [ -n "${_app_node}" ]; then
			_app_ctr=$(service_container_id "${_app_node}" "${SERVICE_NAME}" 2>/dev/null || true)
			if [ -n "${_app_ctr}" ] && probe_app_reachable "${_app_node}" "${_app_ctr}" "${PROBE_PORT}"; then
				echo "${ENTITY} reachable after the $2 primary was killed"
				return 0
			fi
		fi
		sleep 3
	done
	echo "FAILURE: ${ENTITY} not reachable within ${KILL_PRIMARY_TIMEOUT}s after the $2 primary was killed"
	exit 1
}

for engine in ${HA_DEPS}; do
	kill_primary_of "${engine}"
done
