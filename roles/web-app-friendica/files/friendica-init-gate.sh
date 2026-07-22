#!/bin/sh
set -eu

APP_DIR="/var/www/html"
VOLUME_VERSION_FILE="$APP_DIR/VERSION"
IMAGE_VERSION_FILE="/usr/src/friendica/VERSION"

slot="${TASK_SLOT:-1}"
case "$slot" in
  ''|*[!0-9]*) slot=1 ;;
esac

if [ "$slot" -ne 1 ]; then
  image_version="$(cat "$IMAGE_VERSION_FILE")"
  while true; do
    if [ -f "$VOLUME_VERSION_FILE" ]; then
      volume_version="$(cat "$VOLUME_VERSION_FILE" 2>/dev/null || echo '')"
      if [ "$volume_version" = "$image_version" ]; then
        break
      fi
    fi
    echo "Task slot ${slot}: waiting for slot 1 to finish Friendica init..."
    sleep 10
  done
fi

exec /entrypoint.sh "$@"
