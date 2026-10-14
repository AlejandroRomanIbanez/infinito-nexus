"""The WireGuard meshes as an inventory records them.

Single source for what every consumer of the mesh reads, so none of them names
a mesh or reaches into the inventory shape on its own:

* which meshes a deployment declares: ``networks.meshes`` of
  ``svc-net-wireguard``, read from the hub, which is in every mesh;
* which meshes a host joins: ``networks.meshes`` of every other role the host
  carries;
* what a host holds on them: ``networks.interfaces`` of ``svc-net-wireguard``,
  which only the mesh CLI writes.

Every role ships these lists empty, so a value can only come from the
deployment's inventory. That also makes a host's raw ``applications`` block
equal to its merged one for these paths.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

APPLICATION_ID = "svc-net-wireguard"
HUB_ROLE = "svc-swarm-manager"
MESHES_KEY = "meshes"
INTERFACES_KEY = "interfaces"


def _listed(applications: Any, role: str, key: str) -> list[Any]:
    if not isinstance(applications, Mapping):
        return []
    networks = (applications.get(role) or {}).get("networks") or {}
    value = networks.get(key) if isinstance(networks, Mapping) else None
    return list(value) if isinstance(value, (list, tuple)) else []


def declared_meshes(applications: Any) -> list[Mapping[str, Any]]:
    """The meshes declared in a host's ``applications``, in declaration order."""
    return [
        entry
        for entry in _listed(applications, APPLICATION_ID, MESHES_KEY)
        if isinstance(entry, Mapping)
    ]


def joined_meshes(applications: Any, roles: Iterable[str]) -> dict[str, list[str]]:
    """Mesh name to the roles that put the host into it.

    Args:
        applications: the host's ``applications`` block.
        roles: the role groups the host belongs to.
    """
    joined: dict[str, list[str]] = {}
    for role in roles:
        if role == APPLICATION_ID:
            continue
        for name in _listed(applications, role, MESHES_KEY):
            joined.setdefault(str(name), []).append(role)
    return joined


def interfaces(applications: Any) -> list[Mapping[str, Any]]:
    """Every mesh interface recorded in a host's ``applications``."""
    return [
        entry
        for entry in _listed(applications, APPLICATION_ID, INTERFACES_KEY)
        if isinstance(entry, Mapping)
    ]


def owned_interface(
    applications: Any, host: str, mesh: str
) -> Mapping[str, Any] | None:
    """The interface *host* itself holds on *mesh*.

    An entry naming another host is ignored: the lab's credential reset copies
    one host's inventory over the others, and adopting what it left would put
    the hub's address on every node.
    """
    for entry in interfaces(applications):
        if entry.get("name") == mesh and entry.get("host") == host:
            return entry
    return None


def address_on(applications: Any, host: str, mesh: str) -> str:
    """The address *host* holds on *mesh*, or ``""`` when it holds none."""
    entry = owned_interface(applications, host, mesh) or {}
    address = entry.get("address")
    return address if isinstance(address, str) else ""


def primary_address(applications: Any, host: str) -> str:
    """The address the other planes reach *host* on, or ``""`` off the mesh."""
    for entry in interfaces(applications):
        if entry.get("primary") and entry.get("host") == host:
            address = entry.get("address")
            if isinstance(address, str) and address:
                return address
    return ""
