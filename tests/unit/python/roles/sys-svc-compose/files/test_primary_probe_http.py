"""``primary_probe_http.py`` maps the instance's own primary check onto the probe exit codes."""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from utils.cache.files import PROJECT_ROOT

CHECK = PROJECT_ROOT / "roles/sys-svc-compose/files/python/primary_probe_http.py"


class _Check(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/primary" else 503)
        self.end_headers()

    def log_message(self, *args):
        return


class TestPrimaryProbeHttp(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Check)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def _rc(self, port, path):
        return subprocess.run(
            [sys.executable, str(CHECK), str(port), path], check=False
        ).returncode

    def test_a_2xx_answer_is_the_primary(self):
        self.assertEqual(self._rc(self.server.server_address[1], "/primary"), 0)

    def test_an_error_status_is_not_the_primary(self):
        self.assertEqual(self._rc(self.server.server_address[1], "/replica"), 1)

    def test_an_unreachable_check_is_unknown(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        self.assertEqual(self._rc(port, "/primary"), 2)


if __name__ == "__main__":
    unittest.main()
