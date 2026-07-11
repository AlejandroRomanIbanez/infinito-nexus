#!/usr/bin/env bash
# SPOT rescue diagnostics: the single script every Ansible rescue: block runs
# via ansible.builtin.script. It captures a full failure snapshot (all
# containers with their logs and inspect, all swarm services with ps and logs,
# the systemd journal, host resources) into a per-run folder that CI uploads as
# an artifact like the inventory and Playwright artifacts, prints one condensed
# summary, and ALWAYS exits 1 so the deploy still fails.
#
# Args (both optional, only used to label the snapshot):
#   $1  application_id
#   $2  context message describing the failing step
#
# No `set -e`: every collector is best-effort; a missing source must not abort
# the capture. INFINITO_RESCUE_DIAGNOSTICS_DIR (SPOT: group_vars/all/05_paths.yml
# DIR_RESCUE_DIAGNOSTICS) is the required output root; it is never defaulted here
# so there is one source.
set -uo pipefail

APP_ID="${1:-unknown}"
CONTEXT="${2:-}"

OUT_BASE="${INFINITO_RESCUE_DIAGNOSTICS_DIR:?INFINITO_RESCUE_DIAGNOSTICS_DIR not set (SPOT: group_vars/all/05_paths.yml)}"
STAMP="$(date -u +%Y%m%d%H%M%SZ)"
OUT="${OUT_BASE}/${APP_ID}-${STAMP}-$$"
mkdir -p "${OUT}/containers" "${OUT}/services"

runtime() {
	if command -v container >/dev/null 2>&1; then
		container "$@"
	else
		docker "$@"
	fi
}

sanitize() { printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_'; }

{
	echo "application_id: ${APP_ID}"
	echo "context: ${CONTEXT}"
	echo "captured_utc: ${STAMP}"
	echo "host: $(hostname 2>/dev/null || true)"
} >"${OUT}/meta.txt" 2>&1 || true

{
	uname -a
	echo
	cat /etc/os-release 2>/dev/null || true
} >"${OUT}/system.txt" 2>&1 || true

{
	df -h
	echo
	free -m 2>/dev/null || true
	echo
	swapon --show 2>/dev/null || true
	echo
	uptime 2>/dev/null || true
	echo
	echo "===== dmesg (oom/kill evidence, best effort) ====="
	dmesg -T 2>/dev/null | grep -Ei 'oom|kill|memory' | tail -n 80 || true
} >"${OUT}/resources.txt" 2>&1 || true

{
	runtime version
	echo
	runtime info
} >"${OUT}/runtime.txt" 2>&1 || true

runtime stats --no-stream --no-trunc >"${OUT}/stats.txt" 2>&1 || true

journalctl -n 1000 --no-pager >"${OUT}/journal.txt" 2>&1 || true

runtime ps -a >"${OUT}/containers.txt" 2>&1 || true
while IFS= read -r name; do
	[ -n "${name}" ] || continue
	safe="$(sanitize "${name}")"
	runtime logs "${name}" >"${OUT}/containers/${safe}.log" 2>&1 || true
	runtime inspect "${name}" >"${OUT}/containers/${safe}.inspect.json" 2>&1 || true
done < <(runtime ps -a --format '{{.Names}}' 2>/dev/null || true)

runtime service ls >"${OUT}/services.txt" 2>&1 || true
while IFS= read -r svc; do
	[ -n "${svc}" ] || continue
	safe="$(sanitize "${svc}")"
	runtime service ps --no-trunc "${svc}" >"${OUT}/services/${safe}.ps.txt" 2>&1 || true
	runtime service logs --no-task-ids "${svc}" >"${OUT}/services/${safe}.log" 2>&1 || true
done < <(runtime service ls --format '{{.Name}}' 2>/dev/null || true)

containers_n="$(runtime ps -aq 2>/dev/null | wc -l | tr -d ' ')"
services_n="$(runtime service ls -q 2>/dev/null | wc -l | tr -d ' ')"

echo "🩺 Rescue diagnostics for '${APP_ID}'${CONTEXT:+ (${CONTEXT})}"
echo "   snapshot: ${OUT}"
echo "   captured: ${containers_n} container(s), ${services_n} service(s), journal + host resources"
echo "   full detail in the uploaded rescue-diagnostics artifact"

exit 1
