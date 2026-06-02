#!/usr/bin/env bash
set +e

docker rm -f "${MGR}" "${WRK1}" "${WRK2}" "${NFS_SERVER}" apt-cache
docker network rm swarm-lab
exit 0
