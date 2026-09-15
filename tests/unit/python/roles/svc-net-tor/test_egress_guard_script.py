"""The rendered Tor egress guard rebuilds its chain instead of adding to it.

The first version of this guard appended: it created the chain when absent and
appended one ACCEPT per admitted range. Narrowing the admitted set then did
nothing, because the retired range had no removal step and the new one landed
below the DROP, where no packet reaches it. The chain could be loosened and
never tightened, which is the wrong direction for a rule that is the only
boundary two policy-less ports have.

What keeps that from coming back is an order: flush, then admit, then drop, then
hook. These tests pin it against the rendered script, because the ordering is
invisible in the template's individual lines.
"""

from __future__ import annotations

import shlex
import unittest
from pathlib import Path

import jinja2

from . import PROJECT_ROOT

TEMPLATE = (
    PROJECT_ROOT / "roles" / "svc-net-tor" / "templates" / "tor-egress-guard.sh.j2"
)

CHAIN = "INFINITO_TOR_EGRESS"
CLIENTS = ["127.0.0.0/8", "10.208.0.0/12"]
HOOKS = ["INPUT", "DOCKER-USER"]
PORTS = [
    {"port": "9040", "protocol": "tcp"},
    {"port": "9053", "protocol": "udp"},
]


def _render() -> list[str]:
    environment = jinja2.Environment(
        keep_trailing_newline=True,
        autoescape=False,  # noqa: S701  shell, not markup
    )
    environment.filters["quote"] = shlex.quote
    rendered = environment.from_string(
        Path(TEMPLATE).read_text(encoding="utf-8")
    ).render(
        TOR_EGRESS_GUARD_CHAIN=CHAIN,
        TOR_EGRESS_CLIENT_CIDRS=CLIENTS,
        TOR_EGRESS_GUARD_HOOK_CHAINS=HOOKS,
        TOR_EGRESS_GUARDED_PORTS=PORTS,
    )
    return [line.strip() for line in rendered.splitlines() if line.strip()]


def _index_of(lines: list[str], needle: str) -> int:
    for position, line in enumerate(lines):
        if needle in line:
            return position
    raise AssertionError(f"the rendered guard never {needle!r}:\n" + "\n".join(lines))


class TestEgressGuardScript(unittest.TestCase):
    def test_the_chain_is_flushed_before_it_is_filled(self) -> None:
        lines = _render()
        flush = _index_of(lines, '-F "${CHAIN}"')
        first_admit = _index_of(lines, f"-s {CLIENTS[0]}")
        self.assertLess(
            flush,
            first_admit,
            "the chain must be flushed before the admitted ranges are added, or a "
            "narrowed client list leaves the old range in place",
        )

    def test_every_admitted_range_precedes_the_drop(self) -> None:
        lines = _render()
        drop = _index_of(lines, "-j DROP")
        for cidr in CLIENTS:
            with self.subTest(cidr=cidr):
                self.assertLess(
                    _index_of(lines, f"-s {cidr}"),
                    drop,
                    f"{cidr} is admitted below the DROP, where it never matches",
                )

    def test_the_hooks_come_after_the_chain_is_complete(self) -> None:
        """A hook installed first would route packets into a half-built chain."""
        lines = _render()
        drop = _index_of(lines, "-j DROP")
        for chain in HOOKS:
            for entry in PORTS:
                with self.subTest(chain=chain, port=entry["port"]):
                    hook = _index_of(lines, f"-I {chain} -p {entry['protocol']}")
                    self.assertGreater(hook, drop)

    def test_every_admitted_range_and_port_is_rendered(self) -> None:
        lines = _render()
        body = "\n".join(lines)
        for cidr in CLIENTS:
            self.assertIn(cidr, body)
        for chain in HOOKS:
            for entry in PORTS:
                self.assertIn(
                    f"--dport {entry['port']}",
                    body,
                    f"{chain} never guards {entry['protocol']}/{entry['port']}",
                )


if __name__ == "__main__":
    unittest.main()
