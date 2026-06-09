#!/usr/bin/env bash
set +e

REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
DIR_VAR_LIB="$(python3 -c "import yaml,sys;print(yaml.safe_load(open(sys.argv[1]))['DIR_VAR_LIB'])" \
	"${REPO_ROOT}/group_vars/all/05_paths.yml")"

if mountpoint -q "${DIR_VAR_LIB}" 2>/dev/null; then
	umount -lf "${DIR_VAR_LIB}" || true
fi

docker rm -f "${MGR}" "${WRK1}" "${WRK2}" "${NFS_SERVER}"
docker network rm "${SWARM_LAB_NETWORK}"
exit 0
