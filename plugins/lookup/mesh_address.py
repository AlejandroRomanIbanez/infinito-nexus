"""Lookup `mesh_address`: the address a host is reached on over the mesh.

The address belongs to the host, not to a role: the mesh CLI writes it into the
host's ``svc-net-wireguard.networks.interfaces``, and this reads it back through
:mod:`utils.networks.mesh` like every other consumer does. It is the host's
primary address, the one every other plane routes to, whatever the deployment
named its meshes.

Usage:

    {{ lookup('mesh_address', STACK_HOST) }}   # '10.100.0.1', or '' off the mesh

Takes exactly one term, the inventory hostname.
"""

from __future__ import annotations

from typing import Any

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase

from utils.networks.mesh import primary_address


class LookupModule(LookupBase):
    def run(
        self,
        terms: list[Any] | None,
        variables: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Any]:
        if not terms or len(terms) != 1:
            raise AnsibleError("lookup('mesh_address', <hostname>) takes one term")
        host = str(terms[0]).strip()
        hostvars = (variables or {}).get("hostvars") or {}
        try:
            applications = hostvars[host].get("applications") or {}
        except KeyError:
            applications = {}
        return [primary_address(applications, host)]
