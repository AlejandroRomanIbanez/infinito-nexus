"""``health_ready.py`` exits 0 once the engine answers its health URL, else the not-ready code."""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from utils.cache.files import PROJECT_ROOT

HEALTH = (
    PROJECT_ROOT / "roles/svc-ai-libretranslate-engine/files/python/health_ready.py"
)
NOT_READY = 75


class _Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(self.server.status)
        self.end_headers()

    def log_message(self, *args):
        return


class TestHealthReady(unittest.TestCase):
    def _rc(self, port):
        return subprocess.run(
            [
                sys.executable,
                str(HEALTH),
                f"http://127.0.0.1:{port}/health",
                "5",
                str(NOT_READY),
            ],
            check=False,
        ).returncode

    def test_a_healthy_engine_ends_the_wait(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Health)
        server.status = 200
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.assertEqual(self._rc(server.server_address[1]), 0)

    def test_a_closed_port_is_not_ready(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        self.assertEqual(self._rc(port), NOT_READY)


if __name__ == "__main__":
    unittest.main()
