#!/usr/bin/env python3
"""Print, one per line, the role IDs the provision CLI should
``--include`` so the resulting inventory has every group APP_ID's
transitive deps will need at deploy time.

``svc-swarm-manager`` (subset marker),
``svc-storage-nfs-client`` (no ``application_id``) and
``svc-registry-docker`` (consumed by the swarm handler that pushes
locally-built images, but not declared as a meta-dep so it stays
out of compose-mode deploys) are added explicitly because the
dep-walker only knows roles that are in the ``applications`` dict.

Input (env): ``APP_ID``. Optional ``INFINITO_APP_VARIANTS`` (JSON
``{app_id: variant_index}``, set per round by the matrix orchestrator)
selects the active variant so a variant that pins ``services.*`` flags
to ``false`` prunes those providers from the closure instead of the
provision step pulling them in from the variant-free base config.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from utils import PROJECT_ROOT
from utils.cache.applications import get_merged_applications, get_variants
from utils.roles.applications.in_group_deps import applications_if_group_and_all_deps
from utils.roles.applications.services.registry import (
    build_service_registry_from_applications,
)

_ROLES_DIR = PROJECT_ROOT / "roles"

_EXPLICIT_INCLUDES: tuple[str, ...] = (
    "svc-swarm-manager",
    "svc-storage-nfs-client",
    "svc-registry-docker",
)


def _active_variant_map() -> dict[str, int]:
    raw = os.environ.get("INFINITO_APP_VARIANTS")
    if not raw:
        return {}
    try:
        mapping = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(mapping, dict):
        return {}
    return {
        app_id: index
        for app_id, index in mapping.items()
        if isinstance(app_id, str)
        and isinstance(index, int)
        and not isinstance(index, bool)
    }


def _applications_for_active_variants(
    base_applications: dict[str, Any],
) -> dict[str, Any]:
    """Swap every app listed in ``INFINITO_APP_VARIANTS`` to its variant
    config. Index 0 is swapped too: a variant-0 override MAY disable flags
    the base config's dynamic-Jinja form counts as enabled (web-app-nextcloud
    pins 11 partner services off in variant 0), so "variant 0 == base" does
    not hold. Every entry in the map is swapped, not just the primary app,
    because host_vars baking honours the dep roles' indices as well and the
    include closure must match that topology."""
    overrides = _active_variant_map()
    if not overrides:
        return base_applications
    variants_per_app = get_variants(roles_dir=str(_ROLES_DIR))
    applications = dict(base_applications)
    for app_id, index in overrides.items():
        app_variants = variants_per_app.get(app_id) or []
        if 0 <= index < len(app_variants):
            applications[app_id] = app_variants[index]
    return applications


def derive_includes(app_id: str) -> list[str]:
    """Resolve APP_ID's transitive include set under the active variants.

    The service registry (service key -> provider role) stays built from
    the full rendered base set so provider discovery is unaffected by the
    active variants; only the dep-walk sees the variant configs.
    """
    base_applications = get_merged_applications(roles_dir=str(_ROLES_DIR))
    service_registry = build_service_registry_from_applications(base_applications)
    applications = _applications_for_active_variants(base_applications)
    transitive = applications_if_group_and_all_deps(
        applications,
        [app_id],
        project_root=str(PROJECT_ROOT),
        roles_dir=str(_ROLES_DIR),
        service_registry=service_registry,
    )
    found = set(transitive) | set(_EXPLICIT_INCLUDES) | {app_id}
    return sorted(found)


def main() -> int:
    for role_id in derive_includes(os.environ["APP_ID"]):
        print(role_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
