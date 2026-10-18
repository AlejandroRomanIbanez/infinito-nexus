#!/usr/bin/env bash
# Param: MARIADB_HA_BOOTSTRAP  1 on the instance that may initialise an empty data directory
# Param: MARIADB_SEED_PORT     port an empty non-bootstrap instance receives its seed stream on
# Param: ELECTOR_*             options of the writer elector (python -m infinito_elector)
set -euo pipefail

datadir=/var/lib/mysql
ready="${datadir}/.infinito-ha-ready"
db=""
elector=""

shutdown() {
  if [ -n "$elector" ] && kill -0 "$elector" 2>/dev/null; then
    kill -TERM "$elector" || true
    wait "$elector" || true
  fi
  if [ -n "$db" ] && kill -0 "$db" 2>/dev/null; then
    kill -TERM "$db" || true
    wait "$db" || true
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
if [ "$exited" = "$elector" ]; then
  echo "infinito-ha: writer elector exited rc=${rc}; stopping mariadbd" >&2
else
  echo "infinito-ha: mariadbd exited rc=${rc}; stopping the elector" >&2
fi
shutdown 1
