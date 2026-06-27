"""Bridge-resolution lint + repo-wide parity for ``meta/addons/*.yml``.

The central rule of the unified addon contract: every addon file with a
non-empty ``bridges:`` list names in-repo cross-role service dependencies, and
each listed service key MUST be declared as a service block in the SAME role's
``meta/services.yml``, carrying the standard ``enabled`` / ``shared`` flags so
the SSO/LDAP/services-parity requirements keep applying unchanged.

This doubles as the repo-wide bridge-parity check: it scans every role and
fails if any addon bridges a service absent from that role's
``meta/services.yml``.

Two meanings of "bridge" must not be conflated:

* the ``bridges:`` *field*: an in-repo cross-role service dependency
  (validated here);
* ``mechanism: bridge``: a network/appservice bridge addon, which is NOT
  required to declare a ``bridges:`` field. It is ignored here unless the addon
  also declares a ``bridges:`` field, in which case that field is validated.

Suppression: ``# nocheck: addon-bridge`` in the head of a
``meta/addons/<id>.yml`` file exempts that addon's bridge resolution.
"""

from __future__ import annotations

import unittest
from collections.abc import Mapping
from typing import TYPE_CHECKING

from utils.annotations.suppress import is_suppressed_in_head
from utils.cache.files import read_text
from utils.cache.yaml import load_yaml_any
from utils.roles.mapping import ROLE_DIR_META_ADDONS, ROLE_FILE_META_SERVICES

from . import PROJECT_ROOT

if TYPE_CHECKING:
    from pathlib import Path

_BRIDGE_RULE = "addon-bridge"


def _service_blocks(role_dir: Path) -> dict[str, Mapping]:
    """Return the top-level service map from a role's meta/services.yml."""
    services_path = role_dir / ROLE_FILE_META_SERVICES
    if not services_path.is_file():
        return {}
    data = load_yaml_any(str(services_path), default_if_missing={}) or {}
    if not isinstance(data, Mapping):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, Mapping)}


class TestAddonsBridges(unittest.TestCase):
    """Hard lint: every addon ``bridges:`` key resolves to a service block."""

    def test_bridges_resolve_to_services(self) -> None:
        roles_root = PROJECT_ROOT / "roles"
        if not roles_root.is_dir():
            self.skipTest("no roles/ directory")

        errors: list[str] = []

        for role_dir in sorted(p for p in roles_root.iterdir() if p.is_dir()):
            addons_dir = role_dir / ROLE_DIR_META_ADDONS
            if not addons_dir.is_dir():
                continue

            role = role_dir.name
            services = _service_blocks(role_dir)

            for addon_file in sorted(addons_dir.glob("*.yml")):
                addon_id = addon_file.stem
                rel = addon_file.relative_to(PROJECT_ROOT).as_posix()
                spec = load_yaml_any(str(addon_file), default_if_missing={}) or {}
                if not isinstance(spec, Mapping):
                    continue
                bridges = spec.get("bridges")
                if not isinstance(bridges, list) or not bridges:
                    continue

                if is_suppressed_in_head(
                    read_text(str(addon_file)).splitlines(), _BRIDGE_RULE
                ):
                    continue

                for target in bridges:
                    if not isinstance(target, str):
                        continue
                    block = services.get(target)
                    if block is None:
                        errors.append(
                            f"{role}: addons.{addon_id} bridges '{target}' but no "
                            f"'{target}:' service block exists in "
                            f"{ROLE_FILE_META_SERVICES}. Add the bridged service "
                            f"block (with enabled/shared flags) or remove the "
                            f"bridge. ({rel})"
                        )
                        continue
                    if "enabled" not in block or "shared" not in block:
                        missing = [
                            flag for flag in ("enabled", "shared") if flag not in block
                        ]
                        errors.append(
                            f"{role}: addons.{addon_id} bridges '{target}' whose "
                            f"service block is missing {missing}; a bridged service "
                            f"MUST carry both 'enabled' and 'shared'. "
                            f"({role}/{ROLE_FILE_META_SERVICES})"
                        )

        if errors:
            self.fail(
                f"addon bridge-resolution violations ({len(errors)}):\n"
                + "\n".join(f"  - {e}" for e in errors)
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
