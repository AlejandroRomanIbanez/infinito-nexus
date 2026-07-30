"""Contract of the shared worktree metadata helpers.

``worktree_unregister`` is what lets a teardown succeed under the agent sandbox,
which pins some files inside ``.git/worktrees/<id>`` as read-only bind mounts so
the directory cannot be unlinked. Its three outcomes drive both callers: fully
removed, unregistered but pinned, and still registered. The last one is the only
state that keeps a branch claimed, so it must never be reported as success.
"""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from utils.cache.files import PROJECT_ROOT

LIB = PROJECT_ROOT / "scripts" / "system" / "worktree" / "lib.sh"


def _call(func: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", f'source "$1"; shift; {func} "$@"', "bash", str(LIB), *args],
        capture_output=True,
        text=True,
    )


class TestWorktreeMetaDir(unittest.TestCase):
    def test_reads_the_gitdir_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".git").write_text("gitdir: /somewhere/.git/worktrees/feat\n")
            result = _call("worktree_meta_dir", tmp)
        self.assertEqual(result.stdout.strip(), "/somewhere/.git/worktrees/feat")

    def test_missing_git_file_yields_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _call("worktree_meta_dir", tmp)
        self.assertEqual(result.stdout.strip(), "")

    def test_directory_git_yields_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".git").mkdir()
            result = _call("worktree_meta_dir", tmp)
        self.assertEqual(result.stdout.strip(), "")


class TestWorktreeUnregister(unittest.TestCase):
    def _entry(self, tmp: str) -> Path:
        entry = Path(tmp) / "feat"
        entry.mkdir()
        (entry / "gitdir").write_text("/checkout/.git\n")
        (entry / "HEAD").write_text("ref: refs/heads/feat\n")
        (entry / "commondir").write_text("../..\n")
        return entry

    def test_removes_the_whole_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entry = self._entry(tmp)
            result = _call("worktree_unregister", str(entry))
            self.assertEqual(result.returncode, 0)
            self.assertFalse(entry.exists())

    def test_pinned_directory_still_unregisters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entry = self._entry(tmp)
            parent_mode = os.stat(tmp).st_mode
            (entry / "gitdir").unlink()
            (entry / "HEAD").unlink()
            os.chmod(tmp, parent_mode & ~stat.S_IWUSR)
            try:
                result = _call("worktree_unregister", str(entry))
            finally:
                os.chmod(tmp, parent_mode)
            self.assertEqual(result.returncode, 1)
            self.assertTrue(entry.exists())

    def test_undeletable_pointers_report_still_registered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entry = self._entry(tmp)
            mode = os.stat(entry).st_mode
            os.chmod(entry, mode & ~stat.S_IWUSR)
            try:
                result = _call("worktree_unregister", str(entry))
            finally:
                os.chmod(entry, mode)
            self.assertEqual(result.returncode, 2)
            self.assertTrue((entry / "gitdir").exists())

    def test_is_idempotent_on_a_half_emptied_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entry = self._entry(tmp)
            (entry / "HEAD").unlink()
            result = _call("worktree_unregister", str(entry))
            self.assertEqual(result.returncode, 0)
            self.assertFalse(entry.exists())


if __name__ == "__main__":
    unittest.main()
