#!/bin/bash
# Param: STACK    - swarm stack of the engine (e.g. postgres)
# Param: INSTANCE - instance service key (e.g. postgres-mgr-01)
#
# Exit codes:
#   0   Patroni reports the instance as the primary
#   1   Patroni answered and the instance is a replica
#   2   the instance could not be asked
#   3   the instance's service is not deployed
#   64  missing args
set -u

STACK="${1:-}"
INSTANCE="${2:-}"
if [ -z "$STACK" ] || [ -z "$INSTANCE" ]; then
  echo "primary-probe-postgres: STACK and INSTANCE required" >&2
  exit 64
fi

CID=$("$(dirname "$0")/resolve-container-id" "$STACK" "$INSTANCE" 2>/dev/null)
case "$?" in
  0) ;;
  67) exit 3 ;;
  *) exit 2 ;;
esac

container exec "$CID" python3 -c '
import os, sys, urllib.error, urllib.request
try:
    urllib.request.urlopen("http://127.0.0.1:%s/primary" % os.environ["DB_PATRONI_API_PORT"], timeout=5)
except urllib.error.HTTPError:
    sys.exit(1)
except Exception:
    sys.exit(2)
'
RC=$?
case "$RC" in
  0 | 1) exit "$RC" ;;
  *) exit 2 ;;
esac
