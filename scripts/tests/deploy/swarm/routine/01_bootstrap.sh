#!/usr/bin/env bash
# SPOT for the cluster bring-up, one CI step: host-side compose build + up and
# the sudo .deb build, then every node concern (systemd wait, IPs, lab DNS,
# repo + .deb install) via compose/swarm/playbook.yml over the docker connection.
# Host-side pre-clean here is only the bind-mount dir + leftover containers;
# stale root-owned NFS writes are wiped in-node by the play (this often
# non-root act runner cannot delete them).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

set -a
# shellcheck source=scripts/tests/deploy/swarm/topology/base.sh
. "${SCRIPT_DIR}/../topology/base.sh"
set +a

# shellcheck source=scripts/meta/env/load.sh
source "${SCRIPT_DIR}/../../../../../scripts/meta/env/load.sh"

: "${RUNNER_TEMP:?}" "${APP_ID:?}" "${INFINITO_DOMAIN:?}"

bash "${SCRIPT_DIR}/../utils/unmount_nfs_mounts.sh" "${NFS_SERVER}" >/dev/null 2>&1 || true
for node in "${MGR}" "${WRK1}" "${WRK2}" "${NFS_SERVER}" "${BACKUP_NODE}"; do
	docker rm -f "${node}" >/dev/null 2>&1 || true
done
mkdir -p "${RUNNER_TEMP}/nfs-export"

COMPOSE_FILE="${SCRIPT_DIR}/../../../../../compose/swarm.yml"
build_attempts=3
for attempt in $(seq 1 "${build_attempts}"); do
	docker compose -f "${COMPOSE_FILE}" -p "${SWARM_NAME}" --profile drill build && break
	if [ "${attempt}" -eq "${build_attempts}" ]; then
		echo "FAILURE: node image build failed after ${build_attempts} attempts" >&2
		exit 1
	fi
	sleep $((attempt * 5))
done

docker compose -f "${COMPOSE_FILE}" -p "${SWARM_NAME}" --profile drill up -d

HOST_SUDO=""
if [ "$(id -u)" -ne 0 ]; then
	HOST_SUDO="sudo -E"
fi

echo "==> Building .deb once on the act-runner"
DEB_PATH=$(PACKAGE_BUILD_ONLY=1 ${HOST_SUDO} bash "$(pwd)/${INFINITO_PACKAGE_INSTALL_SCRIPT:?}" |
	tee /dev/stderr | tail -n1)
[ -f "${DEB_PATH}" ] || {
	echo "FAILURE: builder did not produce a .deb (${DEB_PATH})"
	exit 1
}
echo "==> built ${DEB_PATH}"
export DEB_PATH

ansible-playbook \
	-i "${MGR},${WRK1},${WRK2},${NFS_SERVER},${BACKUP_NODE}," \
	-c docker \
	"${SCRIPT_DIR}/../../../../../compose/swarm/playbook.yml"
