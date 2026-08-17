"""Lint guard: baudolo is pinned to one version, not two.

`svc-bkp-volume-2-local` pip-installs baudolo on the target host, while
`[project.dependencies]` declares it for the control host, whose
`utils.recovery` imports `baudolo.restore.paths` to read the generation layout.
Two pins mean the code that reads a backup can be a different version from the
one that wrote it, and the mismatch surfaces as a restore that finds nothing.
"""

from __future__ import annotations

import re
import tomllib
import unittest

from utils.cache.files import read_text

from . import PROJECT_ROOT

_PACKAGE = "backup-docker-to-local"
_PYPROJECT = PROJECT_ROOT / "pyproject.toml"
_INSTALL_TASK = PROJECT_ROOT / "roles/svc-bkp-volume-2-local/tasks/01_install.yml"
_TASK_PIN_RE = re.compile(rf"{re.escape(_PACKAGE)}==([0-9][^\"'\s]*)")


def _declared_pin() -> str | None:
    data = tomllib.loads(read_text(str(_PYPROJECT)))
    for requirement in data.get("project", {}).get("dependencies", []):
        if requirement.startswith(f"{_PACKAGE}=="):
            return requirement.split("==", 1)[1].strip()
    return None


class TestBaudoloPin(unittest.TestCase):
    def test_the_role_installs_the_declared_version(self) -> None:
        declared = _declared_pin()
        self.assertIsNotNone(
            declared,
            f"{_PACKAGE} must be pinned in [project.dependencies] of {_PYPROJECT}",
        )

        found = _TASK_PIN_RE.findall(read_text(str(_INSTALL_TASK)))
        self.assertEqual(
            found,
            [declared],
            f"{_INSTALL_TASK} pins {found}, while pyproject.toml declares "
            f"'{declared}'. Both must name the same version.",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
