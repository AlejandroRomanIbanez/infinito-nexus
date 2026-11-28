#!/bin/bash
set -e

: "${ODOO_RC:?ODOO_RC must be set (odoo config path)}"
: "${ODOO_UPDATE_MARKER:?ODOO_UPDATE_MARKER must be set (odoo update marker path)}"

ODOO_ENTRYPOINT_PYTHON_DIR="/usr/local/lib/odoo-entrypoint"

_db_param() {
  python3 "$ODOO_ENTRYPOINT_PYTHON_DIR/db_param.py" "$ODOO_RC" "$1"
}

_guarded_bootstrap() {
  python3 "$ODOO_ENTRYPOINT_PYTHON_DIR/guarded_bootstrap.py" "$ODOO_RC" "$ODOO_INIT_MODULES" "$ODOO_UPDATE_MARKER"
}

if [ -n "${ODOO_INIT_MODULES:-}" ]; then
  wait-for-psql.py \
    --db_host "$(_db_param db_host)" --db_port "$(_db_param db_port)" \
    --db_user "$(_db_param db_user)" --db_password "$(_db_param db_password)" \
    --timeout 120
  _guarded_bootstrap
fi

exec /entrypoint.sh "$@"
