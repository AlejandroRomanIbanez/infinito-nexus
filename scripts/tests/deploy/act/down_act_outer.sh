#!/usr/bin/env bash
# Param: ACT_OUTER_MATCH  optional name fragment; only act outer containers whose name
#                         contains it are removed, so runs of other jobs survive
set +e

# Match act's outer-runner name prefix, not the image: ACT_PLATFORM_IMAGE varies the ancestor.
ids="$(docker ps -aq --filter "name=^act-.*${ACT_OUTER_MATCH:-}")"
if [ -n "${ids}" ]; then
	echo "→ removing act outer container(s): ${ids}"
	# shellcheck disable=SC2086
	docker rm -f ${ids} >/dev/null 2>&1
else
	echo "→ no act outer container present (nothing to do)"
fi

exit 0
