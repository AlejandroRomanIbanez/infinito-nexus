"""``wait_single_writer.sh`` feeds ``writer_count.py`` to an instance, which
succeeds only while exactly one elector answers on its writer URL."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from utils.cache.files import PROJECT_ROOT

FILES = PROJECT_ROOT / "roles" / "sys-svc-compose" / "files"
SCRIPT = FILES / "shell" / "wait_single_writer.sh"
COUNT = FILES / "python" / "writer_count.py"
CONTAINER_STUB = f"""#!/usr/bin/env bash
echo "$*" >> "${{EXEC_LOG}}"
shift 4
exec {sys.executable} "$@"
"""
RESOLVER_STUB = """#!/usr/bin/env bash
printf 'cid-%s\\n' "$2"
"""


class _Writer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/writer" else 503)
        self.end_headers()

    def log_message(self, *args):
        return


class TestWaitSingleWriter(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for name, body in (
            ("resolve-container-id", RESOLVER_STUB),
            ("container", CONTAINER_STUB),
        ):
            path = self.tmp / name
            path.write_text(body)
            path.chmod(0o755)
        self.log = self.tmp / "exec.log"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Writer)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def _run(self, *urls):
        env = {
            **os.environ,
            "PATH": f"{self.tmp}:{os.environ['PATH']}",
            "EXEC_LOG": str(self.log),
            "BIN_RESOLVE_CONTAINER_ID": str(self.tmp / "resolve-container-id"),
            "BIN_WRITER_COUNT": str(COUNT),
        }
        return subprocess.run(
            ["bash", str(SCRIPT), "mariadb", "mariadb-m1", *urls],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def test_exactly_one_writer_passes(self):
        proc = self._run(f"{self.base}/writer", f"{self.base}/replica")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("writers=1", proc.stdout)
        log = self.log.read_text()  # nocheck: cache-read  stub-written
        self.assertIn("exec -i cid-mariadb-m1 python3 -", log)

    def test_two_writers_fail(self):
        proc = self._run(f"{self.base}/writer", f"{self.base}/writer")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("writers=2", proc.stdout)

    def test_no_writer_fails(self):
        self.assertEqual(self._run(f"{self.base}/replica").returncode, 1)

    def test_a_non_http_url_is_never_opened(self):
        proc = self._run(f"file://{COUNT}")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("writers=0", proc.stdout)


if __name__ == "__main__":
    unittest.main()
