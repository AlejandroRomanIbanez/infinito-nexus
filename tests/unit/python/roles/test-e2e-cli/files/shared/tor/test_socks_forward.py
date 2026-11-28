"""The shared SOCKS5 forward the database CLI tests reach their onion through."""

from __future__ import annotations

import importlib.util
import socket
import threading
import unittest

from . import PROJECT_ROOT

MODULE_PATH = PROJECT_ROOT / "roles/test-e2e-cli/files/shared/tor/socks_forward.py"


def _load():
    spec = importlib.util.spec_from_file_location("socks_forward", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _recv_exact(conn: socket.socket, size: int) -> bytes:
    buf = b""
    while len(buf) < size:
        chunk = conn.recv(size - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


class _FakeSocksProxy:
    """A SOCKS5 proxy that records the CONNECT target and echoes the payload."""

    def __init__(self, reply: int) -> None:
        self.reply = reply
        self.target: tuple[str, int] | None = None
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        conn, _ = self.listener.accept()
        with conn:
            _recv_exact(conn, 3)
            conn.sendall(b"\x05\x00")
            head = _recv_exact(conn, 5)
            host = _recv_exact(conn, head[4]).decode()
            port = int.from_bytes(_recv_exact(conn, 2), "big")
            self.target = (host, port)
            conn.sendall(bytes([5, self.reply, 0, 1]) + b"\x00" * 6)
            if self.reply != 0:
                return
            while data := conn.recv(1024):
                conn.sendall(data)


class TestStartForward(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load()

    def test_bytes_reach_the_onion_and_come_back(self) -> None:
        proxy = _FakeSocksProxy(reply=0)
        local = self.module.start_forward(
            f"127.0.0.1:{proxy.port}", "example.onion", 5432
        )
        with socket.create_connection(("127.0.0.1", local), timeout=5) as client:
            client.sendall(b"SELECT 1")
            self.assertEqual(_recv_exact(client, 8), b"SELECT 1")
        self.assertEqual(proxy.target, ("example.onion", 5432))

    def test_a_refused_connect_closes_the_local_connection(self) -> None:
        proxy = _FakeSocksProxy(reply=5)
        local = self.module.start_forward(
            f"127.0.0.1:{proxy.port}", "example.onion", 3306
        )
        with socket.create_connection(("127.0.0.1", local), timeout=5) as client:
            client.settimeout(5)
            self.assertEqual(client.recv(1), b"")


if __name__ == "__main__":
    unittest.main()
