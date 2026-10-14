"""Lookup `mesh_ranges`: the address ranges the WireGuard meshes occupy.

Single SPOT for "which address space do the meshes own". The pool is declared
once, as ``NETWORK_MESH_POOL`` beside every other range the platform
allocates, and anything that has to admit mesh traffic reads it from here
rather than repeating the variable, which is how a range ends up stated twice
and then drifts: a firewall or export list built from a stale copy silently
excludes the hosts that joined since.

Usage:

    {{ lookup('mesh_ranges') }}           # ['10.100.0.0/16']

Takes no terms. The result is a list so a consumer can concatenate it with the
addresses it already allows without special-casing the single-entry shape.

The variable arrives unrendered: a lookup is handed the play vars as declared,
so ``WIREGUARD_SUBNET_POOLS`` reads ``{{ [WIREGUARD_SUBNET_POOL] }}`` until it is
templated. Returning that verbatim put the literal into the NFS export list,
and ganesha refused to start on it.
"""

from __future__ import annotations

from typing import Any

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase

from utils.networks.lookup_context import resolve_var

_POOL_VAR = "WIREGUARD_SUBNET_POOLS"


def _is_template(value: str) -> bool:
    return "{{" in value or "{%" in value


class LookupModule(LookupBase):
    def run(
        self,
        terms: list[Any] | None,
        variables: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Any]:
        if terms:
            raise AnsibleError("lookup('mesh_ranges') takes no terms")
        pools = (variables or {}).get(_POOL_VAR)
        if pools is None:
            raise AnsibleError(f"mesh_ranges: {_POOL_VAR} is not defined")
        pools = resolve_var(getattr(self, "_templar", None), pools)
        if isinstance(pools, str):
            pools = [pools]
        ranges = [str(entry).strip() for entry in pools if str(entry).strip()]
        if not ranges:
            raise AnsibleError(f"mesh_ranges: {_POOL_VAR} declares no range")
        unrendered = [entry for entry in ranges if _is_template(entry)]
        if unrendered:
            raise AnsibleError(
                f"mesh_ranges: {_POOL_VAR} did not render: {', '.join(unrendered)}"
            )
        return [ranges]
