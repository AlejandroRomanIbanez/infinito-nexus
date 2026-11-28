#!/usr/bin/env bash
# Output: the distribution base image INFINITO_DISTRO builds FROM, on stdout.
set -euo pipefail

: "${INFINITO_DISTRO:?Source scripts/meta/env/load.sh or export INFINITO_DISTRO before invoking this script}"
: "${INFINITO_PARENT_IMAGE_OWNER:?Source scripts/meta/env/load.sh}"
: "${INFINITO_PARENT_IMAGE_TAG:?Source scripts/meta/env/load.sh}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"

cd "${repo_root}"
"${PYTHON:-python3}" -m cli.meta.ci.parent_image "${INFINITO_DISTRO}" "${INFINITO_PARENT_IMAGE_OWNER}" "${INFINITO_PARENT_IMAGE_TAG}"
