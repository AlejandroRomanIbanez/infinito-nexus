from __future__ import annotations

import unittest

from ansible.errors import AnsibleError

from plugins.lookup.tor_socks_proxy import LookupModule, resolve_proxy_url

APPS = {"svc-net-tor": {"services": {"tor": {"ports": {"local": {"socks": 9050}}}}}}


class TestResolveProxyUrl(unittest.TestCase):
    def test_swarm_uses_the_shared_overlay_alias(self):
        self.assertEqual(resolve_proxy_url(APPS, "swarm"), "socks5h://tor:9050")

    def test_compose_uses_the_host_gateway(self):
        self.assertEqual(
            resolve_proxy_url(APPS, "compose"),
            "socks5h://host.docker.internal:9050",
        )

    def test_unknown_mode_falls_back_to_the_compose_form(self):
        for mode in ("", "  ", "kubernetes", None):
            with self.subTest(mode=mode):
                self.assertEqual(
                    resolve_proxy_url(APPS, mode),
                    "socks5h://host.docker.internal:9050",
                )

    def test_port_comes_from_the_single_source_of_truth(self):
        apps = {
            "svc-net-tor": {"services": {"tor": {"ports": {"local": {"socks": 9150}}}}}
        }
        self.assertEqual(resolve_proxy_url(apps, "swarm"), "socks5h://tor:9150")

    def test_missing_port_raises(self):
        with self.assertRaises(AnsibleError):
            resolve_proxy_url({"svc-net-tor": {"services": {"tor": {}}}}, "swarm")


class TestTorSocksProxyLookup(unittest.TestCase):
    def test_terms_raise(self):
        lookup = LookupModule()
        lookup._templar = None
        with self.assertRaises(AnsibleError):
            lookup.run(["x"], variables={})


if __name__ == "__main__":
    unittest.main()
