#!/bin/sh
set -eu

APP_DIR="/var/www/html"
WEB_USER="www-data"
WEB_GROUP="www-data"
INSTALL_FLAG="${APP_DIR}/public/installed.flag"

log() { printf '%s %s\n' "[suitecrm-entrypoint]" "$*" >&2; }

if [ ! -d "$APP_DIR" ]; then
  log "ERROR: Application directory '$APP_DIR' does not exist."
  exit 1
fi

PERMS_STAMP="${APP_DIR}/.permissions-applied"
if [ ! -f "$PERMS_STAMP" ]; then
  log "Adjusting file permissions..."
  # Exception: read-only docker-config mounts (e.g. ldap.yaml) are immutable by design,
  # so chown/chmod on them always fails; without || true, set -e aborts the whole boot.
  # This is the one place silence is correct: the writable app dirs below are still
  # chown'd strictly, so any real permission failure there is not swallowed.
  chown -R "$WEB_USER:$WEB_GROUP" "$APP_DIR" || true
  find "$APP_DIR" -type d -exec chmod 755 {} + || true
  find "$APP_DIR" -type f -exec chmod 644 {} + || true

  for d in cache public/upload public/legacy/upload public/legacy/cache; do
    if [ -d "${APP_DIR}/${d}" ]; then
      chmod -R 775 "${APP_DIR}/${d}"
      chown -R "$WEB_USER:$WEB_GROUP" "${APP_DIR}/${d}"
    fi
  done

  echo "applied" > "$PERMS_STAMP"
  chown "$WEB_USER:$WEB_GROUP" "$PERMS_STAMP"
else
  log "Permissions stamp present - skipping full-tree permission pass."
fi

TMPDIR="${APP_DIR}/tmp"
export TMPDIR
mkdir -p "$TMPDIR"
chown "$WEB_USER:$WEB_GROUP" "$TMPDIR"
chmod 775 "$TMPDIR"

BOOT_LOCK="${APP_DIR}/.suitecrm-boot.lock.d"

# Exception: the swarm NFS mount forces local_lock=flock, so flock(2) never
# crosses nodes; atomic mkdir on the NFS server is the working cross-replica mutex.
_have_lock=0
_lock_tries=0
while :; do
  if mkdir "$BOOT_LOCK" 2>/dev/null; then
    _have_lock=1
    break
  fi
  # Exception: 1800s exceeds the orchestrator kill ceiling (start_period 15m
  # plus retries), so only a dead leader's lock can be this old.
  _lock_mtime=$(stat -c %Y "$BOOT_LOCK" 2>/dev/null || echo 0)
  if [ "$_lock_mtime" -gt 0 ] && [ $(($(date +%s) - _lock_mtime)) -ge 1800 ]; then
    log "Stale boot lock detected - removing it and retrying."
    rmdir "$BOOT_LOCK" 2>/dev/null || true
    continue
  fi
  if [ -f "$INSTALL_FLAG" ]; then
    break
  fi
  _lock_tries=$((_lock_tries + 1))
  if [ "$_lock_tries" -ge 180 ]; then
    log "ERROR: timed out waiting for the boot lock or install flag."
    exit 1
  fi
  sleep 5
done

if [ "$_have_lock" = "1" ]; then
  trap 'rmdir "$BOOT_LOCK" 2>/dev/null || true' EXIT
  trap 'rmdir "$BOOT_LOCK" 2>/dev/null || true; exit 143' TERM INT

  CACHE_REFRESH=0
  if [ ! -f "$INSTALL_FLAG" ]; then
    CACHE_REFRESH=1
    log "SuiteCRM 8 is not installed - performing automated installation..."

    php bin/console suitecrm:app:install \
        -u "$SUITECRM_ADMIN_USERNAME" \
        -p "$SUITECRM_ADMIN_PASSWORD" \
        -U "$SUITECRM_DB_USER" \
        -P "$SUITECRM_DB_PASSWORD" \
        -H "$SUITECRM_DB_HOST" \
        -N "$SUITECRM_DB_NAME" \
        -S "$SUITECRM_URL" \
        -d "no"

    echo "installed" > "$INSTALL_FLAG"
    chown "$WEB_USER:$WEB_GROUP" "$INSTALL_FLAG"

    log "SuiteCRM installation completed successfully."
  else
    log "SuiteCRM already installed - skipping installer."
  fi

  if [ "$CACHE_REFRESH" = "1" ] || [ ! -d "${APP_DIR}/cache/prod" ]; then
    log "Clearing Symfony cache..."
    php bin/console cache:clear --no-warmup || true
    php bin/console cache:warmup || true
  else
    log "Existing prod cache - skipping cache:clear/warmup."
  fi

  # Exception: install/cache:clear above run as root; the legacy language
  # caches they wipe are regenerated lazily by apache as www-data, which
  # cannot write into root-owned cache dirs -> permanent 500 without this.
  chown -R "$WEB_USER:$WEB_GROUP" "${APP_DIR}/cache" "${APP_DIR}/public/legacy/cache" 2>/dev/null || true

  rmdir "$BOOT_LOCK" 2>/dev/null || true
  trap - EXIT TERM INT
else
  log "SuiteCRM installed by another replica - skipping installer and cache pass."
fi

echo "OK" > "${APP_DIR}/public/healthcheck.html"
chown "$WEB_USER:$WEB_GROUP" "${APP_DIR}/public/healthcheck.html"

log "Starting apache2-foreground..."
exec apache2-foreground
