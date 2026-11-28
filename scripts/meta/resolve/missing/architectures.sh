#!/usr/bin/env bash
#
# Output:
#   The architectures the reference must serve but does not, space-separated;
#   empty when it serves all of them.
#
# Env:
#   IMAGE_ARCHITECTURES  narrows what the reference must serve; empty asks for
#                        the whole pool utils/github/variant/pools.py declares
set -euo pipefail

ref="${1:?Missing image reference}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../../../.." && pwd)"

if ! manifest="$(docker manifest inspect "${ref}" 2>/dev/null)"; then
	manifest=""
fi

cd "${repo_root}"

MANIFEST="${manifest}" IMAGE_ARCHITECTURES="${IMAGE_ARCHITECTURES:-}" \
	"${PYTHON:-python3}" -m cli.meta.ci.missing_architectures
