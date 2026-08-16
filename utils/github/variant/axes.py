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
from utils.roles.applications.services.registry import (
    build_service_registry_from_roles_dir,
)
from utils.roles.display import VARIANT_SEPARATOR, display_names
from utils.roles.mapping import ROLE_FILE_META_SERVICES
from utils.symbol_glossary import to_emoji, to_word

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import Any

ROLES_DIR = PROJECT_ROOT / "roles"

MODES = ("compose", "swarm", "host")

TOR_MODES = ("auto", "enforced", "exclusive", "disabled")

TOR_DEPLOY_MODES = ("swarm", "compose")

LOCAL_GLYPH = to_emoji("test_host")

_AXIS_GLYPHS = (
    "".join(to_emoji(word) for word in ("tor", "clearnet", "priority")) + LOCAL_GLYPH
)

LABEL_RE = re.compile(
    r"^.*(" + "|".join(re.escape(to_emoji(mode)) for mode in MODES) + r")️?"
    r"(" + re.escape(to_emoji("tor")) + r")?"
    r"[" + re.escape(_AXIS_GLYPHS) + r"️\s]*"
    r"(.+?)"
    r"(?:" + re.escape(VARIANT_SEPARATOR) + r"([0-9,]+))?"
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


def tor_provider() -> str | None:
    """Application id of the role providing the ``tor`` service, ``None`` if
    the registry names none. Resolved rather than hardcoded so renaming the
    provider role cannot leave the matrix pointing at a dead id."""
    entry = build_service_registry_from_roles_dir(ROLES_DIR).get("tor") or {}
    role = entry.get("role")
    return role if isinstance(role, str) and role else None


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


def _reject(app: str, variant: str, reason: str) -> None:
    """Abort on a selection the row cannot satisfy.

    Raises:
        SystemExit: always. A pin the row cannot take is an operator mistake,
            and dropping the row instead would report a green run for a
            combination that never ran.
    """
    shard = f"{VARIANT_SEPARATOR}{variant}" if variant else ""
    raise SystemExit(f"selection {app}{shard}: {reason}")


def check_pins(
    app: str,
    variant: str,
    offered: Sequence[str],
    *,
    pin_mode: str | None,
    pin_tor: bool | None,
    capable: bool,
    tor_mode: str,
) -> None:
    """Prove the row can take what the selection token pinned on it.

    The offered modes are already narrowed by the run's ``--modes`` input and
    the onion states by its ``--tor`` input, so this catches a pin that fights
    the role, the variant, or the run's own axes with one check each.
    """
    if pin_mode is not None and pin_mode not in offered:
        _reject(
            app,
            variant,
            f"pinned mode {pin_mode!r} is not available here "
            f"(offered: {', '.join(offered)})",
        )
    if pin_tor is None:
        return
    for mode in (pin_mode,) if pin_mode else offered:
        if pin_tor in tor_states(mode, capable=capable, tor_mode=tor_mode):
            return
    _reject(
        app,
        variant,
        f"pinned onion state {'tor' if pin_tor else 'clearnet'} is impossible "
        f"here (mode, variant or the run's tor axis rules it out)",
    )


def sort_key(entry: Mapping[str, str]) -> tuple[Any, ...]:
    """Where one entry sorts inside its chunk: display name, then variant,
    then deploy mode, then onion state.

    The chunk split itself is not sorted -- it follows the discovery ranking,
    which is what decides who makes the budget cut. This only orders the jobs
    a chunk already holds, so a chunk's job list reads like the plan table
    instead of like the sweep's rotation.
    """
    return (
        display_names().encode(entry["apps"]),
        tuple(int(part) for part in entry["variant"].split(",") if part),
        MODES.index(entry["mode"]) if entry["mode"] in MODES else len(MODES),
        entry["tor"] == "true",
    )


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
            ``pin_mode``/``pin_tor``, when a selection token set them, pin that
            axis: the priority line then covers only the combinations that
            match, and the regular line takes the pin instead of its rotation.
        sweep: sweep number driving both rotations.
        tor_mode: ``enforced`` onions every capable row, ``disabled`` none,
            ``exclusive`` drops the rows that cannot take one, ``auto``
            rotates.
        variants_per_app: rendered variant configs per app, so a variant that
            switches the tor gate off is never counted capable.

    Returns:
        one entry per (row, mode, tor) the run deploys, carrying the row's
        discovery ``id`` and the ``covered`` id of the earlier row that already
        embeds it (``0``: nothing does), so a reader of the plan can tell a
        redundant row from a unique one without a second query. A regular row
        yields
        exactly one -- the rotation picks its combination for this sweep. A
        priority row yields every combination :func:`combinations` allows, so
        the roles a run is told to prove are proven everywhere at once rather
        than sampled over four sweeps. ``disable`` carries the provider tokens
        the deploy drill switches off; a row without tor disables the provider
        so no dependency edge can pull it back into the closure. The provider's
        own rows therefore never take the clearnet state: disabling tor there
        would strip the app under test out of its own deploy.
    """
    codec = display_names()
    provider = tor_provider()
    entries: list[dict[str, str]] = []
    for position, row in enumerate(rows):
        app = row["name"]
        variant = row.get("variant")
        priority = bool(row.get("priority"))
        capable = tor_capable(app, variant, variants_per_app)
        offered = tuple(row["modes"])
        variant_csv = "" if variant is None else str(variant)
        pin_mode = row.get("pin_mode")
        pin_tor = row.get("pin_tor")
        check_pins(
            app,
            variant_csv,
            offered,
            pin_mode=pin_mode,
            pin_tor=pin_tor,
            capable=capable,
            tor_mode=tor_mode,
        )
        if priority:
            picked = [
                (mode, state)
                for mode, state in combinations(
                    offered, capable=capable, tor_mode=tor_mode
                )
                if pin_mode in (None, mode) and pin_tor in (None, state)
            ]
        else:
            mode = pin_mode or pick_mode(
                _offering(offered, pin_tor, capable=capable, tor_mode=tor_mode),
                position,
                sweep,
            )
            picked = [
                (mode, state)
                for state in _rotated_tor(
                    mode,
                    capable=capable,
                    tor_mode=tor_mode,
                    position=position,
                    sweep=sweep,
                    pin=pin_tor,
                )
            ]
        if app == provider:
            picked = [(mode, enabled) for mode, enabled in picked if enabled]
        label = codec.encode(app, variant_csv)
        for mode, enabled in picked:
            glyphs = to_emoji(mode) + (
                to_emoji("tor" if enabled else "clearnet")
                if mode in TOR_DEPLOY_MODES
                else LOCAL_GLYPH
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
                    "id": str(row.get("id", 0)),
                    "covered": str(row.get("covered_by", 0)),
                    "clone": "true" if row.get("clone") else "false",
                    "artifact": artifact_slug(mode, app, variant_csv, enabled),
                    "label": f"{glyphs}{label}"
                    + (f" {to_emoji('priority')}" if priority else ""),
                }
            )
    return entries


def _offering(
    offered: Sequence[str], pin: bool | None, *, capable: bool, tor_mode: str
) -> tuple[str, ...]:
    """The modes the rotation may still draw from once an onion state is
    pinned: pinning the onion on a row that also offers host must not rotate
    the row onto host, where no onion exists."""
    if pin is None:
        return tuple(offered)
    return tuple(
        mode
        for mode in offered
        if pin in tor_states(mode, capable=capable, tor_mode=tor_mode)
    )


def _rotated_tor(
    mode: str,
    *,
    capable: bool,
    tor_mode: str,
    position: int,
    sweep: int,
    pin: bool | None = None,
) -> list[bool]:
    """The single onion state a regular row takes this sweep, or nothing when
    ``exclusive`` drops it. A pinned state replaces the rotation -- it was
    proven possible by :func:`check_pins` before we get here."""
    allowed = tor_states(mode, capable=capable, tor_mode=tor_mode)
    if pin is not None:
        return [pin]
    if len(allowed) < 2:
        return allowed
    return [capable and wants_tor(position, sweep)]
