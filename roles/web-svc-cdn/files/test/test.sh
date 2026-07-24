#!/usr/bin/env bash
# E2E orchestrator for web-svc-cdn. Branches on the deployed CDN flavor:
#   internal - the one-shot npm-mirror build ran, so the served CDN root holds
#     the npm/ mirror tree (empty when no frontend-dep role is co-deployed).
#   external - front-proxy only, no build stack, so the served root has no npm/.
# Variables sourced from test.env.j2 by test-e2e-cli.
set -euo pipefail

: "${CDN_TEST_FLAVOR:?}"
: "${CDN_TEST_IS_STACK_HOST:?}"
: "${CDN_TEST_WEB_ROOT:?}"

if [[ "${CDN_TEST_IS_STACK_HOST}" != "true" ]]; then
    echo "SKIP: not the stack host; web-svc-cdn only builds there"
    exit 0
fi

npm_dir="${CDN_TEST_WEB_ROOT%/}/npm"

case "${CDN_TEST_FLAVOR}" in
internal)
    if [[ ! -d "${npm_dir}" ]]; then
        echo "FAIL: internal flavor but the one-shot build left no npm mirror at ${npm_dir}"
        exit 1
    fi
    echo "OK: internal flavor built the npm mirror tree at ${npm_dir}"
    ;;
*)
    if [[ -d "${npm_dir}" ]]; then
        echo "FAIL: external flavor but an npm mirror exists at ${npm_dir}; the build stack must not deploy"
        exit 1
    fi
    echo "OK: external flavor served without a build (no npm mirror at ${npm_dir})"
    ;;
esac

echo "ALL CHECKS PASSED"
