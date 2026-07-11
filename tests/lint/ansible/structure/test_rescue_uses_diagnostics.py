"""Every Ansible ``rescue:`` block MUST end with the single SPOT diagnostics
script ``scripts/system/diagnostics/rescue.sh`` run via
``ansible.builtin.script``.

Why
---

Rescue blocks used to carry ad-hoc, per-role failure dumps (container logs,
debug tables, fail messages) that drifted apart and captured different
subsets. The SPOT script captures a full snapshot (all containers with their
logs and inspect, all swarm services with ps and logs, the journal, host
resources) into a folder CI uploads as an artifact, prints one condensed
summary, and always exits 1 so the deploy still fails. Standardising every
rescue on it means one place to improve diagnostics and a uniform, uploadable
failure bundle for every role.

Exception
---------

A rescue block MAY carry exactly one extra task *before* the script call, for
role-specific detail the generic script cannot capture (e.g. Postgres dumping
``pg_hba.conf`` and its auth test). That extra task MUST carry a same-block
``# nocheck: <why>`` comment justifying why the extra diagnostics are needed.
Anything more than one extra task, or an extra task without a justification,
is an offender.

A whole rescue block is exempt when its first task carries a
``# nocheck: rescue-recovery <why>`` comment. This is for the rare block that
must genuinely recover (not just diagnose): a swarm cross-node reschedule needs
a swarm-wide node re-resolve plus a change of ``delegate_to``, which Ansible can
only express by catching the failure and retrying, and which a diagnostics-only
rescue structurally cannot do (see ``web-app-keycloak`` object updates).
"""

from __future__ import annotations

import os
import re
import unittest

from ruamel.yaml import (
    YAML,
)  # nocheck: direct-yaml — this lint needs task line numbers the yaml cache does not expose

from utils.cache.files import iter_project_files_with_content

from . import PROJECT_ROOT

SCRIPT_MARKER = "scripts/system/diagnostics/rescue.sh"
SCRIPT_MODULES = {"ansible.builtin.script", "script"}
_NOCHECK_RE = re.compile(r"#\s*nocheck\b")
_RECOVERY_RE = re.compile(r"#\s*nocheck:\s*rescue-recovery\b")
_yaml = YAML()


def _is_ansible_task_file(rel_path: str) -> bool:
    if not rel_path.startswith(("roles/", "tasks/")):
        return False
    if not rel_path.endswith((".yml", ".yaml")):
        return False
    return "/tasks/" in rel_path or "/handlers/" in rel_path


def _script_value(task: dict) -> str | None:
    for module in SCRIPT_MODULES:
        if module in task:
            value = task[module]
            if isinstance(value, str):
                return value
            if isinstance(value, dict):
                return str(value.get("cmd", ""))
    return None


def _iter_rescue_seqs(node):
    """Yield every ``rescue`` task list found anywhere in the structure."""
    if isinstance(node, list):
        for item in node:
            yield from _iter_rescue_seqs(item)
    elif isinstance(node, dict):
        for key, value in node.items():
            if key == "rescue" and isinstance(value, list):
                yield value
            yield from _iter_rescue_seqs(value)


class TestRescueUsesDiagnostics(unittest.TestCase):
    def test_rescue_blocks_only_call_the_diagnostics_script(self):
        offenders: list[str] = []

        for abs_path, content in iter_project_files_with_content(
            extensions=(".yml", ".yaml")
        ):
            rel_path = os.path.relpath(abs_path, PROJECT_ROOT)
            if not _is_ansible_task_file(rel_path):
                continue
            if "rescue:" not in content:
                continue
            try:
                doc = _yaml.load(content)  # nocheck: direct-yaml — line-aware parse
            except Exception:
                continue
            lines = content.splitlines()

            for rescue in _iter_rescue_seqs(doc):
                tasks = [t for t in rescue if isinstance(t, dict)]
                if not tasks:
                    offenders.append(f"{rel_path}: empty rescue block")
                    continue
                if _RECOVERY_RE.search(lines[tasks[0].lc.line]):
                    continue
                if len(tasks) > 2:
                    offenders.append(
                        f"{rel_path}: rescue block has {len(tasks)} tasks; "
                        f"only {SCRIPT_MARKER} plus at most one justified extra "
                        "task are allowed"
                    )
                    continue

                value = _script_value(tasks[-1])
                if value is None or SCRIPT_MARKER not in value:
                    offenders.append(
                        f"{rel_path}: last rescue task must run {SCRIPT_MARKER} "
                        "via ansible.builtin.script"
                    )
                    continue

                if len(tasks) == 2:
                    span = lines[tasks[0].lc.line : tasks[1].lc.line]
                    if not any(_NOCHECK_RE.search(line) for line in span):
                        offenders.append(
                            f"{rel_path}: the extra rescue task before "
                            f"{SCRIPT_MARKER} must carry a same-block "
                            "'# nocheck: <why>' comment justifying the extra "
                            "diagnostics"
                        )

        self.assertFalse(
            offenders,
            "rescue blocks must end with an ansible.builtin.script call to "
            f"{SCRIPT_MARKER} (plus at most one nocheck-justified extra task):\n"
            + "\n".join(f"  - {o}" for o in offenders),
        )


if __name__ == "__main__":
    unittest.main()
