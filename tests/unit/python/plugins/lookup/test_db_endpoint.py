import unittest

from ansible.errors import AnsibleError

from plugins.lookup.db_endpoint import LookupModule
from utils.roles.db.endpoint import KEEPALIVE_SYSCTLS
from utils.roles.meta_lookup import get_role_ports

HOSTS = ["m1", "m2", "m3"]


def _run(terms, kwargs=None, **variables):
    lookup = LookupModule()
    lookup._templar = None
    return lookup.run(terms, variables=variables, **(kwargs or {}))[0]


class TestDbEndpointLookup(unittest.TestCase):
    def test_ha_postgres(self):
        ports = get_role_ports("svc-db-postgres", "internal")
        cfg = _run(
            ["svc-db-postgres"],
            DEPLOYMENT_MODE="swarm",
            groups={"svc-db-postgres": HOSTS, "svc-swarm-node": HOSTS},
        )
        self.assertIn(
            f"server postgres-m3 postgres-m3:{ports['postgres']} check port {ports['patroni']} ",
            cfg,
        )

    def test_elector_check_port_comes_from_meta(self):
        ports = get_role_ports("svc-db-mariadb", "internal")
        cfg = _run(
            [],
            application_id="svc-db-mariadb",
            DEPLOYMENT_MODE="swarm",
            groups={"svc-db-mariadb": HOSTS, "svc-swarm-node": HOSTS},
        )
        self.assertIn(
            f"server mariadb-m1 mariadb-m1:{ports['mariadb']} check port {ports['writer']} ",
            cfg,
        )

    def test_redis_check_user_and_password(self):
        cfg = _run(
            ["svc-db-redis"],
            {"check_user": "probe-user", "check_password": "Secret123"},
            DEPLOYMENT_MODE="swarm",
            groups={"svc-db-redis": HOSTS, "svc-swarm-node": HOSTS},
        )
        self.assertIn("AUTH\\ probe-user\\ Secret123", cfg)

    def test_sysctls_for_a_privileged_port(self):
        ports = get_role_ports("svc-db-openldap", "internal")
        self.assertEqual(
            _run(["svc-db-openldap"], {"field": "sysctls"}),
            {**KEEPALIVE_SYSCTLS, "net.ipv4.ip_unprivileged_port_start": ports["ldap"]},
        )

    def test_only_keepalive_sysctls_for_an_unprivileged_port(self):
        self.assertEqual(
            _run(["svc-db-postgres"], {"field": "sysctls"}), KEEPALIVE_SYSCTLS
        )

    def test_unknown_field_raises(self):
        with self.assertRaises(AnsibleError):
            _run(["svc-db-postgres"], {"field": "port"})

    def test_standalone_raises(self):
        with self.assertRaises(AnsibleError):
            _run(["svc-db-postgres"], groups={"svc-db-postgres": ["m1"]})

    def test_renderer_error_is_ansible_error(self):
        with self.assertRaises(AnsibleError):
            _run(
                ["svc-db-redis"],
                DEPLOYMENT_MODE="swarm",
                groups={"svc-db-redis": HOSTS, "svc-swarm-node": HOSTS},
            )

    def test_engine_without_endpoint_raises(self):
        with self.assertRaises(AnsibleError):
            _run(["svc-dcs-etcd"], {"field": "sysctls"})


if __name__ == "__main__":
    unittest.main()
