"""Lookup `tor_egress_clients`: who may use this node's Tor egress ports.

Tor's DNSPort and TransPort carry no access policy of their own, unlike
SocksPort with its SocksPolicy, and a swarm-published port cannot be bound to a
single host address. The filter chain installed by ``tasks/router.yml`` is
therefore what bounds them, and this lookup is the list it admits.

Deliberately not the three RFC1918 blocks: ``10.0.0.0/8`` would hand the
operator's whole LAN a resolver and a transparent proxy. Admitted is exactly the
address space this deployment declares for itself:

* loopback, for the node's own dnsmasq,
* every base of ``NETWORK_DOCKER_ADDRESS_POOLS``,
* ``NETWORK_SWARM_GWBRIDGE_POOL``, the gateway bridge docker creates outside
  those pools and without which overlay tasks lose their route out,
* ``NETWORK_ROLE_SUBNET_POOL`` and the blocks of the roles named in
  ``NETWORK_ROLE_SUBNET_EXCEPTION_ROLES``, resolved through ``role_subnets`` so
  the CIDR stays declared in the role that owns it.

Usage:

    {{ lookup('tor_egress_clients') }}
"""

from __future__ import annotations

from typing import Any

from ansible.errors import AnsibleError
from ansible.plugins.loader import lookup_loader
from ansible.plugins.lookup import LookupBase

_REQUIRED = (
    "NETWORK_LOOPBACK_CIDR",
    "NETWORK_DOCKER_ADDRESS_POOLS",
    "NETWORK_SWARM_GWBRIDGE_POOL",
    "NETWORK_ROLE_SUBNET_POOL",
    "NETWORK_ROLE_SUBNET_EXCEPTION_ROLES",
)


def _pool_bases(pools: Any) -> list[str]:
    if not isinstance(pools, (list, tuple)):
        raise AnsibleError(
            "tor_egress_clients: NETWORK_DOCKER_ADDRESS_POOLS must be a list"
        )
    bases: list[str] = []
    for pool in pools:
        base = pool.get("base") if isinstance(pool, dict) else None
        if not base:
            raise AnsibleError(
                f"tor_egress_clients: address pool {pool!r} declares no base"
            )
        bases.append(str(base).strip())
    return bases


class LookupModule(LookupBase):
    def run(
        self,
        terms: list[Any] | None,
        variables: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Any]:
        if terms:
            raise AnsibleError("lookup('tor_egress_clients') expects no terms.")
        variables = variables or getattr(self._templar, "available_variables", {}) or {}
        missing = [name for name in _REQUIRED if variables.get(name) is None]
        if missing:
            raise AnsibleError(
                "tor_egress_clients: missing group variable(s) "
                f"{', '.join(missing)}; the guard must never be narrowed by a "
                "value that silently defaulted"
            )

        excepted = lookup_loader.get(
            "role_subnets",
            loader=getattr(self, "_loader", None),
            templar=getattr(self, "_templar", None),
        ).run(
            [variables["NETWORK_ROLE_SUBNET_EXCEPTION_ROLES"]],
            variables=variables,
        )[0]

        cidrs = [
            str(variables["NETWORK_LOOPBACK_CIDR"]).strip(),
            *_pool_bases(variables["NETWORK_DOCKER_ADDRESS_POOLS"]),
            str(variables["NETWORK_SWARM_GWBRIDGE_POOL"]).strip(),
            str(variables["NETWORK_ROLE_SUBNET_POOL"]).strip(),
            *excepted,
        ]
        seen: dict[str, None] = {}
        for cidr in cidrs:
            seen.setdefault(cidr, None)
        return [list(seen)]
