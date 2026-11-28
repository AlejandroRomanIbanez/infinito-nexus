"""Facts about one role that the swarm drill helpers in ``_context.sh`` read.

Args (argv): a subcommand, the role directory, then its own argument:

- ``primary-service-key <role_dir> <entity>``: the entity's ``proxy.service_key``, else the entity.
- ``placement-manager <role_dir> <role>``: ``true`` when the role declares ``placement: manager``.
- ``probe-port <role_dir> <entity>``: the entity's internal http port, else 80.
- ``nfs-volumes <role_dir> <all|backed-up>``: the docker names of its NFS-backed volumes, one per line.
"""

import sys
from pathlib import Path

from utils.cache.yaml import load_yaml_any
from utils.roles.mapping import ROLE_FILE_META_SERVICES, ROLE_FILE_META_VOLUMES
from utils.roles.meta_lookup import get_role_placement


def _entity(role_dir, entity):
    data = load_yaml_any(
        str(Path(role_dir) / ROLE_FILE_META_SERVICES), default_if_missing=None
    )
    found = data.get(entity) if isinstance(data, dict) else None
    return found if isinstance(found, dict) else None


def primary_service_key(role_dir, entity):
    key = ((_entity(role_dir, entity) or {}).get("proxy") or {}).get("service_key")
    return key if isinstance(key, str) and key else entity


def placement_manager(role_dir, role):
    placement = get_role_placement(role_dir, role_name=role) or ""
    return "true" if placement.strip() == "manager" else "false"


def probe_port(role_dir, entity):
    found = _entity(role_dir, entity)
    if found is None:
        return 80
    try:
        return found["ports"]["internal"]["http"] or 80
    except (KeyError, TypeError):
        return 80


def nfs_volumes(role_dir, scope):
    data = load_yaml_any(
        str(Path(role_dir) / ROLE_FILE_META_VOLUMES), default_if_missing=None
    )
    if isinstance(data, list):
        entries = [entry for entry in data if isinstance(entry, dict)]
    elif isinstance(data, dict):
        entries = [entry for entry in data.values() if isinstance(entry, dict)]
    else:
        entries = []
    names = []
    for volume in entries:
        if volume.get("type") != "volume" or volume.get("nfs") is False:
            continue
        if scope == "backed-up" and volume.get("backup") is False:
            continue
        docker_name = volume.get("docker_name") or volume.get("name")
        if isinstance(docker_name, str):
            names.append(docker_name)
    return "\n".join(names)


COMMANDS = {
    "primary-service-key": primary_service_key,
    "placement-manager": placement_manager,
    "probe-port": probe_port,
    "nfs-volumes": nfs_volumes,
}

if __name__ == "__main__":
    print(COMMANDS[sys.argv[1]](sys.argv[2], sys.argv[3]))
