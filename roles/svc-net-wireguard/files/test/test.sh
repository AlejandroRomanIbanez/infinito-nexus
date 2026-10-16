#!/usr/bin/env bash
# shellcheck shell=bash
#
# svc-net-wireguard role test: three throwaway hosts from one inventory, two
# full meshes, host II in both. Each host joins its meshes through MESH_ROLE's
# networks.meshes. The mesh CLI writes the inventory, playbook-mesh.yml
# deploys the role onto the hosts, and the test proves that I and II reach
# each other, that II and III reach each other, and that I and III do not.
#
# Env (all required; the role's test.env carries them):
#   HOST_IMAGE  pinned base image of the throwaway hosts, without WireGuard
#   MESH_ROLE   role whose networks.meshes puts each host into its meshes
#   PING_COUNT  echo requests per reachability probe
#   PYTHON      interpreter that runs Ansible and the mesh CLI
#   REPO_ROOT   repository the deploy runs from

set -euo pipefail

HOST_IMAGE="${HOST_IMAGE:?pass HOST_IMAGE as env (pinned base image of the hosts)}"
MESH_ROLE="${MESH_ROLE:?pass MESH_ROLE as env (role whose networks.meshes joins the hosts)}"
PING_COUNT="${PING_COUNT:?pass PING_COUNT as env (echo requests per probe)}"
PYTHON="${PYTHON:?pass PYTHON as env (interpreter that runs Ansible)}"
REPO_ROOT="${REPO_ROOT:?pass REPO_ROOT as env (repository the deploy runs from)}"

PREFIX="wg-mesh-$$"
NETWORK="${PREFIX}"
HOST_I="${PREFIX}-1"
HOST_II="${PREFIX}-2"
HOST_III="${PREFIX}-3"
HOSTS=("${HOST_I}" "${HOST_II}" "${HOST_III}")
WORK="$(mktemp -d)"

cleanup() {
	local host
	for host in "${HOSTS[@]}"; do
		if container inspect --type container "${host}" >/dev/null 2>&1; then
			container rm -f "${host}" >/dev/null
		fi
	done
	if container network inspect "${NETWORK}" >/dev/null 2>&1; then
		container network rm "${NETWORK}" >/dev/null
	fi
	rm -rf "${WORK}"
}
trap cleanup EXIT

host_vars() {
	local host="$1" meshes="$2"
	cat >"${WORK}/host_vars/${host}.yml" <<EOF
ansible_connection: docker
ansible_host: ${host}
ansible_user: root
ansible_python_interpreter: /usr/bin/python3
applications:
  svc-net-wireguard:
    networks:
      meshes:
        - name: alpha
          subnet: "10.100.200.0/24"
          listen_port: 51900
        - name: beta
          subnet: "10.100.201.0/24"
          listen_port: 51901
  ${MESH_ROLE}:
    networks:
      meshes: ${meshes}
EOF
}

address() {
	"${PYTHON}" - "${WORK}/host_vars" "$1" "$2" <<'EOF'
import sys
from pathlib import Path

from cli.administration.inventory.mesh.transport import mesh_address

print(mesh_address(Path(sys.argv[1]), sys.argv[2], sys.argv[3]) or "")
EOF
}

reaches() {
	container exec "$1" ping -c "${PING_COUNT}" -W 2 "$2" >/dev/null 2>&1
}

failures=0

expect_reach() {
	local from="$1" to="$2" mesh="$3" target
	target="$(address "${to}" "${mesh}")"
	if [[ -n "${target}" ]] && reaches "${from}" "${target}"; then
		echo "[PASS] ${from} reaches ${to} at ${target} over ${mesh}"
	else
		echo "[FAIL] ${from} does not reach ${to} at '${target}' over ${mesh}" >&2
		failures=$((failures + 1))
	fi
}

expect_isolated() {
	local from="$1" to="$2" mesh="$3" target
	target="$(address "${to}" "${mesh}")"
	if [[ -z "${target}" ]]; then
		echo "[FAIL] ${to} holds no address on ${mesh}" >&2
		failures=$((failures + 1))
	elif reaches "${from}" "${target}"; then
		echo "[FAIL] ${from} reaches ${to} at ${target} over ${mesh}, which it never joined" >&2
		failures=$((failures + 1))
	else
		echo "[PASS] ${from} does not reach ${to} at ${target} over ${mesh}"
	fi
}

cd "${REPO_ROOT}"
mkdir -p "${WORK}/host_vars"
"${PYTHON}" -c 'import secrets; print(secrets.token_hex(32))' >"${WORK}/.password"

echo "[INFO] starting three throwaway hosts from ${HOST_IMAGE}"
container network create "${NETWORK}" >/dev/null
for host in "${HOSTS[@]}"; do
	container run --detach --name "${host}" --hostname "${host}" \
		--network "${NETWORK}" --cap-add NET_ADMIN \
		"${HOST_IMAGE}" sleep infinity >/dev/null
	container exec "${host}" sh -c 'rm -rf /var/lib/apt/lists/* \
		&& apt-get -o Acquire::Retries=3 update -qq \
		&& apt-get -o Acquire::Retries=3 install -y -qq --no-install-recommends python3' >/dev/null
done

cat >"${WORK}/devices.yml" <<EOF
all:
  children:
    svc-net-wireguard:
      hosts:
        ${HOST_I}: {}
        ${HOST_II}: {}
        ${HOST_III}: {}
    ${MESH_ROLE}:
      hosts:
        ${HOST_I}: {}
        ${HOST_II}: {}
        ${HOST_III}: {}
EOF
host_vars "${HOST_I}" "[alpha]"
host_vars "${HOST_II}" "[alpha, beta]"
host_vars "${HOST_III}" "[beta]"

echo "[INFO] writing the meshes into the inventory"
"${PYTHON}" -m cli.administration.inventory.mesh \
	--inventory "${WORK}/devices.yml" \
	--host-vars-dir "${WORK}/host_vars" \
	--vault-password-file "${WORK}/.password"

echo "[INFO] deploying svc-net-wireguard onto the three hosts"
"$(dirname "${PYTHON}")/ansible-playbook" \
	-i "${WORK}/devices.yml" \
	--vault-password-file "${WORK}/.password" \
	playbook-mesh.yml

expect_reach "${HOST_I}" "${HOST_II}" alpha
expect_reach "${HOST_II}" "${HOST_I}" alpha
expect_reach "${HOST_II}" "${HOST_III}" beta
expect_reach "${HOST_III}" "${HOST_II}" beta
expect_isolated "${HOST_I}" "${HOST_III}" beta
expect_isolated "${HOST_III}" "${HOST_I}" alpha

if ((failures > 0)); then
	echo "[FATAL] ${failures} reachability assertion(s) failed" >&2
	exit 1
fi
echo "[OK] I and II reach each other, II and III reach each other, I and III do not"
