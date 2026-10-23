"""Swarm topology validation: manager quorum size and engine-group eligibility."""

from __future__ import annotations

from pathlib import Path

from utils.roles.db.instances import coordination_store, ha_engines

from .loaders import load_yaml_file

MANAGER_GROUP = "svc-swarm-manager"
NODE_GROUP = "svc-swarm-node"


def _collect_groups(inv_dir) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for f in sorted(Path(inv_dir).glob("*.yml")):
        data = load_yaml_file(f)
        if not isinstance(data, dict):
            continue
        children = (data.get("all") or {}).get("children")
        if not isinstance(children, dict):
            continue
        for grp, node in children.items():
            hosts = (node or {}).get("hosts") if isinstance(node, dict) else None
            members = groups.setdefault(grp, [])
            for host in hosts or {}:
                if host not in members:
                    members.append(host)
    return groups


def is_valid_quorum_size(count: int) -> bool:
    """Return True for 0, 1 or an odd count of at least 3.

    Args:
        count: number of members in a Raft- or etcd-style quorum group.
    """
    return count <= 1 or (count >= 3 and count % 2 == 1)


def validate_swarm_topology(inv_dir) -> list[str]:
    """Return topology errors for the inventory in ``inv_dir``.

    Args:
        inv_dir: inventory directory whose ``*.yml`` files are merged.
    """
    groups = _collect_groups(inv_dir)
    errs: list[str] = []
    managers = groups.get(MANAGER_GROUP, [])
    if groups.get(NODE_GROUP) and not managers:
        errs.append(f"Group '{NODE_GROUP}' has hosts but '{MANAGER_GROUP}' is empty")
    elif not is_valid_quorum_size(len(managers)):
        errs.append(
            f"Group '{MANAGER_GROUP}' has {len(managers)} hosts; "
            "it must hold 1 host or an odd number of at least 3"
        )
    store = coordination_store()
    store_members = groups.get(store, [])
    if not is_valid_quorum_size(len(store_members)):
        errs.append(
            f"Group '{store}' has {len(store_members)} hosts; "
            "it must hold 1 member or an odd number of at least 3"
        )
    nodes = set(groups.get(NODE_GROUP, []))
    if not nodes:
        return errs
    engines = ha_engines()
    for grp, hosts in sorted(groups.items()):
        if grp not in engines:
            continue
        errs.extend(
            f"Group '{grp}' lists host '{host}', which is not in '{NODE_GROUP}'"
            for host in hosts
            if host not in nodes
        )
    return errs
