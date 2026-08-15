"""Build the CI deploy matrix of one sweep, chunk by chunk.

Usage:
  python -m cli.meta.ci.matrix --index N [--sweep S] [--modes auto]
      [--whitelist "..."] [--priority "..."] [--lifecycles "..."] [--tor auto]

This is the pipeline the deploy jobs discover through, and the single place
the run's shape is decided:

1. Two discovery queries, keeping today's filter semantics: the priority line
   is queried on its own whitelist so priority roles run even when the
   diff-derived whitelist would not have selected them, and the regular line
   is queried on the effective whitelist with the priority roles blacklisted.
   Concatenated, they are the sweep's ordered candidate list. Both lists are
   selection tokens (:mod:`utils.github.variant.selection`): what a token pins
   narrows the row, what it leaves open the line decides as it always did.
2. Every row is assigned its deploy mode and tor state by its position in
   that list (:mod:`utils.github.variant.axes`).
3. The list is cut into serial chunks with a hard boundary at the
   priority/regular seam (:mod:`cli.meta.ci.chunks`), sized by the run's job
   and queue budget (:mod:`cli.meta.ci.slots`).

``--index`` then prints one chunk as the matrix JSON. Every chunk block runs
the same computation and takes its own slice, so the blocks agree without
passing state between them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from cli.meta.ci import chunks, query, slots
from utils.cache.applications import get_variants
from utils.github.variant import axes, selection
from utils.roles.display import display_names


def candidates(
    *,
    modes: tuple[str, ...],
    whitelist: str,
    priority: str,
    lifecycles: str,
) -> list[dict]:
    """The sweep's ordered candidate rows: priority line first, then the
    regular line, each annotated with the modes it offers and whether it is
    priority."""
    leading = selection.parse_list(priority)
    keep = selection.parse_list(whitelist)
    rows: list[dict] = []
    if leading:
        rows += [
            {**row, "priority": True}
            for row in selection.apply(
                query.discover_rows(
                    modes, whitelist=selection.names(leading), lifecycles=lifecycles
                ),
                leading,
            )
        ]
    rows += [
        {**row, "priority": False}
        for row in selection.apply(
            query.discover_rows(
                modes,
                whitelist=selection.names(keep),
                blacklist=selection.names(leading),
                lifecycles=lifecycles,
            ),
            keep,
        )
    ]
    return [{**row, "modes": query.row_modes(row, modes)} for row in rows]


def entries_of(
    *,
    modes: tuple[str, ...],
    whitelist: str,
    priority: str,
    lifecycles: str,
    sweep: int,
    tor_mode: str,
) -> list[dict[str, str]]:
    """Every candidate row of the sweep, axes assigned, in global order."""
    return axes.assign(
        candidates(
            modes=modes,
            whitelist=whitelist,
            priority=priority,
            lifecycles=lifecycles,
        ),
        sweep=sweep,
        tor_mode=tor_mode,
        variants_per_app=get_variants(),
    )


def chunks_of(entries: list[dict[str, str]], sweep: int) -> list[list[dict[str, str]]]:
    """Cut the sweep's entries into its chunks, priority blocks first.

    Which rows a chunk holds follows the discovery ranking; the order *inside*
    a chunk is then sorted (:func:`utils.github.variant.axes.sort_key`), so the
    job list of a chunk reads by role rather than by the sweep's rotation."""
    return [
        sorted(chunk, key=axes.sort_key)
        for chunk in chunks.plan(
            [entry for entry in entries if entry["priority"] == "true"],
            [entry for entry in entries if entry["priority"] != "true"],
            sweep=sweep,
            size=slots.chunk_size(),
            blocks=slots.chunk_count(),
            budget=slots.available(),
        )
    ]


def build_sweep(
    *,
    modes: tuple[str, ...],
    whitelist: str,
    priority: str,
    lifecycles: str,
    sweep: int,
    tor_mode: str,
) -> list[list[dict[str, str]]]:
    """Every chunk of the sweep, priority blocks first."""
    return chunks_of(
        entries_of(
            modes=modes,
            whitelist=whitelist,
            priority=priority,
            lifecycles=lifecycles,
            sweep=sweep,
            tor_mode=tor_mode,
        ),
        sweep,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the CI deploy matrix of one sweep chunk."
    )
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--sweep", type=int, default=None)
    parser.add_argument("--modes", default=query.ALL_MODES)
    parser.add_argument("--whitelist", default="")
    parser.add_argument("--priority", default="")
    parser.add_argument("--lifecycles", default="")
    parser.add_argument("--tor", default=None)
    args = parser.parse_args(argv)

    codec = display_names()
    if args.lifecycles.strip():
        os.environ["INFINITO_LIFECYCLES"] = args.lifecycles

    sweep = axes.resolve_sweep() if args.sweep is None else args.sweep
    plan = build_sweep(
        modes=query.resolve_modes(args.modes),
        whitelist=codec.decode_list(args.whitelist),
        priority=codec.decode_list(args.priority),
        lifecycles=args.lifecycles,
        sweep=sweep,
        tor_mode=axes.resolve_tor_mode(args.tor),
    )
    chunk = plan[args.index] if 0 <= args.index < len(plan) else []
    dropped = ("priority", "weight", "id", "covered")
    print(json.dumps([{k: v for k, v in e.items() if k not in dropped} for e in chunk]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
