"""Forbid multi-line inline Python embedded in non-Python files.

A Python body that spans more than one line lives in its own ``.py`` file.
The caller runs that file (``python3 <file>.py``), feeds it on stdin
(``container exec -i <cid> python3 - <args> < <file>.py``), or, from Ansible,
uses ``ansible.builtin.script`` with ``executable`` set to the interpreter.

Why
---
* Code inside a shell, YAML or Dockerfile string couples several quoting
  layers (YAML, Jinja, the shell, Python) in one scalar; a quote in one layer
  silently ends another.
* A ``.py`` file is formatted, linted and unit-tested like the rest of the
  Python in this repository; a heredoc body is none of these.

What this lint flags
--------------------
In every tracked file that is not Python, Markdown or a translation catalog
(``.po``, which quotes the docs), outside ``tests/`` and ``docs/``, a Python
invocation (``python``, ``python3``, ``python3.N``,
``${PYTHON}``, ``{{ ansible_python_interpreter }}``) that:

1. passes ``-c <quote>`` whose closing quote is on a later line;
2. reads a heredoc (``<<EOF``, ``<<-EOF``, ``<<'EOF'``) whose body has at
   least one line;
3. passes ``-c "$var"`` / ``-c "${var}"``, a script held in a variable.

A one-line ``python3 -c 'import x; print(x.y)'`` is fine.

Suppression: ``# nocheck: inline-python`` on the line or the line above, with
the reason the code cannot move.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from utils.annotations.suppress import is_suppressed_at
from utils.cache.files import iter_project_files, read_text

from . import PROJECT_ROOT

RULE = "inline-python"
SKIPPED_SUFFIXES = (".py", ".pyc", ".md", ".po", ".png", ".jpg", ".svg", ".ico", ".gz")
SKIPPED_DIRS = ("tests", "docs")

_PY = r"(?:\bpython(?:3(?:\.\d+)?)?\b|\$\{?PYTHON\}?|\{\{\s*ansible_python_interpreter\s*\}\})"
_DASH_C_OPEN = re.compile(_PY + r"[^\n]*?\s-c\s+(?P<q>['\"])")
_DASH_C_VAR = re.compile(_PY + r"[^\n]*?\s-c\s+\"?\$\{?\w+\}?\"?(?:\s|$)")
_HEREDOC_OPEN = re.compile(
    _PY + r"[^\n]*?<<-?\s*(?P<mq>['\"]?)(?P<mark>[A-Za-z_][A-Za-z0-9_]*)(?P=mq)"
)


def _has_unescaped(segment: str, quote: str) -> bool:
    for index, char in enumerate(segment):
        if char != quote:
            continue
        backslashes = len(segment[:index]) - len(segment[:index].rstrip("\\"))
        if backslashes % 2 == 0:
            return True
    return False


def _quote_close(lines: list[str], start: int, quote: str, column: int) -> int | None:
    if _has_unescaped(lines[start][column:], quote):
        return start
    for index in range(start + 1, len(lines)):
        if _has_unescaped(lines[index], quote):
            return index
    return None


def _heredoc_close(lines: list[str], start: int, marker: str) -> int | None:
    for index in range(start + 1, len(lines)):
        if lines[index].strip() == marker:
            return index
    return None


def findings_in(rel: str, lines: list[str]) -> list[str]:
    """Return ``<rel>:<line>: <shape>`` for every inline Python body.

    Args:
        rel: the file's repository-relative path, used in each finding.
        lines: the file's lines.
    """
    found: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if "python" not in line.lower():
            index += 1
            continue
        end = None
        shape = ""
        match = _DASH_C_OPEN.search(line)
        if match:
            close = _quote_close(lines, index, match.group("q"), match.end())
            if close is not None and close > index:
                end, shape = close, f"python -c {match.group('q')}…"
        if end is None and _DASH_C_VAR.search(line):
            end, shape = index, "python -c $script"
        match = _HEREDOC_OPEN.search(line)
        if end is None and match:
            close = _heredoc_close(lines, index, match.group("mark"))
            if close is not None and close > index + 1:
                end, shape = close, f"python <<{match.group('mark')}"
        if end is not None and not is_suppressed_at(lines, index + 1, RULE):
            found.append(f"{rel}:{index + 1}: {shape}")
        index = (end if end is not None else index) + 1
    return found


def _scanned_files():
    for raw in iter_project_files(exclude_dirs=SKIPPED_DIRS):
        path = Path(raw)
        if path.name.endswith(SKIPPED_SUFFIXES):
            continue
        yield path


class TestNoInlineMultilinePython(unittest.TestCase):
    def test_no_inline_python_bodies(self) -> None:
        offenders: list[str] = []
        for path in _scanned_files():
            try:
                text = read_text(str(path))
            except (OSError, UnicodeDecodeError):
                continue
            rel = path.relative_to(PROJECT_ROOT).as_posix()
            offenders += findings_in(rel, text.splitlines())
        if offenders:
            self.fail(
                f"{len(offenders)} inline Python bodies. Move each into its own .py "
                "file and run it, feed it on stdin (`python3 - <args> < <file>.py`), "
                "or use ansible.builtin.script with `executable`; mark a body that "
                f"cannot move with `# nocheck: {RULE}` and the reason:\n"
                + "\n".join(f"  - {item}" for item in offenders)
            )


class TestFindings(unittest.TestCase):
    def test_a_multiline_dash_c_is_found(self) -> None:
        lines = ["python3 -c '", "import sys", "print(sys.argv)", "' a"]
        self.assertEqual(findings_in("x.sh", lines), ["x.sh:1: python -c '…"])

    def test_a_one_line_dash_c_is_fine(self) -> None:
        self.assertEqual(
            findings_in("x.sh", ["python3 -c 'import sys; print(sys.argv)' a"]), []
        )

    def test_a_heredoc_with_arguments_is_found(self) -> None:
        lines = ['python3 - "$a" "$b" <<\'PY\'', "import sys", "PY"]
        self.assertEqual(findings_in("x.sh", lines), ["x.sh:1: python <<PY"])

    def test_the_ansible_interpreter_heredoc_is_found(self) -> None:
        lines = ["    {{ ansible_python_interpreter }} - <<'EOF'", "    import ldap", "    EOF"]
        self.assertEqual(findings_in("t.yml", lines), ["t.yml:1: python <<EOF"])

    def test_a_script_held_in_a_variable_is_found(self) -> None:
        lines = ['NFS="$(python3 -c "${_nfs_py}" backed-up)"']
        self.assertEqual(findings_in("x.sh", lines), ["x.sh:1: python -c $script"])

    def test_a_project_python_variable_is_recognised(self) -> None:
        lines = ['KEY="$("${PYTHON}" -c "', "print(1)", '")"']
        self.assertEqual(findings_in("x.sh", lines), ['x.sh:1: python -c "…'])

    def test_running_a_python_file_is_fine(self) -> None:
        lines = ['python3 "$(dirname "$0")/check.py" "$1"', 'python3 - "$1" < "$0.py"']
        self.assertEqual(findings_in("x.sh", lines), [])

    def test_a_marker_suppresses_with_its_reason(self) -> None:
        lines = [
            "# nocheck: inline-python  the image has no room for a second file",
            "python3 -c '",
            "print(1)",
            "'",
        ]
        self.assertEqual(findings_in("x.sh", lines), [])


if __name__ == "__main__":
    unittest.main()
