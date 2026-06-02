from __future__ import annotations

import re
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from utils.cache.files import iter_project_files, read_text

from . import PROJECT_ROOT

if TYPE_CHECKING:
    from collections.abc import Iterable

SCAN_DIRS = ("roles", "tasks", "playbooks")
MAX_NAME_LENGTH = 120
NOCHECK_TOKEN = "nocheck: name-length"

# Matches `- name: <value>` (quoted or unquoted, with or without list dash).
# Captures the value so its length can be measured without surrounding YAML noise.
_NAME_LINE_RE = re.compile(
    r"""^\s*
        -?\s*                       # optional list dash
        name\s*:\s*                 # the key
        (?:
          "(?P<dq>(?:[^"\\]|\\.)*)" # double-quoted value
        | '(?P<sq>(?:[^'\\]|'')*)'  # single-quoted value
        | (?P<bare>[^#\n].*?)       # bare value (stops at end-of-line; trailing comment trimmed below)
        )
        \s*(?:\#.*)?$
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class Finding:
    file: Path
    line: int
    length: int
    snippet: str

    def format(self, repo_root: Path) -> str:
        rel = self.file.relative_to(repo_root).as_posix()
        return f"{rel}:{self.line}: name is {self.length} chars (limit {MAX_NAME_LENGTH}): {self.snippet[:80]}..."


def _extract_name_value(match: re.Match[str]) -> str:
    if match.group("dq") is not None:
        return match.group("dq")
    if match.group("sq") is not None:
        return match.group("sq")
    return (match.group("bare") or "").strip()


def _iter_yaml_files(repo_root: Path) -> Iterable[Path]:
    for path_str in iter_project_files(extensions=(".yml", ".yaml")):
        rel = Path(path_str).relative_to(repo_root)
        if rel.parts and rel.parts[0] in SCAN_DIRS:
            yield Path(path_str)


def _scan_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = read_text(str(path))
    except (OSError, UnicodeDecodeError):
        return findings

    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if NOCHECK_TOKEN in line:
            continue
        match = _NAME_LINE_RE.match(line)
        if not match:
            continue
        value = _extract_name_value(match)
        if len(value) > MAX_NAME_LENGTH:
            findings.append(
                Finding(file=path, line=idx, length=len(value), snippet=value)
            )
    return findings


class TestTaskNameLength(unittest.TestCase):
    def test_task_name_length_under_limit(self) -> None:
        """Ansible task `name:` strings MUST stay under 120 chars.

        Long task names bloat the playbook output, mangle CI tail-style logs,
        and signal that rationale was inlined where a code comment or the role
        README would serve better. Append `# nocheck: name-length` to opt a
        single line out when the long name is genuinely the clearest signal
        (rare).
        """
        findings: list[Finding] = []
        for yml in _iter_yaml_files(PROJECT_ROOT):
            findings.extend(_scan_file(yml))

        if findings:
            formatted = "\n".join(f.format(PROJECT_ROOT) for f in findings)
            self.fail(
                f"{len(findings)} Ansible task name(s) exceed "
                f"{MAX_NAME_LENGTH} chars:\n{formatted}"
            )


if __name__ == "__main__":
    unittest.main()
