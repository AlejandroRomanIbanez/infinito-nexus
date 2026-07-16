#!/usr/bin/env bash
# shellcheck shell=bash
#
# Validate every Mermaid diagram in the repository's Markdown by rendering it
# with @mermaid-js/mermaid-cli (mmdc). A diagram GitHub cannot render (syntax
# error, reserved-word node id, ...) makes mmdc exit nonzero, failing the lint.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

cd "${REPO_ROOT}"

if ! command -v mmdc >/dev/null 2>&1; then
	echo "mmdc (@mermaid-js/mermaid-cli) not installed. Run 'make install-lint' first." >&2
	exit 127
fi

# Limitation: install-lint skips the puppeteer browser download so it stays
# sandbox-safe; mermaid-cli (puppeteer-core) bundles none, so provision the
# matching chrome-headless-shell here. --install-deps also pulls chrome's shared
# libs (libnspr4, libnss3, ...) on root Linux. Idempotent; needs network + unzip.
if ! npx --yes puppeteer browsers install chrome-headless-shell --install-deps >/dev/null 2>&1; then
	echo "Warning: chrome-headless-shell or its libs may be missing; mermaid rendering may fail." >&2
fi

workdir="$(mktemp -d)"
trap 'rm -rf "${workdir}"' EXIT

puppeteer_cfg="${workdir}/puppeteer-config.json"
printf '%s\n' '{"args":["--no-sandbox","--disable-gpu"]}' >"${puppeteer_cfg}"

mapfile -t md_files < <(grep -rlF --include='*.md' '```mermaid' . 2>/dev/null | sort || true)

if [[ ${#md_files[@]} -eq 0 ]]; then
	echo "No Markdown files contain a mermaid block; nothing to render."
	exit 0
fi

status=0
for md in "${md_files[@]}"; do
	[[ -n "${md}" ]] || continue
	if ! output="$(mmdc --puppeteerConfigFile "${puppeteer_cfg}" -i "${md}" -o "${workdir}/out.md" 2>&1)"; then
		status=1
		printf '❌ %s\n' "${md}"
		printf '%s\n' "${output}" | sed 's/^/    /'
	fi
done

if [[ "${status}" -eq 0 ]]; then
	printf '✅ %d Markdown file(s) with mermaid render cleanly.\n' "${#md_files[@]}"
fi

exit "${status}"
