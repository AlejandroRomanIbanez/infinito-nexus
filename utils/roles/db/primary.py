"""Lookup seam for central database engines in HA form."""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING

from utils.roles.db.instances import (
    FORM_HA,
    SWARM_NODE_GROUP,
    DbInstancesError,
    build_instances,
    data_engines,
    engine_hosts,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def is_ha(
    application_id: str,
    groups: Mapping[str, Sequence[str]] | None,
    deployment_mode: str,
) -> bool:
    """Return True when a central data engine renders its HA form.

    Args:
        application_id: engine role, e.g. ``svc-db-postgres``.
        groups: Ansible ``groups``.
        deployment_mode: ``DEPLOYMENT_MODE``.
    """
    if application_id not in data_engines():
        return False
    groups = groups or {}
    return (
        build_instances(
            application_id,
            engine_hosts(application_id, groups),
            deployment_mode=deployment_mode,
            swarm_nodes=list(groups.get(SWARM_NODE_GROUP) or []),
        )["form"]
        == FORM_HA
    )


def primary_address(bin_resolver: str, stack: str, engine: str) -> str:
    """Return a shell expression resolving the primary's container at call time.

    Args:
        bin_resolver: path of the ``resolve-db-primary`` helper.
        stack: swarm stack of the engine.
        engine: engine word, e.g. ``postgres``.
    """
    return (
        f'"$({shlex.quote(bin_resolver)} {shlex.quote(stack)} {shlex.quote(engine)})"'
    )


def ha_primary_address(
    application_id: str,
    groups: Mapping[str, Sequence[str]] | None,
    deployment_mode: str,
    *,
    bin_resolver: str,
    stack: str,
    engine: str,
) -> str | None:
    """Return the primary-resolving address of an engine in HA form, else None.

    Args:
        application_id: engine role, e.g. ``svc-db-redis``.
        groups: Ansible ``groups``.
        deployment_mode: ``DEPLOYMENT_MODE``.
        bin_resolver: ``BIN_RESOLVE_DB_PRIMARY``; required in HA form.
        stack: swarm stack of the engine.
        engine: engine word the resolver asks the probe of.
    """
    if not is_ha(application_id, groups, deployment_mode):
        return None
    if not bin_resolver:
        raise DbInstancesError(
            f"{application_id} renders its HA form but BIN_RESOLVE_DB_PRIMARY is unset"
        )
    return primary_address(bin_resolver, stack, engine)
