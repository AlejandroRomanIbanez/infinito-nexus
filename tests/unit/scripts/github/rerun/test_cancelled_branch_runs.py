from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from utils.cache.files import PROJECT_ROOT, read_text

SCRIPT = PROJECT_ROOT / "scripts" / "github" / "rerun" / "cancelled_branch_runs.sh"


def _run_record(database_id: int, conclusion: str, status: str) -> dict:
    return {
        "databaseId": database_id,
        "conclusion": conclusion,
        "status": status,
        "attempt": 1,
        "updatedAt": "2026-08-10T15:46:00Z",
    }


class TestCancelledBranchRuns(unittest.TestCase):
    def _run(self, runs: list[dict]) -> tuple[subprocess.CompletedProcess, list[str]]:
        with tempfile.TemporaryDirectory() as tmp:
            stub_bin = Path(tmp) / "bin"
            stub_bin.mkdir()
            rerun_log = Path(tmp) / "rerun.log"
            gh = stub_bin / "gh"
            gh.write_text(
                "#!/bin/sh\n"
                'if [ "$1" = "api" ]; then printf \'[{"name":"b"}]\\n\'; exit 0; fi\n'
                'if [ "$1" = "run" ] && [ "$2" = "list" ]; then'
                f" cat {json.dumps(str(Path(tmp) / 'runs.json'))}; exit 0; fi\n"
                'if [ "$1" = "run" ] && [ "$2" = "rerun" ]; then'
                f' echo "$3" >>{json.dumps(str(rerun_log))}; exit 0; fi\n'
                "exit 1\n"
            )
            gh.chmod(0o755)
            (Path(tmp) / "runs.json").write_text(json.dumps(runs))

            env = dict(os.environ)
            env["PATH"] = f"{stub_bin}:{env['PATH']}"
            env["GH_TOKEN"] = "t"
            env["REPOSITORY"] = "o/r"
            env["MAX_ATTEMPTS"] = "0"
            env["MAX_AGE_HOURS"] = "999999"

            proc = subprocess.run(
                ["bash", str(SCRIPT)],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            reruns = read_text(str(rerun_log)).split() if rerun_log.exists() else []
            return proc, reruns

    def test_revives_the_newest_cancelled_run_when_the_branch_is_idle(self) -> None:
        proc, reruns = self._run(
            [
                _run_record(2, "cancelled", "completed"),
                _run_record(1, "success", "completed"),
            ]
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(reruns, ["2"])

    def test_leaves_the_branch_alone_while_a_run_is_still_active(self) -> None:
        proc, reruns = self._run(
            [
                _run_record(3, "cancelled", "completed"),
                _run_record(2, "", "pending"),
            ]
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(reruns, [])
        self.assertIn("still active", proc.stdout)

    def test_a_queued_run_counts_as_active_too(self) -> None:
        proc, reruns = self._run(
            [
                _run_record(4, "cancelled", "completed"),
                _run_record(3, "", "queued"),
            ]
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(reruns, [])


if __name__ == "__main__":
    unittest.main()
