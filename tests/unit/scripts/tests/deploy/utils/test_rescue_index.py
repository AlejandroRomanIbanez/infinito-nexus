"""The caller contract of the rescue-artifact index.

``rescue_index.sh`` runs inside cleanup handlers and in a GitHub step under
``bash -e`` with no fallback, so its exit status decides whether the caller
finishes tearing down. Both cases here fail against a version without the
terminal ``exit 0``: a fatal usage error, and a ``find`` that rejects
``-printf`` — the latter also has to stay distinguishable from an empty tree
rather than reporting one.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from utils.cache.files import PROJECT_ROOT

INDEX = PROJECT_ROOT / "scripts" / "tests" / "deploy" / "utils" / "rescue_index.sh"
FIND_WITHOUT_PRINTF = '#!/bin/sh\necho "find: unrecognized: -printf" >&2\nexit 1\n'


class TestRescueIndexContract(unittest.TestCase):
    def _run(self, *args: str, stub_find: bool = False) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        with tempfile.TemporaryDirectory() as tmp:
            if stub_find:
                stub_bin = Path(tmp) / "bin"
                stub_bin.mkdir()
                find = stub_bin / "find"
                find.write_text(FIND_WITHOUT_PRINTF)
                find.chmod(0o755)
                env["PATH"] = f"{stub_bin}:{env['PATH']}"
            return subprocess.run(
                ["bash", str(INDEX), *args],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_a_fatal_error_does_not_reach_the_caller(self) -> None:
        self.assertEqual(self._run().returncode, 0)

    def test_a_failed_walk_neither_aborts_nor_looks_like_an_empty_tree(self) -> None:
        with (
            tempfile.TemporaryDirectory() as populated,
            tempfile.TemporaryDirectory() as empty,
        ):
            (Path(populated) / "a").mkdir()
            (Path(populated) / "a" / "collected.log").write_text("evidence")

            broken = self._run(populated, stub_find=True)
            genuinely_empty = self._run(empty)

        self.assertEqual(broken.returncode, 0)
        self.assertNotEqual(
            broken.stdout.replace(populated, ""),
            genuinely_empty.stdout.replace(empty, ""),
        )


if __name__ == "__main__":
    unittest.main()
