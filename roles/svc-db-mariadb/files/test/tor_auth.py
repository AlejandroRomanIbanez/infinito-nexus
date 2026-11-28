"""Authenticate to MariaDB over Tor and run SELECT 1.

Args (argv): SOCKS proxy ``host:port``, onion host, onion port.
Env: DB_USER, DB_PW. Exits 0 when SELECT 1 returns 1.
"""

import os
import sys

import pymysql
from socks_forward import start_forward

local_port = start_forward(sys.argv[1], sys.argv[2], int(sys.argv[3]))
try:
    conn = pymysql.connect(
        host="127.0.0.1",
        port=local_port,
        user=os.environ["DB_USER"],
        password=os.environ["DB_PW"],
        connect_timeout=120,
        read_timeout=120,
    )
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        row = cur.fetchone()
    conn.close()
except Exception as exc:
    print(f"auth error: {exc}", file=sys.stderr)
    sys.exit(1)
sys.exit(0 if row and row[0] == 1 else 1)
