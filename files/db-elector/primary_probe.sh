#!/bin/bash
# Param: STACK    - swarm stack of the engine (e.g. mariadb)
# Param: INSTANCE - instance service key (e.g. mariadb-mgr-01)
#
# Exit codes:
#   0   the instance's writer elector holds the writer lease
#   1   the elector answered and the instance is no writer
#   2   the instance could not be asked
#   3   the instance's service is not deployed
#   64  missing args
set -u

STACK="${1:-}"
INSTANCE="${2:-}"
if [ -z "$STACK" ] || [ -z "$INSTANCE" ]; then
  echo "primary-probe: STACK and INSTANCE required" >&2
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
    urllib.request.urlopen("http://127.0.0.1:%s/writer" % os.environ["ELECTOR_PORT"], timeout=5)
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
