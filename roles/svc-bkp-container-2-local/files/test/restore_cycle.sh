#!/usr/bin/env bash
# nocheck: raw-docker
# Disaster-recovery drill against the newest backup generation:
# stop every container, wipe each backed-up volume, restore it via
# baudolo-restore, restart the previously running containers and require
# every one of them healthy (or running when it defines no healthcheck).
set -euo pipefail

: "${BKP_TEST_BACKUPS_DIR:?}"
: "${BKP_TEST_RESTORE_BIN:?}"
: "${BKP_TEST_RSYNC_IMAGE:?}"
: "${BKP_TEST_HEALTH_TIMEOUT:?}"
: "${MACHINE_HASH:?}"
: "${REPO_DIR:?}"
: "${REPO_NAME:?}"
: "${NEWEST_GENERATION:?}"

GEN_DIR="${REPO_DIR}/${NEWEST_GENERATION}"

if [[ "$(docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null)" == "active" ]]; then
    echo "SKIP: swarm node detected; docker stop races the orchestrator's reconciler, the drill only supports compose hosts"
    exit 0
fi

SELF_NAME=""
SELF_PROJECT=""
if docker inspect "$(hostname)" >/dev/null 2>&1; then
    SELF_NAME="$(docker inspect -f '{{.Name}}' "$(hostname)" | sed 's|^/||')"
    SELF_PROJECT="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$(hostname)")"
    echo "OK: excluding own container '${SELF_NAME}' (project '${SELF_PROJECT}') from the cycle"
fi

mapfile -t RUNNING < <(docker ps --format '{{.Names}}\t{{.Label "com.docker.compose.project"}}' |
    awk -F'\t' -v self="${SELF_PROJECT}" -v selfname="${SELF_NAME}" \
        '$1 != selfname && (self == "" || $2 != self) { print $1 }')
if (( ${#RUNNING[@]} < 1 )); then
    echo "FAIL: no running containers before the restore cycle"
    exit 1
fi
echo "OK: ${#RUNNING[@]} running container(s) recorded"

docker pull "${BKP_TEST_RSYNC_IMAGE}" >/dev/null

echo "Stopping all containers..."
for name in "${RUNNING[@]}"; do
    docker stop "${name}" >/dev/null 2>&1 || echo "GONE: ${name} disappeared before stop"
done
for name in "${RUNNING[@]}"; do
    if [[ "$(docker inspect -f '{{.State.Status}}' "${name}" 2>/dev/null || echo gone)" == "running" ]]; then
        echo "FAIL: ${name} still running after docker stop"
        exit 1
    fi
done
echo "OK: all containers stopped"

mapfile -t VOLUMES < <(find "${GEN_DIR}" -mindepth 2 -maxdepth 2 -type d -name files -printf '%h\n' | sort | xargs -rn1 basename)
echo "Restoring ${#VOLUMES[@]} volume(s) from generation ${NEWEST_GENERATION}"

for volume in "${VOLUMES[@]}"; do
    if ! docker volume inspect "${volume}" >/dev/null 2>&1; then
        echo "SKIP: volume ${volume} does not exist on this host"
        continue
    fi
    docker run --rm -v "${volume}:/wipe" "${BKP_TEST_RSYNC_IMAGE}" \
        sh -c 'rm -rf /wipe/* /wipe/.[!.]* /wipe/..?*' >/dev/null
    if [[ -n "$(docker run --rm -v "${volume}:/wipe" "${BKP_TEST_RSYNC_IMAGE}" sh -c 'find /wipe -mindepth 1 -print -quit')" ]]; then
        echo "FAIL: volume ${volume} not empty after wipe"
        exit 1
    fi
    "${BKP_TEST_RESTORE_BIN}" files "${volume}" "${MACHINE_HASH}" "${NEWEST_GENERATION}" \
        --backups-dir "${BKP_TEST_BACKUPS_DIR}" \
        --repo-name "${REPO_NAME}" \
        --rsync-image "${BKP_TEST_RSYNC_IMAGE}"
    echo "OK: restored ${volume}"
done

echo "Restarting previously running containers..."
for name in "${RUNNING[@]}"; do
    docker start "${name}" >/dev/null 2>&1 || echo "GONE: ${name} disappeared before start"
done

DEADLINE=$(( $(date +%s) + BKP_TEST_HEALTH_TIMEOUT ))
for name in "${RUNNING[@]}"; do
    while :; do
        state="$(docker inspect -f '{{.State.Status}} {{.State.ExitCode}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${name}" 2>/dev/null)" || {
            echo "GONE: ${name} disappeared during health wait"
            break
        }
        read -r status exit_code health <<<"${state}"
        if [[ "${health}" == "healthy" ]] || { [[ "${health}" == "none" ]] && [[ "${status}" == "running" ]]; }; then
            echo "OK: ${name} ${status}/${health}"
            break
        fi
        if [[ "${status}" == "exited" ]] && [[ "${exit_code}" == "0" ]]; then
            echo "OK: ${name} oneshot exited 0"
            break
        fi
        if (( $(date +%s) >= DEADLINE )); then
            echo "FAIL: ${name} is ${status}/${health} after ${BKP_TEST_HEALTH_TIMEOUT}s"
            docker ps -a --format 'table {{.Names}}\t{{.Status}}'
            exit 1
        fi
        sleep 5
    done
done
echo "OK: all restored containers healthy"
