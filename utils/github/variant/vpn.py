"""The WireGuard-mesh axis of a deploy row."""

from __future__ import annotations

import os

VPN_MODES = ("auto", "enforced", "disabled")
"""How a run treats the axis. ``auto`` rotates it, the other two hold every
meshable row on one side so a whole sweep can be spent proving that side.
There is no ``exclusive``: every meshable row can take the mesh, so there is
nothing to drop."""

VPN_DEPLOY_MODES = ("swarm", "compose")
"""Modes the axis applies to. Every row in one of them carries the mesh or
direct glyph; a compose row takes the mesh only on its role's smallest variant
(:func:`meshable`)."""


def meshable(mode: str, *, smallest: bool = False) -> bool:
    """Whether a row in *mode* can carry the mesh.

    Args:
        mode: the deploy mode of the row.
        smallest: whether the row deploys its role's smallest variant.
    """
    if mode == "compose":
        return smallest
    return mode in VPN_DEPLOY_MODES


def resolve_vpn_mode(raw: str | None = None) -> str:
    """Mesh axis mode from ``INFINITO_VPN``; unknown or empty means ``auto``.

    Args:
        raw: explicit value; ``None`` reads the environment.

    Returns:
        one of :data:`VPN_MODES`.
    """
    if raw is None:
        raw = os.environ.get("INFINITO_VPN")
    value = (raw or "").strip().lower()
    return value if value in VPN_MODES else "auto"


def vpn_states(
    mode: str, *, vpn_mode: str = "auto", smallest: bool = False
) -> list[bool]:
    """The mesh states *mode* is worth running for a priority row."""
    if not meshable(mode, smallest=smallest):
        return [False]
    if vpn_mode == "enforced":
        return [True]
    if vpn_mode == "disabled":
        return [False]
    return [False, True]


def pinned_vpn_states(
    mode: str,
    *,
    pin: bool | None = None,
    vpn_mode: str = "auto",
    smallest: bool = False,
) -> list[bool]:
    """The mesh states a priority row takes, global axis ahead of the pin.

    Args:
        mode: the deploy mode of the row.
        pin: the state the row asked for, or None for every state.
        vpn_mode: the run's axis mode.
        smallest: whether the row deploys its role's smallest variant.
    """
    states = vpn_states(mode, vpn_mode=vpn_mode, smallest=smallest)
    if vpn_mode in ("enforced", "disabled") or pin is None:
        return states
    return [state for state in states if state == pin]


def wants_vpn(position: int, sweep: int) -> bool:
    """Whether a meshable row carries the mesh this sweep.

    Reads the position's second digit. The mode rotation spends the first:
    ``(position + sweep) % 2`` decides which parity of rows deploys in swarm,
    so a mesh rotation on the same digit held every swarm row of a sweep on
    one arm and a default run never compared the two.
    """
    return (position // 2 + sweep // 4) % 2 == 0


def rotated_vpn(
    mode: str,
    *,
    position: int,
    sweep: int,
    pin: bool | None = None,
    vpn_mode: str = "auto",
    smallest: bool = False,
) -> bool:
    """The single mesh state a regular row takes this sweep."""
    if not meshable(mode, smallest=smallest):
        return False
    if vpn_mode in ("enforced", "disabled"):
        return vpn_mode == "enforced"
    if pin is not None:
        return pin
    return wants_vpn(position, sweep)
