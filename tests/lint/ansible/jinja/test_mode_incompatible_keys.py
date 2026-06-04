"""Block raw YAML keys that are incompatible between docker-compose and
swarm deployment modes.

Each rule corresponds to a service-level YAML key whose semantics differ
between the two modes. Render paths must route through the appropriate
SPOT lookup (defined in `plugins/lookup/`) which suppresses or rewrites
the key per `DEPLOYMENT_MODE`.

Currently enforced rules:

* ``container-name`` -> ``compose_container_name`` lookup. Hard-rejected
  in swarm when ``deploy.replicas > 1`` (deploy fails outright).
* ``restart-key`` -> ``compose_restart`` lookup. Silently ignored in
  swarm (operator's ``docker_restart_policy`` is dropped, swarm uses
  whatever ``deploy.restart_policy.condition`` is set to).

Suppress per offending line with ``# nocheck: <rule-name>`` either on
the same line or the line above.

Adding a new rule: append a ``ModeRule`` to ``_RULES``. The scaffolding
(file walk, suppression, line-grouping) is shared.
"""

from __future__ import annotations

import re
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from utils.annotations.suppress import is_suppressed_at
from utils.cache.files import iter_project_files, read_text

from . import PROJECT_ROOT


@dataclass(frozen=True)
class ModeRule:
    name: str
    description: str
    raw_regex: re.Pattern[str]
    remediation: str
    extra_regexes: tuple[re.Pattern[str], ...] = field(default_factory=tuple)


# container-name regexes -------------------------------------------------
_CN_RAW = re.compile(r"(?m)^\s*container_name\s*:")
_CN_LOOKUP_NAME = r"""['"]compose_container_name['"]"""
# Split-Jinja form: lookup(..., A }}-{{ B) -> jinja parse error.
_CN_BROKEN_SPLIT = re.compile(
    rf"lookup\(\s*{_CN_LOOKUP_NAME}\s*,[^)]*\}}\}}[^{{]*\{{\{{",
)
# Embedded-Jinja-in-literal-string: lookup(..., "{{ X }}_suffix")
# Deprecated in ansible-core 2.23.
_CN_BROKEN_EMBED = re.compile(
    rf"lookup\(\s*{_CN_LOOKUP_NAME}\s*,\s*['\"][^'\"]*\{{\{{",
)

# restart-key regex ------------------------------------------------------
_RESTART_RAW = re.compile(r"(?m)^\s*restart\s*:")

_RULES: tuple[ModeRule, ...] = (
    ModeRule(
        name="container-name",
        description=(
            "Raw `container_name:` collides with swarm-mode replicas > 1 "
            "and aborts `docker stack deploy`."
        ),
        raw_regex=_CN_RAW,
        extra_regexes=(_CN_BROKEN_SPLIT, _CN_BROKEN_EMBED),
        remediation=(
            "Route through the `compose_container_name` lookup "
            "(plugins/lookup/compose_container_name.py) so swarm-mode "
            "replicas do not collide on the static name. The lookup "
            "expects a single string argument: "
            "`{{ lookup('compose_container_name', MY_CONTAINER) }}`."
        ),
    ),
    ModeRule(
        name="restart-key",
        description=(
            "Top-level `restart:` is silently ignored by swarm (replaced "
            "by `deploy.restart_policy`), producing warnings and "
            "double-declared intent."
        ),
        raw_regex=_RESTART_RAW,
        remediation=(
            "Route through the `compose_restart` lookup "
            "(plugins/lookup/compose_restart.py). With no argument it "
            "defers to `docker_restart_policy`/`DOCKER_RESTART_POLICY` "
            "(matching the previous direct rendering): "
            "`{{ lookup('compose_restart') }}`. Pass an explicit policy "
            "if a service needs an override: "
            "`{{ lookup('compose_restart', 'on-failure') }}`."
        ),
    ),
)


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


def _hits_for(text: str, rule: ModeRule) -> set[int]:
    hits: set[int] = set()
    for regex in (rule.raw_regex, *rule.extra_regexes):
        for m in regex.finditer(text):
            hits.add(text[: m.start()].count("\n") + 1)
    return hits


# Fast pre-filter substrings per rule: skip the regex if the literal key
# does not appear in the file at all. Cheap text-membership check.
_PREFILTER: dict[str, tuple[str, ...]] = {
    "container-name": ("container_name",),
    "restart-key": ("restart:",),
}


class TestModeIncompatibleKeys(unittest.TestCase):
    def test_no_mode_incompatible_keys_in_templates(self) -> None:
        offenders_by_rule: dict[str, list[str]] = {r.name: [] for r in _RULES}

        for path in _candidate_paths():
            try:
                text = read_text(str(path))
            except (OSError, UnicodeDecodeError):
                continue
            lines = text.splitlines()
            rel = path.relative_to(PROJECT_ROOT)

            for rule in _RULES:
                needles = _PREFILTER.get(rule.name, ())
                if needles and not any(n in text for n in needles):
                    continue
                hits = _hits_for(text, rule)
                for idx in sorted(hits):
                    if is_suppressed_at(lines, idx, rule.name):
                        continue
                    line_snip = lines[idx - 1].strip() if 1 <= idx <= len(lines) else ""
                    offenders_by_rule[rule.name].append(f"{rel}:{idx}: {line_snip}")

        sections: list[str] = []
        for rule in _RULES:
            items = offenders_by_rule[rule.name]
            if not items:
                continue
            sections.append(
                f"[{rule.name}] {rule.description}\n"
                f"  Fix: {rule.remediation}\n"
                f"  Suppress per line with `# nocheck: {rule.name}` if "
                "the literal key is genuinely required.\n"
                "  Offenders:\n    - " + "\n    - ".join(items)
            )

        if sections:
            self.fail(
                "Mode-incompatible YAML keys found in templates:\n\n"
                + "\n\n".join(sections)
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
