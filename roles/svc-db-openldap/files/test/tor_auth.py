"""Bind to OpenLDAP over Tor and ask who am I.

Args (argv): SOCKS proxy ``host:port``, onion host, onion port.
Env: BIND_DN, DB_PW. Exits 0 when the bind succeeds and the server names the identity.
"""

import os
import sys

from ldap3 import Connection, Server
from socks_forward import start_forward

local_port = start_forward(sys.argv[1], sys.argv[2], int(sys.argv[3]))
try:
    server = Server("127.0.0.1", port=local_port, connect_timeout=120)
    conn = Connection(
        server,
        user=os.environ["BIND_DN"],
        password=os.environ["DB_PW"],
        auto_bind=True,
        receive_timeout=120,
    )
    who = conn.extend.standard.who_am_i()
    conn.unbind()
except Exception as exc:
    print(f"bind error: {exc}", file=sys.stderr)
    sys.exit(1)
sys.exit(0 if who else 1)
