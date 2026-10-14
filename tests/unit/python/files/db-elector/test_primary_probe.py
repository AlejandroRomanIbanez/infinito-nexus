"""``files/db-elector/primary_probe.sh``, the writer probe MariaDB and
OpenLDAP share, maps the elector's answer onto the probe exit codes."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from utils.cache.files import PROJECT_ROOT

SCRIPT = PROJECT_ROOT / "files" / "db-elector" / "primary_probe.sh"
CONTAINER_STUB = """#!/usr/bin/env bash
echo "$*" >> "${EXEC_LOG}"
exit "${EXEC_RC}"
"""
RESOLVER_STUB = """#!/usr/bin/env bash
[ -n "${RESOLVE_FAILS}" ] && exit "${RESOLVE_FAILS}"
printf 'cid-%s\\n' "$2"
"""


class TestElectorPrimaryProbe(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        shutil.copy(SCRIPT, self.tmp / "primary-probe-mariadb")
        for name, body in (
            ("resolve-container-id", RESOLVER_STUB),
            ("container", CONTAINER_STUB),
        ):
            path = self.tmp / name
            path.write_text(body)
            path.chmod(0o755)
        self.log = self.tmp / "exec.log"

    def _run(self, exec_rc=0, resolve_fails=""):
        env = {
            **os.environ,
            "PATH": f"{self.tmp}:{os.environ['PATH']}",
            "EXEC_RC": str(exec_rc),
            "EXEC_LOG": str(self.log),
            "RESOLVE_FAILS": resolve_fails,
        }
        return subprocess.run(
            ["bash", str(self.tmp / "primary-probe-mariadb"), "mariadb", "mariadb-m1"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        ).returncode

    def test_writer(self):
        self.assertEqual(self._run(0), 0)
        log = self.log.read_text()  # nocheck: cache-read  the stub appends to this log during the test, a cached read would go stale
        self.assertIn("exec cid-mariadb-m1 python3 -c", log)
        self.assertIn("/writer", log)

    def test_no_writer(self):
        self.assertEqual(self._run(1), 1)

    def test_exec_failures_are_unknown(self):
        for rc in (2, 125, 126, 127):
            with self.subTest(rc=rc):
                self.assertEqual(self._run(rc), 2)

    def test_unresolvable_instance_is_unknown(self):
        for rc in ("64", "65", "66"):
            with self.subTest(rc=rc):
                self.assertEqual(self._run(0, resolve_fails=rc), 2)

    def test_undeployed_instance_is_absent(self):
        self.assertEqual(self._run(0, resolve_fails="67"), 3)


if __name__ == "__main__":
    unittest.main()
