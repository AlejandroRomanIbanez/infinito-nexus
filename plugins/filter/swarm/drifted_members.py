"""Name the HA database members a stack deploy would restart."""

from __future__ import annotations

import json

from ansible.errors import AnsibleFilterError

from utils.cache.yaml import load_yaml_str
from utils.roles.swarm_drift import SwarmDriftError, drifted_fields


def swarm_drifted_members(stack_config: str, stack: str, inspected) -> list[str]:
    """Return the members whose rendered service differs from the running one.

    Args:
        stack_config: stdout of ``docker stack config`` for the engine.
        stack: swarm stack name.
        inspected: loop results of ``docker service inspect --format
            '{{json .Spec}}'``, one per member key in ``item``; a member that
            is not running yet (non-zero ``rc``) is left to the stack deploy.

    Returns:
        the drifted member keys, in loop order.
    """
    config = load_yaml_str(stack_config) or {}
    services = config.get("services") or {}
    drifted = []
    for result in inspected or []:
        member = result.get("item")
        if result.get("rc") != 0 or member not in services:
            continue
        try:
            fields = drifted_fields(
                services[member], config, stack, json.loads(result["stdout"])
            )
        except (SwarmDriftError, ValueError, KeyError) as exc:
            raise AnsibleFilterError(f"swarm_drifted_members: {member}: {exc}") from exc
        if fields:
            drifted.append(member)
    return drifted


class FilterModule:
    def filters(self):
        return {"swarm_drifted_members": swarm_drifted_members}
