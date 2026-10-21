#!/usr/bin/env bash
# Param: MARIADB_HA_BOOTSTRAP  1 on the instance that may initialise an empty data directory
# Param: MARIADB_SEED_PORT     port an empty non-bootstrap instance receives its seed stream on
# Param: ELECTOR_*             options of the writer elector (python -m infinito_elector); without ELECTOR_HOST_ID the stock entrypoint runs (standalone form)
set -euo pipefail

if [ -z "${ELECTOR_HOST_ID:-}" ]; then
  exec docker-entrypoint.sh "$@"
fi

datadir=/var/lib/mysql
ready="${datadir}/.infinito-ha-ready"
recovered="${datadir}/.infinito-ha-recovered"
db=""
elector=""

semi_sync_master() {
  gosu mysql mariadb --no-defaults --user="${ELECTOR_MARIADB_LOCAL_USER:?}" --socket="${ELECTOR_MARIADB_SOCKET:?}" \
    --connect-timeout=2 -N -B -e 'SELECT @@GLOBAL.rpl_semi_sync_master_enabled' 2>/dev/null
}

# Stops mariadbd: cleanly on a replica, by SIGKILL on a writer or when the role
# is unknown. A clean shutdown commits the writes still waiting for a semi-sync
# acknowledgement, and they become errant GTIDs no peer has; a kill leaves them
# prepared, so recovery as a replica (init_rpl_role = SLAVE) truncates them.
stop_db() {
  local master
  master="$(semi_sync_master || echo unknown)"
  case "$master" in
    0 | OFF)
      kill -TERM "$db" || true # nocheck: shell-or-true -- mariadbd may already have exited
      ;;
    *)
      echo "infinito-ha: semi-sync master is '${master}'; killing mariadbd so recovery drops unacknowledged writes" >&2
      case "$master" in 1 | ON) touch "$recovered" ;; esac
      kill -KILL "$db" || true # nocheck: shell-or-true -- mariadbd may already have exited
      ;;
  esac
  wait "$db" || true # nocheck: shell-or-true -- the exit code of a stopped mariadbd is irrelevant here
}

shutdown() {
  if [ -n "$elector" ] && kill -0 "$elector" 2>/dev/null; then
    kill -TERM "$elector" || true # nocheck: shell-or-true -- the elector may already have exited
    wait "$elector" || true # nocheck: shell-or-true -- the elector's exit code is irrelevant on shutdown
  fi
  if [ -n "$db" ] && kill -0 "$db" 2>/dev/null; then
    stop_db
  fi
  exit "${1:-0}"
}
trap 'shutdown 0' TERM INT

exec 9>"${datadir}/.instance.lock"
if ! flock -x -n 9; then
  echo "infinito-ha: waiting for the previous instance to release ${datadir}" >&2
  flock -x 9
fi

if [ "${MARIADB_HA_BOOTSTRAP:-0}" != "1" ] && [ ! -d "${datadir}/mysql" ]; then
  echo "infinito-ha: empty data directory, waiting for a seed stream on ${MARIADB_SEED_PORT}" >&2
  chown mysql:mysql "$datadir"
  gosu mysql python3 /opt/infinito/seed_relay.py recv "${MARIADB_SEED_PORT}" "${ELECTOR_REPLICATION_PASSWORD_FILE:?}" | gosu mysql mbstream -x -C "$datadir"
  gosu mysql mariadb-backup --prepare --target-dir="$datadir"
fi

docker-entrypoint.sh "$@" &
db=$!

while [ ! -e "$ready" ]; do
  kill -0 "$db" 2>/dev/null || shutdown 1
  sleep 2
done

until mariadb-admin --socket="${ELECTOR_MARIADB_SOCKET:?}" ping --silent >/dev/null 2>&1; do
  kill -0 "$db" 2>/dev/null || shutdown 1
  sleep 1
done

gosu mysql python3 -m infinito_elector &
elector=$!

exited=""
rc=0
wait -n -p exited "$db" "$elector" || rc=$?
if [ "$exited" = "$elector" ] && [ "$rc" = 3 ]; then
  echo "infinito-ha: former writer must recover before it follows; killing mariadbd" >&2
  kill -KILL "$db"
  exit 1
elif [ "$exited" = "$elector" ]; then
  echo "infinito-ha: writer elector exited rc=${rc}; stopping mariadbd" >&2
else
  echo "infinito-ha: mariadbd exited rc=${rc}; stopping the elector" >&2
fi
shutdown 1
