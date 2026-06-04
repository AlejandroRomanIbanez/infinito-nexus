"""Unit tests for the compose_container_name lookup plugin.

Pins the contract for the lookup that gates `container_name:` emission in
docker-compose templates between compose and swarm deployment modes.
"""

from __future__ import annotations

import importlib.util
import unittest

from ansible.errors import AnsibleError

from . import PROJECT_ROOT


def _load_lookup():
    spec = importlib.util.spec_from_file_location(
        "lookup_compose_container_name",
        str(PROJECT_ROOT / "plugins/lookup/compose_container_name.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod.LookupModule


class _DummyTemplar:
    """Stand-in for Ansible's templar that returns inputs unchanged."""

    def __init__(self, available_variables=None):
        self.available_variables = available_variables or {}

    def template(self, value):
        return value


class TestComposeContainerNameLookup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.LookupModule = _load_lookup()

    def _make(self, variables):
        lm = self.LookupModule()
        lm._templar = _DummyTemplar(variables)
        lm._loader = None
        return lm

    def test_compose_mode_emits_container_name(self):
        lm = self._make({"DEPLOYMENT_MODE": "compose"})
        result = lm.run(["myapp"], variables={"DEPLOYMENT_MODE": "compose"})
        self.assertEqual(result, ['container_name: "myapp"'])

    def test_swarm_mode_emits_empty(self):
        lm = self._make({"DEPLOYMENT_MODE": "swarm"})
        result = lm.run(["myapp"], variables={"DEPLOYMENT_MODE": "swarm"})
        self.assertEqual(result, [""])

    def test_swarm_mode_with_surrounding_whitespace(self):
        lm = self._make({"DEPLOYMENT_MODE": "  swarm  "})
        result = lm.run(["myapp"], variables={"DEPLOYMENT_MODE": "  swarm  "})
        self.assertEqual(result, [""])

    def test_missing_deployment_mode_defaults_to_compose(self):
        lm = self._make({})
        result = lm.run(["myapp"], variables={})
        self.assertEqual(result, ['container_name: "myapp"'])

    def test_empty_terms_raises(self):
        lm = self._make({"DEPLOYMENT_MODE": "compose"})
        with self.assertRaises(AnsibleError):
            lm.run([], variables={"DEPLOYMENT_MODE": "compose"})

    def test_none_terms_raises(self):
        lm = self._make({"DEPLOYMENT_MODE": "compose"})
        with self.assertRaises(AnsibleError):
            lm.run(None, variables={"DEPLOYMENT_MODE": "compose"})

    def test_too_many_terms_raises(self):
        lm = self._make({"DEPLOYMENT_MODE": "compose"})
        with self.assertRaises(AnsibleError):
            lm.run(["a", "b"], variables={"DEPLOYMENT_MODE": "compose"})

    def test_non_string_name_coerced_to_string(self):
        lm = self._make({"DEPLOYMENT_MODE": "compose"})
        result = lm.run([42], variables={"DEPLOYMENT_MODE": "compose"})
        self.assertEqual(result, ['container_name: "42"'])


if __name__ == "__main__":
    unittest.main(verbosity=2)
