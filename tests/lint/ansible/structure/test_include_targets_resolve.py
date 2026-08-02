"""Every static ``include_tasks`` target must resolve to exactly one file.

Rationale
=========
A relative include is resolved at RUNTIME. A typo, or a file moved into a
subdirectory without updating its includers, therefore survives every static
gate: ``ansible-lint`` passes, and ``ansible-playbook --syntax-check`` never
parses a dynamically included task file at all. The play dies mid-deploy,
after everything before it has already run.

The second failure mode is worse because it is silent. Ansible searches
several roots for a relative include, so a bare ``foo.yml`` can match both the
including file's own directory and the role's ``tasks/`` directory. Whichever
root wins, the other file is shadowed and nobody notices until the wrong tasks
run.

Detection enumerates the roots Ansible searches for a role-relative include --
the including file's own directory, the role's ``tasks/`` directory, the role
root and the project root, each also probed with a ``tasks/`` prefix (which is
what makes the shared ``utils/once/flag.yml`` style includes resolve) -- and
requires exactly one of them to hold the file. Templated targets (``{{ … }}``)
are skipped unless the task carries a literal ``loop:`` list, in which case
every list entry is checked.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from utils.cache.yaml import load_yaml_any

from . import PROJECT_ROOT

INCLUDE_KEYS = (
    "include_tasks",
    "ansible.builtin.include_tasks",
    "import_tasks",
    "ansible.builtin.import_tasks",
)
SEARCH_PREFIXES = ("", "tasks")


def _iter_tasks(node: Any):
    if isinstance(node, list):
        for item in node:
            yield from _iter_tasks(item)
    elif isinstance(node, dict):
        yield node
        for key in ("block", "rescue", "always"):
            yield from _iter_tasks(node.get(key))


def _include_targets(task: dict) -> list[str]:
    for key in INCLUDE_KEYS:
        value = task.get(key)
        if isinstance(value, dict):
            value = value.get("file")
        if not isinstance(value, str):
            continue
        if "{{" not in value:
            return [value]
        loop = task.get("loop")
        if isinstance(loop, list):
            return [i for i in loop if isinstance(i, str) and "{{" not in i]
        return []
    return []


def _search_roots(task_file: Path, role_dir: Path) -> list[Path]:
    return [task_file.parent, role_dir / "tasks", role_dir, PROJECT_ROOT]


def _distinct_hits(target: str, roots: list[Path]) -> list[Path]:
    hits = [
        root / prefix / target for root in roots for prefix in SEARCH_PREFIXES
    ]
    resolved = {h.resolve() for h in hits if h.is_file()}
    return sorted(resolved)


class TestIncludeTargetsResolve(unittest.TestCase):
    def test_every_static_include_resolves_uniquely(self) -> None:
        findings: list[str] = []

        for role_dir in sorted((PROJECT_ROOT / "roles").iterdir()):
            tasks_dir = role_dir / "tasks"
            if not tasks_dir.is_dir():
                continue
            for task_file in sorted(tasks_dir.rglob("*.yml")):
                document = load_yaml_any(task_file)
                if not isinstance(document, list):
                    continue
                roots = _search_roots(task_file, role_dir)
                for task in _iter_tasks(document):
                    if not isinstance(task, dict):
                        continue
                    for target in _include_targets(task):
                        hits = _distinct_hits(target, roots)
                        rel = task_file.relative_to(PROJECT_ROOT).as_posix()
                        if not hits:
                            searched = ", ".join(
                                r.relative_to(PROJECT_ROOT).as_posix() or "."
                                for r in roots
                            )
                            findings.append(
                                f"{rel}: '{target}' resolves to no file "
                                f"(searched under {searched})"
                            )
                        elif len(hits) > 1:
                            shown = ", ".join(
                                h.relative_to(PROJECT_ROOT).as_posix() for h in hits
                            )
                            findings.append(
                                f"{rel}: '{target}' is ambiguous -- it matches "
                                f"{shown}"
                            )

        self.assertFalse(
            findings,
            f"{len(findings)} static include target(s) do not resolve to "
            "exactly one file. A missing target kills the play at runtime, "
            "and an ambiguous one silently runs whichever file Ansible's "
            "search order happens to reach first. Point the include at a "
            "path that is unique across the including file's directory, the "
            "role's tasks/ directory, the role root and the project root:\n"
            + "\n".join(findings),
        )


if __name__ == "__main__":
    unittest.main()
