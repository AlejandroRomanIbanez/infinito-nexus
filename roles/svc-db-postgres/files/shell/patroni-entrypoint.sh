#!/bin/sh
# Param: $1 - mounted patroni.yml secret (root-owned, 0400)
# Param: $2 - postgres-owned copy Patroni and patronictl read
# Param: DB_REPLICATION_SUBNET - CIDR of the engine-internal overlay pg_hba admits replication from
# Param: DB_POSTGRES_PORT / DB_PATRONI_API_PORT - ports advertised to the peers
set -e
# The service name also resolves on the coordination-store network, whose source addresses pg_hba rejects
# shellcheck disable=SC2046 # hostname -I prints one address per word, each a separate argument
address=$(python3 -c 'import ipaddress, sys; net = ipaddress.ip_network(sys.argv[1]); print(next(a for a in sys.argv[2:] if ipaddress.ip_address(a) in net))' "${DB_REPLICATION_SUBNET:?}" $(hostname -I))
export PATRONI_POSTGRESQL_CONNECT_ADDRESS="${address}:${DB_POSTGRES_PORT:?}"
export PATRONI_RESTAPI_CONNECT_ADDRESS="${address}:${DB_PATRONI_API_PORT:?}"
install -o postgres -g postgres -m 0600 "${1:?}" "${2:?}"
mkdir -p "${PGDATA:?}"
chown postgres:postgres "$(dirname "$PGDATA")" "$PGDATA"
chmod 0700 "$PGDATA"
pid="$PGDATA/postmaster.pid"
if [ -f "$pid" ] && [ ! -s "$pid" ]; then rm -f "$pid"; fi
exec gosu postgres patroni "$2"
