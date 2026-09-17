"""Semver primitives shared by every version-bump backend.

A "version" here is a tag of the shape
``v?<numeric-semver><patch>?(-<flavor>)?``, where the numeric part has 1 to 5
dot-separated components, the optional ``<patch>`` is a vendor counter written
as a letter and a number (e.g. the Checkmk tag ``2.4.0p32``), and the optional
``-<flavor>`` suffix is an opaque discriminator (e.g. the Docker Official Image
tag ``5.4.5-php8.3-apache`` or the npm-style ``1.2.3-alpha``).

Upgrade candidates MUST share the same depth (1 to 5 components) AND the same
flavor as the current tag, so that ``5.4.5-php8.3-apache`` never silently bumps
to ``5.4.6-php8.4-apache`` (different runtime) or to ``5.4.6`` (different
depth). The patch letter joins the flavor and its number joins the ordering
key, which is what keeps ``2.4.0p32`` ordering against ``2.4.0p33`` and never
against the four-component ``2.4.0.32``.
"""

from __future__ import annotations

import os
import re

_SEMVER_CORE = r"v?\d+(?:\.\d+){0,4}"
_VERSIONED_TAG_RE = re.compile(
    rf"^(?P<semver>{_SEMVER_CORE})(?P<patch>[A-Za-z]\d+)?(?P<flavor>-\S+)?$"
)


def _parse_versioned_tag(tag: str) -> tuple[str, str, int | None] | None:
    match = _VERSIONED_TAG_RE.match(str(tag).strip())
    if match is None:
        return None
    patch = match.group("patch")
    flavor = (match.group("flavor") or "") + (patch[0] if patch else "")
    return match.group("semver"), flavor, int(patch[1:]) if patch else None


def is_semver(value: str) -> bool:
    return _parse_versioned_tag(value) is not None


def version_key(tag: str) -> tuple[int, ...]:
    parsed = _parse_versioned_tag(tag)
    if parsed is None:
        return (0,) * 4
    semver, _flavor, patch = parsed
    parts = tuple(int(part) for part in semver.lstrip("v").split("."))
    padded = parts + (0,) * (4 - len(parts))
    return padded if patch is None else (*padded, patch)


def version_depth(tag: str) -> int:
    parsed = _parse_versioned_tag(tag)
    if parsed is None:
        return 0
    semver, _flavor, _patch = parsed
    return len(semver.lstrip("v").split("."))


def version_flavor(tag: str) -> str:
    """Return the ``-<flavor>`` suffix of a versioned tag, or "" when none."""
    parsed = _parse_versioned_tag(tag)
    return parsed[1] if parsed else ""


def latest_semver(tags: list[str], depth: int, flavor: str = "") -> str | None:
    candidates = [
        tag
        for tag in tags
        if is_semver(tag)
        and version_depth(tag) == depth
        and version_flavor(tag) == flavor
    ]
    return max(candidates, key=version_key, default=None)


def resolve_max_fetch_workers() -> int:
    return int(os.environ["INFINITO_WORKER_FETCH"])
