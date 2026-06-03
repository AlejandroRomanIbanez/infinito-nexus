#!/usr/bin/env bash
set -euo pipefail

stack_service="${1:?stack_service required (e.g. mediawiki_mediawiki)}"
require_running="${2:-true}"

task_id="$(container service ps "${stack_service}" --filter desired-state=running --format '{{.ID}}' --no-trunc 2>/dev/null | head -n1)"
if [ -z "${task_id}" ]; then
	echo "no-task-yet" >&2
	exit 1
fi

if [ "${require_running}" = "true" ]; then
	state="$(container inspect "${task_id}" --format '{{.Status.State}}' 2>/dev/null)"
	case "${state}" in
		running | starting)
			:
			;;
		*)
			echo "task-state=${state}" >&2
			exit 1
			;;
	esac
fi

cid="$(container inspect "${task_id}" --format '{{.Status.ContainerStatus.ContainerID}}' 2>/dev/null)"
if [ -z "${cid}" ]; then
	echo "no-container-id-in-task" >&2
	exit 1
fi

printf '%s' "${cid}"
