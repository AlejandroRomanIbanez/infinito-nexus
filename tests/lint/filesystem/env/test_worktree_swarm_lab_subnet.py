"""Every worktree slot must pin a valid swarm lab subnet of its own.

`scripts/system/worktree/up.sh` derives `INFINITO_SWARM_LAB_SUBNET` from the
slot. A derivation that overflows an octet yields an address Docker rejects at
network creation, so `make swarm-zombie` dies in every worktree past that slot.
"""

from __future__ import annotations

import ipaddress
import re
import unittest

from utils.cache.files import read_text
from utils.env.parser import parse_static_env

from . import PROJECT_ROOT

_UP_SH = PROJECT_ROOT / "scripts/system/worktree/up.sh"
_MAX_SLOT_RE = re.compile(r"^max_slot=(?P<value>\d+)$", re.MULTILINE)
_LAB_PREFIX_RE = re.compile(r'^lab_prefix="(?P<template>[^"]+)"$', re.MULTILINE)
_LAB_SUBNET_RE = re.compile(
    r"^INFINITO_SWARM_LAB_SUBNET=\$\{lab_prefix\}\.0/24$", re.MULTILINE
)


class TestWorktreeSwarmLabSubnet(unittest.TestCase):
    def setUp(self) -> None:
        source = read_text(str(_UP_SH))
        max_slot = _MAX_SLOT_RE.search(source)
        lab_prefix = _LAB_PREFIX_RE.search(source)
        self.assertIsNotNone(max_slot, f"{_UP_SH} declares no max_slot")
        self.assertIsNotNone(lab_prefix, f"{_UP_SH} declares no lab_prefix")
        self.assertRegex(source, _LAB_SUBNET_RE)
        self.max_slot = int(max_slot.group("value"))
        self.template = lab_prefix.group("template")

    def _subnet(self, slot: int) -> ipaddress.IPv4Network:
        prefix = self.template.replace("${slot}", str(slot))
        return ipaddress.ip_network(f"{prefix}.0/24")

    def test_every_slot_pins_a_valid_distinct_lab_subnet(self) -> None:
        primary = ipaddress.ip_network(
            parse_static_env(PROJECT_ROOT / "default.env")["INFINITO_SWARM_LAB_SUBNET"]
        )
        worktree_subnets = ipaddress.ip_network("172.30.0.0/16")
        seen: dict[ipaddress.IPv4Network, int] = {}
        for slot in range(1, self.max_slot + 1):
            with self.subTest(slot=slot):
                subnet = self._subnet(slot)
                self.assertFalse(subnet.overlaps(primary), f"slot {slot} overlaps {primary}")
                self.assertFalse(
                    subnet.overlaps(worktree_subnets),
                    f"slot {slot} overlaps the worktree subnets {worktree_subnets}",
                )
                self.assertNotIn(subnet, seen, f"slot {slot} repeats slot {seen.get(subnet)}")
                seen[subnet] = slot


if __name__ == "__main__":
    unittest.main()
