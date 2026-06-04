"""Block raw `container_name: ...` YAML keys in Jinja templates under
roles/*/templates/ (scans every .j2 file recursively, including
compose.override.yml.j2 and other compose.*.yml.j2 variants).

container_name is illegal alongside swarm-mode replicas > 1, so all
compose.yml.j2 templates must route through the `compose_container_name`
lookup (plugins/lookup/compose_container_name.py) which suppresses the key
in swarm mode.

Suppress this rule with `# nocheck: container-name` on the same line or
the immediately preceding non-empty line if the literal key is genuinely
required at a substitution point (rare).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from utils.annotations.suppress import is_suppressed_at
from utils.cache.files import iter_project_files, read_text

from . import PROJECT_ROOT

_RAW_LINE = re.compile(r"(?m)^\s*container_name\s*:")

# Block sweep-mistake forms that pass the raw-key lint but break at render time:
#   1) Split Jinja: {{ lookup('compose_container_name', A }}-{{ B) }}
#      The outer `{{ }}` closes mid-call. Jinja parse error.
#   2) Embedded Jinja in literal string: {{ lookup(..., "{{ X }}_suffix") }}
#      Currently rendered via Ansible's recursive templating; removed in
#      ansible-core 2.23. Use tilde concat: `X ~ '_suffix'`.
# Both regexes accept single- OR double-quoted lookup name and span multiple
# lines (DOTALL via negated character classes already covers newlines).
_LOOKUP_NAME = r"""['"]compose_container_name['"]"""
_BROKEN_SPLIT = re.compile(
    rf"lookup\(\s*{_LOOKUP_NAME}\s*,[^)]*\}}\}}[^{{]*\{{\{{",
)
_BROKEN_EMBED = re.compile(
    rf"lookup\(\s*{_LOOKUP_NAME}\s*,\s*['\"][^'\"]*\{{\{{",
)

_RULE = "container-name"


def _candidate_paths() -> list[Path]:
    out: list[Path] = []
    for s in iter_project_files():
        p = Path(s)
        if p.suffix.lower() != ".j2":
            continue
        try:
            rel = p.relative_to(PROJECT_ROOT)
        except ValueError:
            continue
        parts = rel.parts
        if len(parts) >= 3 and parts[0] == "roles" and "templates" in parts:
            out.append(p)
    return out


class TestNoRawContainerName(unittest.TestCase):
    def test_raw_container_name_is_forbidden_in_templates(self) -> None:
        offenders: list[str] = []
        for path in _candidate_paths():
            try:
                text = read_text(str(path))
            except (OSError, UnicodeDecodeError):
                continue
            if "container_name" not in text:
                continue
            lines = text.splitlines()
            # Combine matches from all three regexes; _BROKEN_SPLIT and
            # _BROKEN_EMBED scan the FULL text so multi-line broken forms also
            # surface (the negated char classes already span newlines).
            hits: set[int] = set()
            for m in _RAW_LINE.finditer(text):
                hits.add(text[: m.start()].count("\n") + 1)
            for m in _BROKEN_SPLIT.finditer(text):
                hits.add(text[: m.start()].count("\n") + 1)
            for m in _BROKEN_EMBED.finditer(text):
                hits.add(text[: m.start()].count("\n") + 1)

            for idx in sorted(hits):
                if is_suppressed_at(lines, idx, _RULE):
                    continue
                rel = path.relative_to(PROJECT_ROOT)
                line_snip = lines[idx - 1].strip() if 1 <= idx <= len(lines) else ""
                offenders.append(f"{rel}:{idx}: {line_snip}")

        if offenders:
            self.fail(
                "Raw `container_name:` keys found in templates. Route through "
                "the `compose_container_name` lookup "
                "(plugins/lookup/compose_container_name.py) so swarm-mode "
                "replicas do not collide on the static name, or annotate the "
                f"line with `# nocheck: {_RULE}` if the literal key is "
                "genuinely required:\n  - " + "\n  - ".join(offenders)
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
