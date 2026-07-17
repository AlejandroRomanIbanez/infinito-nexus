#!/bin/sh
# Param: JOB (env) - swarm service name of the one-shot install job.
# Exit 0 once the job task reports Complete, 2 on a terminal failure state
# (Failed/Rejected/Shutdown, so a crashed install never passes silently),
# 1 while still pending.
set -eu
state="$(container service ps "$JOB" --no-trunc --format '{{.CurrentState}} {{.Error}}' | head -1)"
case "$state" in
  Complete*) exit 0 ;;
  Failed*|Rejected*|Shutdown*) echo "install job failed: $state" >&2; exit 2 ;;
  *) exit 1 ;;
esac
