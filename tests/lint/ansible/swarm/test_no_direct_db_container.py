"""Forbid direct ``container`` uses of ``lookup('database')`` / ``lookup('engine')``.

In HA form a central engine has no single container: ``container`` becomes a
shell expression that resolves the current primary at call time. A caller
that treats it as a plain name (a ``--filter name=``, a network disconnect, a
compose cid) breaks silently once the engine gains hosts. Use ``address`` inside
a shell command, or ``swarm/resolve/primary.yml`` for node + container id.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from utils.cache.files import iter_project_files_with_content

from . import PROJECT_ROOT

_DIRECT_CONTAINER = re.compile(
    r"lookup\(\s*['\"](?:database|engine)['\"][^)]*,\s*['\"]container['\"]\s*\)"
)


def _direct_uses() -> dict[str, int]:
    found: dict[str, int] = {}
    for path_str, content in iter_project_files_with_content(
        extensions=(".yml", ".yaml", ".j2"),
        exclude_tests=True,
    ):
        rel = Path(path_str).relative_to(PROJECT_ROOT).as_posix()
        if not rel.startswith("roles/"):
            continue
        hits = len(_DIRECT_CONTAINER.findall(content))
        if hits:
            found[rel] = hits
    return found


class TestNoDirectDbContainer(unittest.TestCase):
    def test_no_direct_container_uses(self) -> None:
        found = _direct_uses()
        if found:
            self.fail(
                "Direct lookup('database'|'engine', ..., 'container') uses. "
                "In HA form 'container' resolves the primary at call time and is "
                "no plain name. Use 'address' inside a shell command or "
                "roles/sys-svc-compose/tasks/utils/swarm/resolve/primary.yml.\n"
                + "\n".join(f"- {p}: {c}" for p, c in sorted(found.items()))
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
