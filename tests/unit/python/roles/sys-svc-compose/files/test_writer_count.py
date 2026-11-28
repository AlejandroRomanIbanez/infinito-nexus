"""``writer_count.py`` succeeds only while exactly one elector answers on its writer URL."""

from __future__ import annotations

import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from utils.cache.files import PROJECT_ROOT

COUNT = PROJECT_ROOT / "roles/sys-svc-compose/files/python/writer_count.py"


class _Elector(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/writer" else 503)
        self.end_headers()

    def log_message(self, *args):
        return


class TestWriterCount(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Elector)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def _run(self, *urls):
        return subprocess.run(
            [sys.executable, str(COUNT), *urls],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_one_writer_passes(self):
        proc = self._run(f"{self.base}/writer", f"{self.base}/replica")
        self.assertEqual((proc.returncode, proc.stdout.split()[0]), (0, "writers=1"))

    def test_two_writers_fail(self):
        proc = self._run(f"{self.base}/writer", f"{self.base}/writer")
        self.assertEqual((proc.returncode, proc.stdout.split()[0]), (1, "writers=2"))

    def test_a_non_http_url_is_never_opened(self):
        proc = self._run(f"file://{COUNT}")
        self.assertEqual((proc.returncode, proc.stdout.split()[0]), (1, "writers=0"))


if __name__ == "__main__":
    unittest.main()
