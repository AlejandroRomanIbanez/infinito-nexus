# nocheck: mirrored-unit-test - holds a PostgreSQL advisory lock on the live Odoo database and runs the odoo binary of the image; neither exists outside the Odoo container
"""Initialise an empty Odoo database, or apply a pending ``-u all``.

The advisory lock serialises the bootstrap across replicas that start at once.

Args:
    argv[1]: path of the Odoo config file.
    argv[2]: comma-separated modules to install into an empty database.
    argv[3]: update marker path; when it exists, every module is updated and
        the marker removed.
"""

import configparser
import subprocess
import sys
from pathlib import Path

import psycopg2


def main(rc: str, modules: str, marker: str) -> int:
    config = configparser.ConfigParser()
    config.read(rc)
    options = config["options"]
    db = options.get("db_name")
    conn = psycopg2.connect(
        host=options.get("db_host"),
        port=options.get("db_port", "5432"),
        user=options.get("db_user"),
        password=options.get("db_password"),
        dbname=db,
    )
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT pg_advisory_lock(hashtext('odoo_bootstrap_init'))")
    try:
        cur.execute("SELECT to_regclass('public.ir_module_module')")
        if cur.fetchone()[0] is None:
            print(
                f"[odoo-entrypoint] empty database -> installing core modules: {modules}",
                flush=True,
            )
            subprocess.run(
                [
                    "odoo",
                    "--no-http",
                    f"--database={db}",
                    f"--init={modules}",
                    "--stop-after-init",
                ],
                check=True,
            )
        elif marker and Path(marker).exists():
            print(
                "[odoo-entrypoint] update marker present -> `-u all` before serving",
                flush=True,
            )
            subprocess.run(
                [
                    "odoo",
                    "--no-http",
                    f"--database={db}",
                    "-u",
                    "all",
                    "--stop-after-init",
                ],
                check=True,
            )
            Path(marker).unlink()
    finally:
        cur.execute("SELECT pg_advisory_unlock(hashtext('odoo_bootstrap_init'))")
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
