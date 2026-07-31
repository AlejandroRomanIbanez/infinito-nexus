"""Contract of the docker data-root filesystem resolver.

``resolve.sh`` hands its decision to the next workflow step through
``GITHUB_ENV``, and that step passes it positionally to ``docker_dataroot.sh``.
A key renamed on either side is silent: the applying script receives an empty
string, reports "no filesystem stated", exits 0, and the run goes green with the
feature switched off. Checked here by executing the resolver: the keys it emits
are the keys the workflows read, a stated pick is marked required while a drawn
one is not, a stated pick overrides the pool, and a pick is always drawn from a
pool the target can serve.

The pool contents are policy, not contract, and are deliberately not asserted -
the per-distro expectation is derived from the resolver's own answers.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from utils.cache.files import PROJECT_ROOT, read_text

RESOLVE = (
    PROJECT_ROOT
    / "scripts"
    / "tests"
    / "deploy"
    / "utils"
    / "filesystem"
    / "resolve.sh"
)
WORKFLOWS = [
    PROJECT_ROOT / ".github" / "workflows" / f"test-deploy-{mode}.yml"
    for mode in ("compose", "host", "swarm")
]
CONSUMED = re.compile(r"\$\{(INFINITO_DOCKER_FILESYSTEM[A-Z_]*)\}")
POOL = re.compile(r"random out of '([^']*)'")
ALL_DISTROS = ("arch", "debian", "ubuntu", "fedora", "centos")


class Resolved:
    def __init__(self, stdout: str, env: str):
        self.stdout = stdout
        self.env = dict(line.split("=", 1) for line in env.splitlines() if "=" in line)
        self.picked = self.env["INFINITO_DOCKER_FILESYSTEM"]
        self.required = self.env["INFINITO_DOCKER_FILESYSTEM_REQUIRED"]
        match = POOL.search(stdout)
        self.pool = match.group(1).split() if match else None


def resolve(stated: str, distros: str, scope: str) -> Resolved:
    with tempfile.TemporaryDirectory() as tmp:
        env_file = Path(tmp) / "env"
        summary = Path(tmp) / "summary.md"
        env_file.touch()
        summary.touch()
        env = dict(os.environ)
        env.update(GITHUB_ENV=str(env_file), GITHUB_STEP_SUMMARY=str(summary))
        proc = subprocess.run(
            ["bash", str(RESOLVE), stated, "unit/test", distros, scope],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        return Resolved(proc.stdout, read_text(str(env_file)))


class TestFilesystemResolve(unittest.TestCase):
    def test_the_emitted_keys_are_the_keys_the_workflows_read(self) -> None:
        consumed = set()
        for workflow in WORKFLOWS:
            consumed |= set(CONSUMED.findall(read_text(str(workflow))))
        self.assertEqual(consumed, set(resolve("", "debian", "runner").env))

    def test_a_stated_pick_is_required_and_a_drawn_one_is_not(self) -> None:
        self.assertEqual(resolve("zfs", "debian", "runner").required, "true")
        self.assertEqual(resolve("", "debian", "runner").required, "false")

    def test_a_stated_pick_overrides_the_pool(self) -> None:
        stated = resolve("zfs", " ".join(ALL_DISTROS), "runner")
        self.assertEqual(stated.picked, "zfs")
        self.assertIsNone(stated.pool)

    def test_a_drawn_pick_comes_from_the_reported_pool(self) -> None:
        for scope in ("runner", "node"):
            drawn = resolve("", " ".join(ALL_DISTROS), scope)
            self.assertIn(drawn.picked, drawn.pool)

    def test_the_node_pool_is_what_every_distro_can_serve(self) -> None:
        singles = {d: set(resolve("", d, "node").pool) for d in ALL_DISTROS}
        combined = set(resolve("", " ".join(ALL_DISTROS), "node").pool)
        self.assertEqual(combined, set.intersection(*singles.values()))

    def test_the_runner_pool_ignores_the_distro_list(self) -> None:
        self.assertEqual(
            resolve("", " ".join(ALL_DISTROS), "runner").pool,
            resolve("", "centos", "runner").pool,
        )

    def test_a_missing_scope_is_a_hard_error(self) -> None:
        proc = subprocess.run(
            ["bash", str(RESOLVE), "", "unit/test", "debian"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
