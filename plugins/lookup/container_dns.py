from __future__ import annotations

from typing import Any

from ansible.plugins.lookup import LookupBase

_TOR_ROLE = "svc-net-tor"


def resolve_container_dns(variables: dict[str, Any]) -> list[str]:
    """Return the resolver list for the container runtime, most specific first.

    On a Tor node the node dnsmasq resolves ``.onion`` through Tor's DNSPort
    and everything else through the clearnet upstream, which is what makes
    per-app proxy settings unnecessary. It is only reachable on the docker
    bridge address because docker discards loopback resolvers, and it is
    absent before docker itself is installed, hence the guard.

    The clearnet resolver stays as a second entry so that losing dnsmasq costs
    onion names rather than all name resolution.
    """
    facts = variables.get("ansible_facts") or {}
    bridge = ((facts.get("docker0") or {}).get("ipv4") or {}).get("address") or ""
    on_tor_node = _TOR_ROLE in (variables.get("group_names") or [])

    clearnet = (
        ((variables.get("networks") or {}).get("internet") or {}).get("dns") or ""
    )

    resolvers = [str(r) for r in (bridge if on_tor_node else "", clearnet) if r]
    return resolvers


class LookupModule(LookupBase):
    """
    Usage:
      {{ lookup('container_dns') }}

    Resolver list for the docker daemon's ``dns`` key. Takes no terms.
    """

    def run(self, terms, variables: dict[str, Any] | None = None, **kwargs):
        if terms:
            raise ValueError("lookup('container_dns') takes no positional terms.")
        variables = variables or getattr(self._templar, "available_variables", {}) or {}
        return [resolve_container_dns(variables)]
