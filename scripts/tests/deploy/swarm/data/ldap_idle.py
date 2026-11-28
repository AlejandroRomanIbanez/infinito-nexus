"""Bind anonymously, idle on the same connection, then bind again.

Args (argv): LDAP host, LDAP port, idle seconds.
Prints ``first`` or ``no-bind`` for the first bind and ``second`` or
``dropped`` for the one after the idle time.
"""

import socket
import sys
import time

BIND = bytes.fromhex("300c020101600702010304008000")

with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=10) as conn:
    conn.sendall(BIND)
    print("first" if conn.recv(64)[5:6] == b"\x61" else "no-bind")
    time.sleep(float(sys.argv[3]))
    conn.sendall(BIND.replace(b"\x02\x01\x01", b"\x02\x01\x02", 1))
    print("second" if conn.recv(64)[5:6] == b"\x61" else "dropped")
