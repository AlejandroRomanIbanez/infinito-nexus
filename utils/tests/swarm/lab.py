"""Lab-shape facts the swarm matrix needs beyond the node names."""

from __future__ import annotations

import os

from utils.cache.yaml import load_yaml_any


def application_overrides() -> dict:
    """Return the ``applications`` subtree of the lab-size override file.

    The failover suite points ``SWARM_DATA_LAB_VARS`` at that file; unset, the
    drill keeps the production sizes.
    """
    path = os.environ.get("SWARM_DATA_LAB_VARS")
    if not path:
        return {}
    return (load_yaml_any(path, default_if_missing={}) or {}).get("applications") or {}
