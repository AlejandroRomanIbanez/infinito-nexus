"""``primary_probe.sh`` of svc-db-postgres maps Patroni's answer, and the
instance resolver's failures, onto the probe exit codes."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from utils.cache.files import PROJECT_ROOT

SCRIPT = (
    PROJECT_ROOT / "roles" / "svc-db-postgres" / "files" / "shell" / "primary_probe.sh"
)
CONTAINER_STUB = """#!/usr/bin/env bash
exit "${EXEC_RC}"
"""
RESOLVER_STUB = """#!/usr/bin/env bash
[ -n "${RESOLVE_FAILS}" ] && exit "${RESOLVE_FAILS}"
printf 'cid-%s\\n' "$2"
"""


class TestPostgresPrimaryProbe(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        shutil.copy(SCRIPT, self.tmp / "primary-probe-postgres")
        for name, body in (
            ("resolve-container-id", RESOLVER_STUB),
            ("container", CONTAINER_STUB),
        ):
            path = self.tmp / name
            path.write_text(body)
            path.chmod(0o755)

    def _run(self, exec_rc=0, resolve_fails=""):
        env = {
            **os.environ,
            "PATH": f"{self.tmp}:{os.environ['PATH']}",
            "EXEC_RC": str(exec_rc),
            "RESOLVE_FAILS": resolve_fails,
        }
        return subprocess.run(
            [
                "bash",
                str(self.tmp / "primary-probe-postgres"),
                "postgres",
                "postgres-m1",
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        ).returncode

    def test_primary_and_replica(self):
        self.assertEqual(self._run(0), 0)
        self.assertEqual(self._run(1), 1)

    def test_unresolvable_instance_is_unknown(self):
        for rc in ("64", "65", "66"):
            with self.subTest(rc=rc):
                self.assertEqual(self._run(0, resolve_fails=rc), 2)

    def test_undeployed_instance_is_absent(self):
        self.assertEqual(self._run(0, resolve_fails="67"), 3)


if __name__ == "__main__":
    unittest.main()
