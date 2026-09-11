"""Resolve which role is the active mail provider for a deploy.

``MAIL_PROVIDER`` is the operator's config flag and always wins while the role
it names is part of the deploy. It is a static inventory value, though, so a
round that deploys only the alternative provider would otherwise resolve to a
role that is not there: the provider binds no public mail ports, skips
``sys-ctl-mtn-cert-deploy``, and every consumer resolves its SMTP host against
a server that was never deployed.

Falling back to whichever declaring role IS deployed fixes that, and ordering
the fallback ``provides:`` before ``covers:`` keeps it single-valued — two
providers can never both consider themselves active and bind port 25.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from utils.roles.applications.services.registry import (
    build_covered_key_to_role,
    build_role_to_primary_service_key,
    build_service_registry_from_roles_dir,
)

if TYPE_CHECKING:
    from pathlib import Path

MAIL_SERVICE_KEY = "email"


def _registry(roles_dir: Path) -> dict[str, dict[str, Any]]:
    return build_service_registry_from_roles_dir(roles_dir)


def declaring_roles(roles_dir: Path) -> list[str]:
    """Roles that declare the mail service, ``provides:`` before ``covers:``.

    Args:
        roles_dir: repository ``roles/`` directory.

    Returns:
        Role ids in fallback priority order, without duplicates.
    """
    registry = _registry(roles_dir)
    ordered: list[str] = []

    for role, primary_key in sorted(
        build_role_to_primary_service_key(registry).items()
    ):
        if primary_key == MAIL_SERVICE_KEY and role not in ordered:
            ordered.append(role)

    covering = build_covered_key_to_role(registry).get(MAIL_SERVICE_KEY, "")
    if covering and covering not in ordered:
        ordered.append(covering)

    return ordered


def resolve_active_provider(
    configured: str, group_names: list[str] | tuple[str, ...], roles_dir: Path
) -> str:
    """The role acting as mail provider for this deploy.

    Args:
        configured: the ``MAIL_PROVIDER`` value from the inventory.
        group_names: the roles taking part in this deploy.
        roles_dir: repository ``roles/`` directory.

    Returns:
        ``configured`` when that role is deployed, otherwise the
        highest-priority declaring role that is; ``configured`` when none is.
    """
    present = set(group_names or ())
    if configured and configured in present:
        return configured

    for role in declaring_roles(roles_dir):
        if role in present:
            return role

    return configured
