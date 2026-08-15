"""Assign the deploy axes to CI matrix rows.

Every row of the CI matrix is one ``role#variant`` selection. Two axes are
decided here, both as a deterministic rotation over the row's position in the
*global* discovery order and the sweep number -- never at random, so a red job
can be reproduced by re-running the same sweep, and so consecutive sweeps
cover the combinations instead of sampling them:

* **mode** -- which of ``compose``/``swarm``/``host`` the row deploys in,
  drawn from the modes the role actually offers. In practice that is at most
  two: swarm requires the role to ship its own stack, host requires it not to.
  ``(position + sweep) % len(offered)`` therefore flips a row between its two
  modes on consecutive sweeps.

* **tor** -- whether the row deploys behind the node onion. Driven by
  ``sweep // 2`` so it does NOT flip in lockstep with the mode; a row walks
  all four mode/tor combinations over four sweeps instead of only two.

A row's position is its index in the uncapped discovery order, not its index
inside a chunk, so slicing the list into chunks never changes what a row is
assigned.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, NamedTuple

from utils import PROJECT_ROOT
from utils.cache.yaml import load_yaml_any
from utils.roles.display import display_names
from utils.roles.mapping import ROLE_FILE_META_SERVICES
from utils.symbol_glossary import to_emoji, to_word

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import Any

ROLES_DIR = PROJECT_ROOT / "roles"

MODES = ("compose", "swarm", "host")

TOR_MODES = ("auto", "enforced", "exclusive", "disabled")

TOR_DEPLOY_MODES = ("swarm", "compose")

_AXIS_GLYPHS = "".join(to_emoji(word) for word in ("tor", "clearnet", "priority"))

LABEL_RE = re.compile(
    r"^.*(" + "|".join(re.escape(to_emoji(mode)) for mode in MODES) + r")️?"
    r"(" + re.escape(to_emoji("tor")) + r")?"
    r"[" + re.escape(_AXIS_GLYPHS) + r"️\s]*"
    r"(.+?)"
    r"(?:\s+([0-9,]+))?"
    r"[" + re.escape(_AXIS_GLYPHS) + r"️\s]*$"
)
"""The leading ``.*`` is greedy on purpose: it anchors on the LAST mode glyph.
A reusable-workflow caller path can carry a mode glyph of its own (``z / 💻
Host / 💻 sys-front-proxy``), and matching the first one would swallow the
caller name into the role."""


class Label(NamedTuple):
    """One deploy job title, taken apart."""

    mode: str
    name: str
    variant: str
    tor: bool


def parse_label(name: str) -> Label | None:
    """Take a deploy job title apart.

    The inverse of what :func:`assign` builds, kept next to it so the two
    cannot drift: consumers that hand-rolled their own regex over raw role
    ids silently matched nothing once job titles carried display names, and
    every failure went unreported.

    Args:
        name: the job title, with or without a reusable-workflow caller path
            in front of it.

    Returns:
        ``None`` when the title carries no deploy row. ``name`` is the display
        name, returned unresolved -- callers decode it through
        ``utils.roles.display``, which is what knows the role tree. ``tor``
        matters because a priority role runs the same mode and variant twice,
        once behind the onion and once not, and only the glyph tells the two
        jobs apart.
    """
    match = LABEL_RE.match(name.strip())
    if match is None:
        return None
    return Label(
        to_word(match.group(1)),
        match.group(3).strip(),
        (match.group(4) or ""),
        match.group(2) is not None,
    )


def _tor_flag(config: Mapping[str, Any]) -> Any:
    """The ``services.tor.enabled`` value of one config, or ``None`` if unset."""
    services = config.get("services") if isinstance(config, dict) else None
    tor = services.get("tor") if isinstance(services, dict) else None
    return tor.get("enabled") if isinstance(tor, dict) else None


def _base_tor_capable(app: str) -> bool:
    """Read the tor gate straight from the role's ``meta/services.yml``."""
    path = ROLES_DIR / app / ROLE_FILE_META_SERVICES
    if not path.exists():
        return True
    try:
        services = load_yaml_any(path) or {}
    except Exception:  # noqa: BLE001  malformed role meta must not break the matrix
        return True
    return _tor_flag({"services": services}) is not False


def tor_capable(
    app: str,
    variant: int | None = None,
    variants_per_app: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
) -> bool:
    """Whether a matrix row may be deployed behind the node onion.

    Args:
        app: application id.
        variant: the row's variant index; ``None`` for a role declaring none.
        variants_per_app: rendered variant configs per app; ``None`` falls back
            to the role's base ``meta/services.yml``.

    Returns:
        ``False`` when the covered variant pins ``services.tor.enabled`` to a
        literal false, ``True`` otherwise. A reactive Jinja flag counts as
        capable: it is the role saying "onion when the node is dark".
        Consulting the variant matters -- roles pin the gate ``true`` in
        variant 0 and ``false`` in the rest, so reading only the base config
        claims an onion for rounds that deliberately run without one.
    """
    declared = (variants_per_app or {}).get(app) or []
    if variant is None or not 0 <= variant < len(declared):
        return _base_tor_capable(app)
    return _tor_flag(declared[variant]) is not False


def resolve_tor_mode(raw: str | None = None) -> str:
    """Tor axis mode from ``INFINITO_TOR``; unknown or empty means ``auto``.

    Args:
        raw: explicit value; ``None`` reads the environment.

    Returns:
        one of :data:`TOR_MODES`.
    """
    if raw is None:
        raw = os.environ.get("INFINITO_TOR")
    value = (raw or "").strip().lower()
    return value if value in TOR_MODES else "auto"


def resolve_sweep(raw: str | None = None) -> int:
    """Sweep number from ``INFINITO_CI_SWEEP``; it drives both rotations."""
    if raw is None:
        raw = os.environ.get("INFINITO_CI_SWEEP")
    try:
        return int((raw or "0").strip())
    except ValueError:
        return 0


def pick_mode(offered: Sequence[str], position: int, sweep: int) -> str:
    """The deploy mode a row runs in this sweep.

    Args:
        offered: modes the role supports, in a stable order.
        position: the row's index in the global discovery order.
        sweep: sweep number.

    Raises:
        ValueError: *offered* is empty -- a row the query returned always has
            at least one mode, so an empty list is a bug upstream, not a case
            to paper over with a fallback mode.
    """
    if not offered:
        raise ValueError("row offers no deploy mode; the query should have dropped it")
    return offered[(position + sweep) % len(offered)]


def wants_tor(position: int, sweep: int) -> bool:
    """Whether a capable row takes the onion this sweep. Halved on
    ``sweep // 2`` so it does not flip in lockstep with :func:`pick_mode`."""
    return (position + sweep // 2) % 2 == 0


def artifact_slug(mode: str, app: str, variant: str, tor: bool) -> str:
    """What identifies one deploy job's artifacts.

    Built here rather than as a workflow expression so the matrix entry and
    every consumer read the same string: a priority role runs the same mode
    and variant twice, once behind the onion and once not, and two jobs
    uploading under one name is an artifact conflict, not an overwrite.
    """
    return f"{mode}-{app}{f'-{variant}' if variant else ''}{'-tor' if tor else ''}"


def tor_states(mode: str, *, capable: bool, tor_mode: str) -> list[bool]:
    """The onion states one *mode* is worth running for a priority row.

    Args:
        mode: the deploy mode the row runs in.
        capable: whether the row's variant may take an onion at all.
        tor_mode: the run's tor axis.

    Returns:
        ``[True, False]`` on a tor-carrying mode under ``auto`` -- a priority
        row is not sampled, it covers both states in the same sweep. An
        explicit ``enforced``/``exclusive``/``disabled`` is an operator
        narrowing and still wins, and a mode that carries no onion axis at all
        (host) only ever yields the clearnet state.
    """
    if mode not in TOR_DEPLOY_MODES:
        return [False]
    if tor_mode == "disabled":
        return [False]
    if tor_mode in ("enforced", "exclusive"):
        if capable:
            return [True]
        return [] if tor_mode == "exclusive" else [False]
    return [True, False] if capable else [False]


def combinations(
    offered: Sequence[str], *, capable: bool, tor_mode: str
) -> list[tuple[str, bool]]:
    """Every ``(mode, tor)`` pair a priority row is deployed in.

    Priority rows are the ones a run must not sample: they cover the whole
    cross-product of the modes their role offers and the onion states each of
    those modes can take, in one sweep, instead of walking it over four.
    """
    return [
        (mode, enabled)
        for mode in offered
        for enabled in tor_states(mode, capable=capable, tor_mode=tor_mode)
    ]


def assign(
    rows: Sequence[Mapping[str, Any]],
    *,
    sweep: int,
    tor_mode: str,
    variants_per_app: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
) -> list[dict[str, str]]:
    """Turn ordered discovery rows into CI matrix entries.

    Args:
        rows: discovery rows, each carrying ``name``, ``variant``, ``modes``
            (the offered subset) and ``priority``, in global query order.
        sweep: sweep number driving both rotations.
        tor_mode: ``enforced`` onions every capable row, ``disabled`` none,
            ``exclusive`` drops the rows that cannot take one, ``auto``
            rotates.
        variants_per_app: rendered variant configs per app, so a variant that
            switches the tor gate off is never counted capable.

    Returns:
        one entry per (row, mode, tor) the run deploys. A regular row yields
        exactly one -- the rotation picks its combination for this sweep. A
        priority row yields every combination :func:`combinations` allows, so
        the roles a run is told to prove are proven everywhere at once rather
        than sampled over four sweeps. ``disable`` carries the provider tokens
        the deploy drill switches off; a row without tor disables the provider
        so no dependency edge can pull it back into the closure.
    """
    codec = display_names()
    entries: list[dict[str, str]] = []
    for position, row in enumerate(rows):
        app = row["name"]
        variant = row.get("variant")
        priority = bool(row.get("priority"))
        capable = tor_capable(app, variant, variants_per_app)
        offered = tuple(row["modes"])
        if priority:
            picked = combinations(offered, capable=capable, tor_mode=tor_mode)
        else:
            mode = pick_mode(offered, position, sweep)
            picked = [
                (mode, state)
                for state in _rotated_tor(
                    mode,
                    capable=capable,
                    tor_mode=tor_mode,
                    position=position,
                    sweep=sweep,
                )
            ]
        variant_csv = "" if variant is None else str(variant)
        label = codec.encode(app, variant_csv)
        for mode, enabled in picked:
            glyphs = to_emoji(mode) + (
                to_emoji("tor" if enabled else "clearnet")
                if mode in TOR_DEPLOY_MODES
                else ""
            )
            entries.append(
                {
                    "apps": app,
                    "variant": variant_csv,
                    "mode": mode,
                    "tor": "true" if enabled else "false",
                    "disable": "" if enabled else "tor",
                    "priority": "true" if priority else "false",
                    "weight": str(row.get("weight", 0)),
                    "artifact": artifact_slug(mode, app, variant_csv, enabled),
                    "label": f"{glyphs}{label}"
                    + (f" {to_emoji('priority')}" if priority else ""),
                }
            )
    return entries


def _rotated_tor(
    mode: str, *, capable: bool, tor_mode: str, position: int, sweep: int
) -> list[bool]:
    """The single onion state a regular row takes this sweep, or nothing when
    ``exclusive`` drops it."""
    allowed = tor_states(mode, capable=capable, tor_mode=tor_mode)
    if len(allowed) < 2:
        return allowed
    return [capable and wants_tor(position, sweep)]
