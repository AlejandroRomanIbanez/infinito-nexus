import unittest
from pathlib import Path
from typing import ClassVar

from jinja2 import Environment, StrictUndefined, select_autoescape

import plugins.lookup.mesh_address as mesh_address
from utils.cache.files import PROJECT_ROOT
from utils.cache.yaml import load_yaml

_WIREGUARD_VARS = Path(PROJECT_ROOT) / "group_vars" / "all" / "21_wireguard.yml"


def _lookup(hostvars):
    def lookup(name, *terms):
        if name != "mesh_address":
            raise AssertionError(f"unexpected lookup({name!r})")
        plugin = mesh_address.LookupModule()
        return plugin.run(list(terms), variables={"hostvars": hostvars})[0]

    return lookup


class TestWireguardEnabled(unittest.TestCase):
    env: ClassVar[Environment]
    source: ClassVar[str]

    @classmethod
    def setUpClass(cls):
        cls.env = Environment(undefined=StrictUndefined, autoescape=select_autoescape())
        cls.source = load_yaml(_WIREGUARD_VARS)["WIREGUARD_ENABLED"]

    def _render(self, *, mode, interfaces=None):
        applications = (
            {}
            if interfaces is None
            else {"svc-net-wireguard": {"networks": {"interfaces": interfaces}}}
        )
        hostvars = {"bkp": {"applications": applications}}
        return (
            self.env.from_string(self.source)
            .render(
                DEPLOYMENT_MODE=mode, inventory_hostname="bkp", lookup=_lookup(hostvars)
            )
            .strip()
        )

    @staticmethod
    def _interface(host):
        return {"name": "data", "host": host, "address": "10.100.1.12", "primary": True}

    def test_swarm_always_runs_it(self):
        self.assertEqual("True", self._render(mode="swarm"))

    def test_a_compose_host_given_a_mesh_runs_it(self):
        interfaces = [self._interface("bkp")]
        self.assertEqual("True", self._render(mode="compose", interfaces=interfaces))

    def test_a_compose_host_without_a_mesh_stays_untouched(self):
        self.assertEqual("False", self._render(mode="compose"))

    def test_an_entry_another_host_owns_does_not_count(self):
        interfaces = [self._interface("mgr")]
        self.assertEqual("False", self._render(mode="compose", interfaces=interfaces))
