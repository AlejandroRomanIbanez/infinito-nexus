"""Render the deploy plan of a CI run, one section per deploy mode.

Usage:
  python -m cli.meta.ci.plan --distros "debian" [--whitelist "..."]
      [--priority "..."] [--modes "swarm compose host"] [--lifecycles "..."]
      [--cli]

Every section runs the production discovery query (cli.meta.ci.query,
the same SPOT scripts/meta/resolve/apps.sh uses) three times: the
priority line, the capped regular line, and the uncapped candidate list.
Rows keep the query's own order, so the budget cut is visible: starred
priority rows first, then the regular rows the run actually triggers,
then the candidates that fell behind the cap or the coverage dedup.
One row per variant; a triggered role runs every variant row.

``--cli`` renders fixed-width terminal tables instead of Markdown.
"""

from __future__ import annotations

import argparse
import os
import sys

from cli.meta.ci.query import MODES, discover, max_jobs
from cli.meta.roles.applications.complexity.model import compute_complexity_rows
from utils.cache.files import PROJECT_ROOT
from utils.symbol_glossary import to_emoji

_STAR = to_emoji("priority")
_OK = to_emoji("enabled")
_OFF = to_emoji("disabled")

_COLUMNS = ("name", "weight", "priority", "variant", "distros")
_HEADERS = (
    *(f"{to_emoji(key)} {key.capitalize()}" for key in _COLUMNS),
    f"{to_emoji('enabled')} Triggered",
)


def collect_mode_plan(
    mode: str, *, whitelist: str, priority: str, lifecycles: str = ""
) -> list[tuple[str, str]]:
    """Ordered ``(role, status)`` pairs for one mode: priority-line roles
    first (⭐, query order), then every uncapped candidate in query order
    with ✅ when the capped regular query triggers it, ❌ otherwise."""
    rows: list[tuple[str, str]] = []
    if priority.strip():
        rows += [
            (role, _STAR)
            for role in discover(
                mode, whitelist=priority, lifecycles=lifecycles, capped=True
            )
        ]
    triggered = set(
        discover(
            mode,
            whitelist=whitelist,
            blacklist=priority,
            lifecycles=lifecycles,
            capped=True,
        )
    )
    rows += [
        (role, _OK if role in triggered else _OFF)
        for role in discover(
            mode,
            whitelist=whitelist,
            blacklist=priority,
            lifecycles=lifecycles,
            capped=False,
        )
    ]
    return rows


def role_facts(lifecycles: str = "") -> tuple[dict[str, int], dict[str, int]]:
    envelope = set(lifecycles.replace(",", " ").split()) or None
    weights: dict[str, int] = {}
    variants: dict[str, int] = {}
    for row in compute_complexity_rows(PROJECT_ROOT / "roles", lifecycles=envelope):
        weights[row.name] = row.weight
        variants[row.name] = row.variants
    return weights, variants


def _cells(
    rows: list[tuple[str, str]],
    weights: dict[str, int],
    variants: dict[str, int],
    *,
    priority: str,
    distros: str,
) -> list[tuple[str, ...]]:
    priority_roles = set(priority.split())
    return [
        (
            role,
            str(weights.get(role, 0)),
            _STAR if role in priority_roles else "",
            str(variant),
            distros,
            status,
        )
        for role, status in rows
        for variant in range(variants.get(role, 1))
    ]


def render_markdown(
    sections: list[tuple[str, int, list[tuple[str, ...]]]],
) -> str:
    lines = ["## Deploy plan 🧭"]
    for mode, budget, cells in sections:
        lines += [
            "",
            f"### {to_emoji(mode)} {mode} (max jobs: {budget})",
            "",
            "| " + " | ".join(_HEADERS) + " |",
            "|" + "---|" * len(_HEADERS),
        ]
        lines += ["| " + " | ".join(cell) + " |" for cell in cells]
    return "\n".join(lines)


def render_cli(
    sections: list[tuple[str, int, list[tuple[str, ...]]]],
) -> str:
    widths = [
        max([len(header), *(len(cell[i]) for _, _, cells in sections for cell in cells)])
        for i, header in enumerate(_HEADERS)
    ]
    blocks = []
    for mode, budget, cells in sections:
        title = f"{to_emoji(mode)} {mode} (max jobs: {budget})"
        header = "  ".join(h.ljust(w) for h, w in zip(_HEADERS, widths, strict=True))
        rule = "  ".join("-" * w for w in widths)
        rows = [
            "  ".join(
                value.ljust(w) for value, w in zip(cell, widths, strict=True)
            )
            for cell in cells
        ]
        blocks.append("\n".join([title, header, rule, *rows]))
    return "\n\n".join(blocks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the CI deploy plan, one section per deploy mode."
    )
    parser.add_argument("--distros", default="")
    parser.add_argument("--whitelist", default="")
    parser.add_argument("--priority", default="")
    parser.add_argument("--modes", default="")
    parser.add_argument("--lifecycles", default="")
    parser.add_argument("--cli", action="store_true")
    args = parser.parse_args(argv)

    if args.lifecycles.strip():
        os.environ["INFINITO_LIFECYCLES"] = args.lifecycles

    active = [m for m in MODES if m in args.modes.split()] or list(MODES)
    weights, variants = role_facts(args.lifecycles)
    sections = []
    for mode in active:
        rows = collect_mode_plan(
            mode,
            whitelist=args.whitelist,
            priority=args.priority,
            lifecycles=args.lifecycles,
        )
        cells = _cells(
            rows, weights, variants, priority=args.priority, distros=args.distros
        )
        sections.append((mode, max_jobs(mode), cells))

    render = render_cli if args.cli else render_markdown
    print(render(sections))
    return 0


if __name__ == "__main__":
    sys.exit(main())
