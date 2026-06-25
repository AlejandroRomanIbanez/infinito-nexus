#!/usr/bin/env bash
# Entrypoint for the ephemeral CI runner container.
# On every start: register with the provider (GitHub or Gitea), run, exit.
# Docker restarts the container and the cycle repeats.
set -euo pipefail

# In DinD test context there is no real provider token — verify the binary is
# present then sleep so the container stays running (exit 0 would trigger an
# immediate Docker restart loop with restart: unless-stopped).
if [[ "${DOCKER_IN_CONTAINER:-false}" == "true" ]]; then
    echo "SKIP: DinD environment — skipping runner registration"
    if [[ "${RUNNER_PROVIDER:-github}" == "gitea" ]]; then
        if [[ -x "./act_runner" ]]; then
            echo "OK: act_runner binary present at $(pwd)/act_runner"
        else
            echo "FAIL: act_runner not found"
            exit 1
        fi
    else
        if [[ -f "./run.sh" ]]; then
            echo "OK: runner binary present at $(pwd)/run.sh"
        else
            echo "FAIL: run.sh not found"
            exit 1
        fi
    fi
    exec sleep infinity
fi

# --- Gitea provider (act_runner against a co-located instance) ---
if [[ "${RUNNER_PROVIDER:-github}" == "gitea" ]]; then
    : "${RUNNER_API_TOKEN:?RUNNER_API_TOKEN must be set}"
    : "${RUNNER_GITEA_INSTANCE:?RUNNER_GITEA_INSTANCE must be set}"
    : "${RUNNER_NAME:?RUNNER_NAME must be set}"
    : "${RUNNER_LABELS:?RUNNER_LABELS must be set}"

    ./act_runner register \
        --no-interactive \
        --instance "${RUNNER_GITEA_INSTANCE}" \
        --token "${RUNNER_API_TOKEN}" \
        --name "${RUNNER_NAME}" \
        --labels "${RUNNER_LABELS}"

    exec ./act_runner daemon
fi

# --- GitHub provider (default) ---
: "${RUNNER_API_TOKEN:?RUNNER_API_TOKEN must be set}"
: "${RUNNER_GITHUB_OWNER:?RUNNER_GITHUB_OWNER must be set}"
: "${RUNNER_GITHUB_REPO:?RUNNER_GITHUB_REPO must be set}"
: "${RUNNER_NAME:?RUNNER_NAME must be set}"
: "${RUNNER_LABELS:?RUNNER_LABELS must be set}"

TOKEN=$(curl -fsSL \
    -X POST \
    -H "Authorization: Bearer ${RUNNER_API_TOKEN}" \
    -H "Accept: application/vnd.github.v3+json" \
    "https://api.github.com/repos/${RUNNER_GITHUB_OWNER}/${RUNNER_GITHUB_REPO}/actions/runners/registration-token" \
    | jq -r .token)

./config.sh \
    --url "https://github.com/${RUNNER_GITHUB_OWNER}/${RUNNER_GITHUB_REPO}" \
    --token "${TOKEN}" \
    --name "${RUNNER_NAME}" \
    --labels "${RUNNER_LABELS}" \
    --ephemeral \
    --unattended \
    --replace

exec ./run.sh
