#!/usr/bin/env bash
# shellcheck shell=bash
#
# Runs the JavaScript unit suite through node:test, Node's built-in runner.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"

cd "${REPO_ROOT}"

suite="tests/unit/javascript"

mapfile -t tests < <(find "${suite}" -name '*.test.js' | sort)

if ((${#tests[@]} == 0)); then
	printf 'ERROR test-unit-javascript: no JavaScript unit tests in %s\n' "${suite}" >&2
	exit 1
fi

exec node --test "${tests[@]}"
