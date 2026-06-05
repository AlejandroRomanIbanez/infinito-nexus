"""Drift guard: every `template:` task that ships a ``.conf.j2`` file
must adopt the project's :mod:`plugins.action.conf_template` wrapper.

The wrapper folds the ``IS_STACK_HOST`` gate into the module so callers
do not silently fail on worker hosts whose nginx/etc tree is owned
exclusively by the stack host (the failure pattern that bit
web-app-prometheus in CI run 27034636121). Keeping the bare
``template:`` module reachable for ``.conf.j2`` payloads re-opens that
class of bug.

Detection
=========
Line-based scan of every ``.yml`` file in the project. A finding is
recorded when:

* a line opens a ``template:`` (or ``ansible.builtin.template:``) task,
  AND
* the next ``src:`` line on the same task contains a ``.conf.j2``
  literal.

Escape hatch
============
Add ``# nocheck: conf-template`` on the ``template:`` line, on the
``src:`` line, or anywhere else inside the task body when the bare
``template:`` is genuinely required (e.g. the wrapper itself must not
self-call, a destination is provably worker-local, or the task is
inside a fixture). Use sparingly — each suppression is a missed SPOT.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from utils.cache.files import iter_project_files_with_content

from . import PROJECT_ROOT

TEMPLATE_MODULE_PATTERN = re.compile(
    r"^(?P<indent>\s*)-?\s*(ansible\.builtin\.template|template)\s*:\s*(?:#.*)?$"
)
SRC_LINE_PATTERN = re.compile(r"^\s*src\s*:\s*[\"']?(?P<src>[^\"'\s#]+)")
NOCHECK_MARKER = "nocheck: conf-template"


def _find_task_block_end(lines: list[str], start_idx: int, base_indent: int) -> int:
    """Walk forward from start_idx until the indentation drops to or
    below base_indent (== a new sibling task or the end of the task
    list). Returns the exclusive end index.
    """
    end = start_idx + 1
    while end < len(lines):
        line = lines[end]
        stripped = line.lstrip()
        if stripped and not stripped.startswith("#"):
            indent = len(line) - len(stripped)
            if indent <= base_indent:
                break
        end += 1
    return end


class TestConfTemplateMigration(unittest.TestCase):
    def test_no_bare_template_for_conf_j2_payloads(self):
        findings: list[tuple[str, int, str]] = []

        for path_str, content in iter_project_files_with_content(extensions=(".yml",)):
            rel = Path(path_str).relative_to(PROJECT_ROOT).as_posix()
            if rel.startswith("tests/lint/"):
                continue

            lines = content.splitlines()
            for idx, line in enumerate(lines):
                match = TEMPLATE_MODULE_PATTERN.match(line)
                if not match:
                    continue
                base_indent = len(match.group("indent"))
                block_end = _find_task_block_end(lines, idx, base_indent)
                block_lines = lines[idx:block_end]

                src_value: str | None = None
                for inner in block_lines[1:]:
                    src_match = SRC_LINE_PATTERN.match(inner)
                    if src_match:
                        src_value = src_match.group("src")
                        break
                if not src_value or ".conf.j2" not in src_value:
                    continue

                if any(NOCHECK_MARKER in inner for inner in block_lines):
                    continue

                findings.append((rel, idx + 1, line.strip()))

        if findings:
            formatted = "\n".join(
                f"- {path}:{line_no}: {snippet}"
                for path, line_no, snippet in sorted(
                    findings, key=lambda item: (item[0], item[1])
                )
            )
            self.fail(
                "Found bare `template:` tasks that ship a `.conf.j2` payload.\n\n"
                "Replace them with `conf_template:` so the IS_STACK_HOST gate is "
                "enforced centrally and worker hosts no longer abort with "
                "'Destination directory does not exist'.\n\n"
                f"If a call site genuinely cannot use the wrapper, suppress with "
                f"`# {NOCHECK_MARKER}` and add a one-line reason.\n\n"
                f"{formatted}"
            )


if __name__ == "__main__":
    unittest.main()
