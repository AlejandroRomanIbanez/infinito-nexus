"""Read the deploy axes an operator pins in ``whitelist`` and ``priority``.

A selection token names a role and MAY narrow the axes that role's rows would
otherwise be assigned: which variants run, which deploy mode, and whether the
row goes behind the node onion. What a token leaves open stays open -- the
priority line then covers every combination of it, the whitelist line lets the
sweep rotation pick one, exactly as an unpinned run does.

Two spellings are accepted, so an operator can either type the token or paste
back the job title of the run they want repeated:

* the job label CI emits (``🚀🧅网络应用·Nextcloud#2``) -- the glyphs carry
  mode and onion state, the ``#`` shard the variants;
* an ASCII form (``web-app-nextcloud#0,2@swarm+tor``).

The onion state spells out as ``+tor``/``+clearnet`` rather than as a ``-tor``
suffix: a role id may itself end in ``-tor`` (``svc-net-tor``), and a suffix
that eats the tail of a role name selects a different role in silence.

Everything a token pins is checked against what the row can actually do
(:func:`utils.github.variant.axes.assign`) and against the run's own mode and
tor inputs. A contradiction aborts the matrix instead of quietly deploying
something else or nothing at all.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

from utils.github.variant.axes import MODES
from utils.roles.display import VARIANT_SEPARATOR, display_names
from utils.symbol_glossary import to_emoji

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from typing import Any

MODE_SEPARATOR = "@"

TOR_SEPARATOR = "+"

TOR_WORDS = {"tor": True, "clearnet": False}

_STRIPPED_GLYPHS = ("priority", "test_host")

_VARIATION = re.compile("[︎️]")

_TOKEN = re.compile(
    r"^(?P<name>[^#@+\s]+)"
    r"(?:" + re.escape(VARIANT_SEPARATOR) + r"(?P<variants>\d+(?:,\d+)*))?"
    r"(?:" + re.escape(MODE_SEPARATOR) + r"(?P<mode>[a-z]+))?"
    r"(?:" + re.escape(TOR_SEPARATOR) + r"(?P<tor>[a-z]+))?$"
)

_SYNTAX = (
    f"<role>[{VARIANT_SEPARATOR}<variant,variant>]"
    f"[{MODE_SEPARATOR}<{'|'.join(MODES)}>]"
    f"[{TOR_SEPARATOR}<{'|'.join(TOR_WORDS)}>]"
)


class Pin(NamedTuple):
    """One selection token, taken apart.

    ``variants`` empty, ``mode`` or ``tor`` ``None`` each mean "not pinned":
    that axis keeps whatever the line it stands in would assign.
    """

    app: str
    variants: tuple[int, ...] = ()
    mode: str | None = None
    tor: bool | None = None

    @property
    def pinned(self) -> bool:
        """Whether the token narrows anything at all beyond the role name."""
        return bool(self.variants) or self.mode is not None or self.tor is not None


def describe(pin: Pin) -> str:
    """The token as an operator would have written it, for error messages."""
    variants = ",".join(str(index) for index in pin.variants)
    return (
        pin.app
        + (f"{VARIANT_SEPARATOR}{variants}" if variants else "")
        + (f"{MODE_SEPARATOR}{pin.mode}" if pin.mode else "")
        + (
            f"{TOR_SEPARATOR}{'tor' if pin.tor else 'clearnet'}"
            if pin.tor is not None
            else ""
        )
    )


def _glyphs(text: str) -> tuple[str, str | None, bool | None]:
    """Take the label glyphs off a pasted job title and read them as axes."""
    mode: str | None = None
    tor: bool | None = None
    for candidate in MODES:
        glyph = to_emoji(candidate)
        if glyph in text:
            mode, text = candidate, text.replace(glyph, "")
    for word, state in TOR_WORDS.items():
        glyph = to_emoji(word)
        if glyph in text:
            tor, text = state, text.replace(glyph, "")
    for word in _STRIPPED_GLYPHS:
        text = text.replace(to_emoji(word), "")
    return text.strip(), mode, tor


def _agree(pin: Any, glyph: Any, token: str, axis: str) -> Any:
    """One axis stated twice must state the same thing."""
    if pin is not None and glyph is not None and pin != glyph:
        raise SystemExit(
            f"selection token {token!r} pins two different {axis} values; "
            f"drop one of them"
        )
    return glyph if pin is None else pin


def parse(token: str) -> Pin:
    """One selection token as a :class:`Pin`.

    Args:
        token: label form or ASCII form; a bare role id or display name pins
            nothing and selects every row of that role.

    Raises:
        SystemExit: the token is unparsable, or names a mode or onion state
            that does not exist. A typo must abort the run rather than narrow
            it to nothing.
    """
    text, glyph_mode, glyph_tor = _glyphs(_VARIATION.sub("", token.strip()))
    match = _TOKEN.match(text)
    if match is None:
        raise SystemExit(f"unparsable selection token {token!r}; expected {_SYNTAX}")

    mode = match.group("mode")
    if mode is not None and mode not in MODES:
        raise SystemExit(
            f"selection token {token!r} names unknown deploy mode {mode!r}; "
            f"expected {', '.join(MODES)}"
        )
    word = match.group("tor")
    if word is not None and word not in TOR_WORDS:
        raise SystemExit(
            f"selection token {token!r} names unknown onion state {word!r}; "
            f"expected {', '.join(TOR_WORDS)}"
        )

    name = match.group("name")
    variants = match.group("variants")
    return Pin(
        display_names().decode(name) or name,
        tuple(int(index) for index in variants.split(",")) if variants else (),
        _agree(mode, glyph_mode, token, "mode"),
        _agree(TOR_WORDS[word] if word else None, glyph_tor, token, "onion"),
    )


def parse_list(tokens: str) -> list[Pin]:
    """Every token of a space-separated ``whitelist``/``priority`` input."""
    return [parse(token) for token in tokens.split()]


def names(pins: Iterable[Pin]) -> str:
    """The role ids the pins select, deduplicated, in the order given -- what
    the discovery query filters on. The axes are applied afterwards, on the
    rows the query returned."""
    return " ".join(dict.fromkeys(pin.app for pin in pins))


def apply(
    rows: Sequence[Mapping[str, Any]], pins: Sequence[Pin]
) -> list[dict[str, Any]]:
    """Keep the rows the pins select and stamp the pinned axes onto them.

    Args:
        rows: discovery rows of one line, in query order.
        pins: that line's selection tokens; empty means "no selection", and
            every row passes through untouched.

    Returns:
        one entry per (row, pin) the selection asks for, each carrying
        ``pin_mode`` and ``pin_tor`` for
        :func:`utils.github.variant.axes.assign` to honour. Order is the
        query's -- a selection narrows what runs, it never re-ranks it.

        A row several tokens name is emitted once per token, which is the whole
        point of the axes: ``role#1@compose+tor role#1@swarm+tor`` is one
        variant that failed in two modes, and it has to come back as two
        deploys. Two tokens narrowing a row the same way collapse into one, so
        a duplicate in the input cannot become two jobs racing for one artifact
        name.

        A bare role name loses to any token that narrows the same row: writing
        ``role role#1@swarm`` asks for a specific deploy, not for that deploy
        plus a rotation-picked one on top.

    Raises:
        SystemExit: a token that pins something matched no row at all. Silently
            deploying nothing is how a mistyped variant index turns into a
            green run that tested nothing.
    """
    if not pins:
        return [dict(row) for row in rows]
    kept: list[dict[str, Any]] = []
    matched: set[int] = set()
    for row in rows:
        hits = [
            (index, pin)
            for index, pin in enumerate(pins)
            if pin.app == row["name"]
            and (not pin.variants or row.get("variant") in pin.variants)
        ]
        matched.update(index for index, _pin in hits)
        narrowing = [(index, pin) for index, pin in hits if pin.pinned]
        seen: set[tuple[str | None, bool | None]] = set()
        for _index, pin in narrowing or hits[:1]:
            if (pin.mode, pin.tor) in seen:
                continue
            seen.add((pin.mode, pin.tor))
            kept.append({**row, "pin_mode": pin.mode, "pin_tor": pin.tor})
    for index, pin in enumerate(pins):
        if index not in matched and pin.pinned:
            raise SystemExit(
                f"selection {describe(pin)!r} matches no discovered row; "
                f"check the variant index and the run's lifecycle/mode filters"
            )
    return kept
