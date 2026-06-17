"""Lint: EVERY addon of EVERY role ships a per-addon Playwright spec.

For each ``roles/<role>/meta/addons/<id>.yml`` a spec MUST exist at
``roles/<role>/files/playwright/addons/<id>.spec.js``. There is no exemption:
no mechanism auto-exempt and no ``# nocheck`` escape. Every addon is a
declared behaviour of the deployment and therefore carries its own spec
(gated with ``skipUnlessAddonEnabled`` so it skips cleanly when the addon is
not enabled in the current variant).
"""

from __future__ import annotations

import unittest

from utils.update.addons import iter_addon_files

from . import PROJECT_ROOT


class TestAddonsPlaywrightSpec(unittest.TestCase):
    def test_every_addon_has_a_spec(self) -> None:
        roles_root = PROJECT_ROOT / "roles"
        if not roles_root.is_dir():
            self.skipTest("no roles/ directory")

        errors: list[str] = []
        for role, addon_file in iter_addon_files(roles_root):
            addon_id = addon_file.stem
            rel = addon_file.relative_to(PROJECT_ROOT).as_posix()
            spec_path = (
                roles_root
                / role
                / "files"
                / "playwright"
                / "addons"
                / f"{addon_id}.spec.js"
            )
            if not spec_path.is_file():
                errors.append(
                    f"{role}: addons.{addon_id} has no Playwright spec at "
                    f"{spec_path.relative_to(PROJECT_ROOT).as_posix()} "
                    f"(declared in {rel}); every addon MUST ship a spec."
                )

        if errors:
            self.fail(
                f"playwright per-addon spec violations ({len(errors)}):\n"
                + "\n".join(f"  - {e}" for e in errors)
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
