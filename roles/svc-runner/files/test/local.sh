#!/usr/bin/env bash
# Local checks for svc-runner: container health, DooD socket, and (in CI) a full
# nested deploy. Only runs via test-e2e-cli (RUNTIME dev/act/github), always
# containerized — no bare-host path. The deploy test needs GITHUB_TOKEN + a
# ci-<sha> tag so runner-1 can pull from GHCR.
set -euo pipefail

fail_count=0

echo "DinD mode: verifying runner containers started..."
for i in $(seq 1 "${RUNNER_COUNT}"); do
    # || echo: inspect exits non-zero if absent; keeps set -e from aborting first.
    state=$(container inspect --format '{{.State.Status}}' "${RUNNER_PROJECT_PREFIX}-${i}" 2>/dev/null || echo "not found")
    if [[ "${state}" != "running" ]]; then
        echo "FAIL: ${RUNNER_PROJECT_PREFIX}-${i} is not running (state=${state})"
        fail_count=$((fail_count + 1))
    else
        echo "OK: ${RUNNER_PROJECT_PREFIX}-${i} is running"
    fi
done
[[ "${fail_count}" -eq 0 ]] || { echo "FAIL: ${fail_count} container(s) not healthy in DinD"; exit 1; }

# DooD socket reachable — core capability for running CI jobs.
echo "DinD mode: verifying DooD socket in ${RUNNER_PROJECT_PREFIX}-1..."
if ! docker exec "${RUNNER_PROJECT_PREFIX}-1" docker version >/dev/null 2>&1; then
    echo "FAIL: Docker socket not accessible inside ${RUNNER_PROJECT_PREFIX}-1 — DooD broken in DinD"
    exit 1
fi
echo "OK: DooD socket accessible inside ${RUNNER_PROJECT_PREFIX}-1"

# Full deploy test, via DooD into the DinD daemon. Skipped locally (no token / no
# ci-<sha> image).
if [[ -n "${GITHUB_TOKEN:-}" ]] && [[ "${INFINITO_IMAGE_TAG:-}" == ci-* ]]; then
    echo "DinD mode: running full deploy test inside ${RUNNER_PROJECT_PREFIX}-1..."

    # Per-instance copy: the shared /opt/src/infinito .env/Corefile would make
    # inner coredns serve the wrong IP. Same-path dir keeps DooD bind-mounts valid.
    _iso_src="${RUNNER_INSTALL_DIR}/1/nested-src"
    container exec --user root "${RUNNER_PROJECT_PREFIX}-1" \
        bash -c "rm -rf ${_iso_src} && mkdir -p ${_iso_src} && tar -C /opt/src/infinito --exclude='./.env' --exclude='./compose/coredns/Corefile' --exclude='./.venvs' --exclude='./venv' --exclude='*/node_modules' --exclude='*/__pycache__' -cf - . | tar -C ${_iso_src} -xf - && chown -R github-runner:github-runner ${_iso_src}"

    # GHCR login (<<< avoids the pipe pattern the raw-docker lint rejects).
    container exec -e "GITHUB_TOKEN=${GITHUB_TOKEN}" "${RUNNER_PROJECT_PREFIX}-1" \
        bash -c "docker login ghcr.io -u github-actions --password-stdin <<< \"\${GITHUB_TOKEN}\""

    container exec "${RUNNER_PROJECT_PREFIX}-1" \
        bash -c "cd ${_iso_src} && make install"

    # Fresh nested state (a stale /etc/nginx volume dir breaks openresty bootstrap).
    container exec "${RUNNER_PROJECT_PREFIX}-1" \
        bash -c "docker ps -aq --filter label=com.docker.compose.project=infinito | xargs -r docker rm -f" \
        || true
    container exec "${RUNNER_PROJECT_PREFIX}-1" \
        bash -c "docker volume ls -q --filter name=^infinito_ | xargs -r docker volume rm" \
        || true

    # Deploy web-app-dashboard like the smoke test. Overrides: COMPOSE_PROJECT_NAME/
    # INFINITO_RUNNER_PREFIX=infinito so the nested stack builds its own
    # correctly-subnetted network instead of reusing runner-1's; RUNTIME=github
    # runs the E2E roles; CI=true keeps the package-cache off (direct pulls).
    if ! container exec \
        -e "COMPOSE_PROJECT_NAME=infinito" \
        -e "INFINITO_RUNNER_PREFIX=infinito" \
        -e "RUNTIME=github" \
        -e "CI=true" \
        -e "apps=web-app-dashboard" \
        -e "disable=matomo" \
        -e "INFINITO_DEPLOY_TYPE=server" \
        -e "INFINITO_DISTROS=debian" \
        -e "INFINITO_INVENTORY_DIR=/tmp/runner-dind-inventory" \
        -e "INFINITO_DOCKER_VOLUME=/tmp/runner-dind-docker" \
        -e "INFINITO_IMAGE_TAG=${INFINITO_IMAGE_TAG}" \
        -e "INFINITO_GHCR_MIRROR_PREFIX=${INFINITO_GHCR_MIRROR_PREFIX:-}" \
        -e "GITHUB_TOKEN=${GITHUB_TOKEN}" \
        -e "GITHUB_REPOSITORY=${GITHUB_REPOSITORY:-}" \
        -e "GITHUB_REPOSITORY_OWNER=${GITHUB_REPOSITORY_OWNER:-}" \
        -e "ANSIBLE_LOG_PATH=/tmp/ansible-runner-dind-test.log" \
        "${RUNNER_PROJECT_PREFIX}-1" \
        bash "${_iso_src}/scripts/tests/deploy/ci/all.sh"; then
        echo "FAIL: nested deploy failed"
        exit 1
    fi
    echo "OK: full deploy inside ${RUNNER_PROJECT_PREFIX}-1 succeeded"
else
    echo "DinD mode: skipping full deploy test (GITHUB_TOKEN absent or INFINITO_IMAGE_TAG is not ci-<sha>)"
fi

echo "ALL LOCAL CHECKS PASSED (DinD)"
