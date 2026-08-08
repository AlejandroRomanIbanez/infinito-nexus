"""Read a lint tool's pinned release from the ``sys-lint`` role.

``roles/sys-lint/meta/services.yml`` is the SPOT for both the repository and
the version of every GitHub-release lint tool. Each entry carries the
``repository`` / ``ref`` pair that ``utils.update.repository`` already scans,
so the existing ``update-repository-refs`` CI job bumps the pins to the latest
semver tag and opens a PR -- the same machinery that keeps ``roles/pkgmgr``
current.

The installers therefore never ask GitHub which version is current: that made
every install non-reproducible and turned a DNS hiccup into a hard
`make install-lint` failure.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from utils import PROJECT_ROOT
from utils.cache.yaml import load_yaml_any
from utils.roles.mapping import ROLE_FILE_META_SERVICES

if TYPE_CHECKING:
    from pathlib import Path

_SLUG_RE = re.compile(r"github\.com[/:](?P<slug>[^/]+/[^/]+?)(?:\.git)?/?$")


def pinned_release(tool: str, roles_dir: Path | None = None) -> tuple[str, str]:
    """The ``(owner/repo, version)`` ``roles/sys-lint`` pins for *tool*.

    Args:
        tool: the tool's service key, e.g. ``actionlint``.
        roles_dir: roles tree to read; defaults to the project's own.

    Returns:
        the GitHub slug and the version without a leading ``v``.

    Raises:
        RuntimeError: the services file, the ``repository`` or the ``ref`` is
            missing or malformed. Guessing any of them would install a tool
            nobody chose.
    """
    root = roles_dir if roles_dir is not None else PROJECT_ROOT / "roles"
    path = root / "sys-lint" / ROLE_FILE_META_SERVICES
    data = load_yaml_any(str(path), default_if_missing=None)
    if data is None:
        raise RuntimeError(f"No release pin for {tool}: {path} is missing or empty.")

    entry = data.get(tool) if isinstance(data, dict) else None
    repository = entry.get("repository") if isinstance(entry, dict) else None
    ref = entry.get("ref") if isinstance(entry, dict) else None
    if not isinstance(ref, str) or not ref.strip():
        raise RuntimeError(f"No release pin for {tool}: {path} declares no ref.")
    if not isinstance(repository, str) or not repository.strip():
        raise RuntimeError(f"No release pin for {tool}: {path} declares no repository.")

    match = _SLUG_RE.search(repository.strip())
    if not match:
        raise RuntimeError(
            f"Cannot derive a GitHub slug for {tool} from {repository!r} in {path}."
        )
    return match["slug"], ref.strip().lstrip("v")


def resolve_release(tool: str, roles_dir: Path | None = None) -> tuple[str, str]:
    """The ``(owner/repo, version)`` an installer should fetch for *tool*.

    Args:
        tool: the tool's service key, e.g. ``actionlint``.
        roles_dir: roles tree to read; defaults to the project's own.

    Returns:
        the pinned slug, and the pinned version unless ``<TOOL>_VERSION`` in
        the environment overrides it for a one-off install.
    """
    slug, version = pinned_release(tool, roles_dir)
    override = os.environ.get(f"{tool.upper()}_VERSION", "").lstrip("v")
    return slug, override or version


__all__ = ["pinned_release", "resolve_release"]
