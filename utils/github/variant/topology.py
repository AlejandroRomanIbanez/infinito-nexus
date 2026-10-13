"""The database topology axis (``standalone`` or ``ha``) of the CI deploy matrix."""

from __future__ import annotations

import os

TOPOLOGIES = ("standalone", "ha")

TOPOLOGY_MODES = ("swarm",)

_TRUTHY = ("1", "true", "on", "yes", "enabled")


def resolve_db_topology(raw: str | None = None) -> bool:
    """Whether the db topology axis is on, from ``INFINITO_CI_DB_TOPOLOGY``.

    Args:
        raw: explicit value; ``None`` reads the environment. The workflow
            feeds it from its ``db_topology`` dispatch input or, failing that,
            the repository variable of the same name.

    Returns:
        ``True`` only for an explicit truthy value; anything else keeps the
        axis off and every swarm row standalone.
    """
    if raw is None:
        raw = os.environ.get("INFINITO_CI_DB_TOPOLOGY")
    return (raw or "").strip().lower() in _TRUTHY


def pick_topology(position: int, sweep: int) -> str:
    """The database topology a regular swarm row deploys this sweep."""
    return TOPOLOGIES[(position + sweep // 4) % len(TOPOLOGIES)]


def topologies(
    mode: str, *, enabled: bool, priority: bool, position: int, sweep: int
) -> tuple[str, ...]:
    """The db topologies one (row, mode) deploys: none outside swarm or with
    the axis off, both for a priority row, the rotation's pick otherwise."""
    if not enabled or mode not in TOPOLOGY_MODES:
        return ("",)
    if priority:
        return TOPOLOGIES
    return (pick_topology(position, sweep),)


def matrix_keys(topology: str) -> dict[str, str]:
    """The matrix keys one entry carries for *topology*.

    Emitted on every entry, axis on or off, because the deploy workflow reads
    both and GitHub resolves a missing key to the empty string silently.
    """
    return {
        "db_topology": topology,
        "kill_primary": "true" if topology == "ha" else "false",
    }
