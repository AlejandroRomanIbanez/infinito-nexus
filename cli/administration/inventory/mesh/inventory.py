"""Read group membership, mesh declarations and who joins which mesh.

Group membership is collected across every inventory file it is spread over.
The swarm lab keeps the backup host in a sibling ``backup.yml`` rather than in
the cluster inventory, so a mesh that spans both planes is only complete when
both files have been read.

The declarations and the memberships are ordinary ``applications`` values in
each host's ``host_vars``: the hub's ``svc-net-wireguard.networks.meshes``
declares the meshes, and every other role's ``networks.meshes`` puts the hosts
carrying it into them (:mod:`utils.networks.mesh`).
"""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from typing import Any

from cli.administration.inventory.provision.ruamel_io import load_document
from utils import PROJECT_ROOT
from utils.cache.yaml import load_yaml_any
from utils.networks.mesh import (
    APPLICATION_ID,
    HUB_ROLE,
    MESHES_KEY,
    declared_meshes,
    joined_meshes,
)

from .model import MeshSpec, Topology

POOL_VAR = "NETWORK_MESH_POOL"


def groups_of(inventory_files: list[Path]) -> dict[str, list[str]]:
    """The union of ``group -> hosts`` over every given inventory file."""
    groups: dict[str, list[str]] = {}
    for path in inventory_files:
        if not path.exists():
            continue
        document = load_yaml_any(str(path))
        if not isinstance(document, dict):
            continue
        _collect(document.get("all", {}), groups)
    return groups


def _collect(node: Any, groups: dict[str, list[str]]) -> None:
    if not isinstance(node, dict):
        return
    for name, child in (node.get("children") or {}).items():
        if not isinstance(child, dict):
            continue
        bucket = groups.setdefault(name, [])
        for host in child.get("hosts") or {}:
            if host not in bucket:
                bucket.append(host)
        _collect(child, groups)


def host_applications(host_vars_dir: Path, host: str) -> Any:
    """The ``applications`` block of *host*'s ``host_vars``, or ``{}``."""
    path = host_vars_dir / f"{host}.yml"
    if not path.is_file():
        return {}
    return load_document(path).get("applications") or {}


def hub_of(groups: dict[str, list[str]]) -> str:
    """The host that routes for every mesh."""
    hubs = sorted(dict.fromkeys(groups.get(HUB_ROLE, [])))
    if len(hubs) != 1:
        raise ValueError(
            f"hub group '{HUB_ROLE}' resolves to {len(hubs)} hosts, expected exactly 1"
        )
    return hubs[0]


def specs_of(applications: Any, inventory_files: list[Path]) -> list[MeshSpec]:
    """The meshes declared in *applications*, in declaration order.

    Args:
        applications: the hub's ``applications`` block.
        inventory_files: the inventories of the deploy, whose ``group_vars``
            may narrow the platform's mesh pool.
    """
    declared = declared_meshes(applications)
    if not declared:
        raise ValueError(
            f"{APPLICATION_ID} declares no networks.{MESHES_KEY}: a deployment "
            "states its meshes in the hub's host_vars"
        )
    pool = pool_of(inventory_files)
    specs = [
        MeshSpec(
            name=str(entry["name"]),
            subnet=str(entry["subnet"]),
            listen_port=int(entry["listen_port"]),
            routed_range=str(entry.get("routed_range") or pool),
        )
        for entry in declared
    ]
    names = [spec.name for spec in specs]
    duplicated = sorted({name for name in names if names.count(name) > 1})
    if duplicated:
        raise ValueError(f"meshes declared more than once: {duplicated}")
    assert_no_subnet_overlap(specs, pool)
    return specs


def topology_of(
    groups: dict[str, list[str]], host_vars_dir: Path, specs: list[MeshSpec]
) -> Topology:
    """Who the inventory puts into each declared mesh.

    A host joins a mesh when any role it carries lists that mesh in its
    ``networks.meshes``. A name nobody declared is refused rather than
    dropped, because the host would otherwise deploy without the tunnel its
    inventory asked for.
    """
    hub = hub_of(groups)
    spokes: dict[str, list[str]] = {spec.name: [] for spec in specs}
    hosts = sorted({host for members in groups.values() for host in members})
    for host in hosts:
        roles = [group for group, members in groups.items() if host in members]
        joined = joined_meshes(host_applications(host_vars_dir, host), roles)
        for name, by in sorted(joined.items()):
            if name not in spokes:
                raise ValueError(
                    f"{host}: {', '.join(by)} join(s) mesh '{name}', which "
                    f"{APPLICATION_ID} does not declare"
                )
            if host != hub:
                spokes[name].append(host)
    return Topology(hub=hub, spokes={name: tuple(h) for name, h in spokes.items()})


_REFERENCE = re.compile(r"^\s*\{\{\s*(?P<name>[A-Z0-9_]+)\s*\}\}\s*$")


def _literal_of(name: str, directories: list[Path]) -> str | None:
    """The literal ``name`` holds in the first directory that defines one."""
    for directory in directories:
        for path in sorted(directory.glob("*.yml")):
            document = load_yaml_any(str(path), default_if_missing={})
            value = (document or {}).get(name)
            if isinstance(value, str) and not _REFERENCE.match(value):
                return value
    return None


def pool_of(inventory_files: list[Path]) -> str:
    """The range every mesh subnet is carved from.

    A deployment narrows it in its own ``group_vars/all``; otherwise the
    platform's ``NETWORK_MESH_POOL`` applies, which is where every range the
    platform allocates is declared once.
    """
    directories: list[Path] = []
    for path in inventory_files:
        group_vars = Path(path).parent / "group_vars"
        directories += [group_vars, group_vars / "all"]
    directories.append(PROJECT_ROOT / "group_vars" / "all")
    pool = _literal_of(POOL_VAR, list(dict.fromkeys(directories)))
    if pool is None:
        raise ValueError(f"{POOL_VAR} is defined nowhere the deploy reads it from")
    return pool


def assert_no_subnet_overlap(specs: list[MeshSpec], pool: str | None) -> None:
    """Fail when two meshes overlap, or when one escapes the declared pool.

    Checked before a deploy rather than discovered at runtime, where an overlap
    presents as a peer that is configured, handshakes, and still cannot be
    reached.
    """
    networks = [
        (spec, ipaddress.ip_network(spec.subnet, strict=True)) for spec in specs
    ]

    if pool:
        allowed = ipaddress.ip_network(pool, strict=True)
        for spec, network in networks:
            if not network.subnet_of(allowed):
                raise ValueError(
                    f"mesh '{spec.name}' subnet {spec.subnet} falls outside "
                    f"the declared pool {pool}"
                )

    for index, (spec, network) in enumerate(networks):
        for other_spec, other in networks[index + 1 :]:
            if network.overlaps(other):
                raise ValueError(
                    f"mesh '{spec.name}' subnet {spec.subnet} overlaps "
                    f"mesh '{other_spec.name}' subnet {other_spec.subnet}"
                )

    ports = [spec.listen_port for spec in specs]
    duplicated = {port for port in ports if ports.count(port) > 1}
    if duplicated:
        raise ValueError(f"meshes share listen port(s): {sorted(duplicated)}")
