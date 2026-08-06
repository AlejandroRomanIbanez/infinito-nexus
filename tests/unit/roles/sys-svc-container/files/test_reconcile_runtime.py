import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from utils import PROJECT_ROOT
from utils.cache.files import read_text

SCRIPT = PROJECT_ROOT / "roles/sys-svc-container/files/reconcile_runtime.sh"

SYSTEMCTL_STUB = """#!/usr/bin/env bash
echo "systemctl $*" >>"$STUB_LOG"
case "$1" in
show)
\tcase "$4" in
\tcontainerd.service) echo "$STUB_CONTAINERD_STARTED" ;;
\tdocker.service) echo "$STUB_DOCKER_STARTED" ;;
\tesac
\t;;
list-units) printf '%s\\n' "$STUB_SCOPES" ;;
esac
exit 0
"""

DOCKER_STUB = """#!/usr/bin/env bash
echo "docker $*" >>"$STUB_LOG"
printf '%s\\n' "$STUB_KNOWN"
"""


class TestReconcileRuntime(unittest.TestCase):
    def run_script(self, *, containerd_started, docker_started, scopes, known):
        """Run the script against stubbed systemctl/docker.

        Args:
            containerd_started: ActiveEnterTimestampMonotonic of containerd.
            docker_started: ActiveEnterTimestampMonotonic of dockerd.
            scopes: newline separated `systemctl list-units` output.
            known: newline separated container ids dockerd still knows.

        Returns:
            Tuple of the script's stdout and the recorded stub invocations.
        """
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            log = bin_dir / "calls.log"
            for name, body in (
                ("systemctl", SYSTEMCTL_STUB),
                ("docker", DOCKER_STUB),
            ):
                stub = bin_dir / name
                stub.write_text(body)
                stub.chmod(0o755)
            env = dict(os.environ)
            env.update(
                PATH=f"{bin_dir}{os.pathsep}{env['PATH']}",
                STUB_LOG=str(log),
                STUB_CONTAINERD_STARTED=str(containerd_started),
                STUB_DOCKER_STARTED=str(docker_started),
                STUB_SCOPES=scopes,
                STUB_KNOWN=known,
            )
            done = subprocess.run(
                ["bash", str(SCRIPT)],
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            calls = read_text(str(log)) if log.exists() else ""
            return done.stdout, calls

    def test_healthy_start_order_changes_nothing(self):
        stdout, calls = self.run_script(
            containerd_started=100,
            docker_started=200,
            scopes="docker-aaa.scope loaded active running",
            known="bbb",
        )
        self.assertIn("UNCHANGED", stdout)
        self.assertNotIn("restart", calls)
        self.assertNotIn("stop", calls)

    def test_containerd_restart_reaps_untracked_scope_and_restarts_docker(self):
        stdout, calls = self.run_script(
            containerd_started=300,
            docker_started=200,
            scopes="docker-orphan.scope loaded active running\ndocker-live.scope loaded active running",
            known="live",
        )
        self.assertIn("RECONCILED: 1 orphaned container scope(s)", stdout)
        self.assertIn("systemctl stop docker-orphan.scope", calls)
        self.assertNotIn("docker-live.scope", calls.split("systemctl stop ")[1])
        self.assertIn("systemctl restart docker.service", calls)

    def test_containerd_restart_without_orphans_still_restarts_docker(self):
        stdout, calls = self.run_script(
            containerd_started=300,
            docker_started=200,
            scopes="docker-live.scope loaded active running",
            known="live",
        )
        self.assertIn("RECONCILED: 0 orphaned container scope(s)", stdout)
        self.assertNotIn("systemctl stop", calls)
        self.assertIn("systemctl restart docker.service", calls)


if __name__ == "__main__":
    unittest.main()
