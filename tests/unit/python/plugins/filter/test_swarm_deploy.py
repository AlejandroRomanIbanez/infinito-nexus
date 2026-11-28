"""``swarm_deploy`` and ``swarm_deploy_replicas`` decide the swarm ``deploy:`` block of one service."""

from __future__ import annotations

import unittest

from plugins.filter.swarm.deploy import swarm_deploy, swarm_deploy_replicas

APPS = {
    "web-app-demo": {
        "services": {
            "demo": {"replicas": 2, "cpus": "50%", "mem_limit": "1g"},
            "worker": {"placement": "manager", "platform_arch": "amd64"},
        }
    },
    "sys-svc-compose": {"services": {"haproxy": {"mem_limit": "128m"}}},
}


def ctx(**overrides):
    base = {
        "application_id": "web-app-demo",
        "service": "",
        "sizing_application_id": "web-app-demo",
        "applications": APPS,
        "db_instance": None,
        "seeded_after_converge": None,
        "replicas_forced": None,
        "max_replicas_per_node": None,
        "db_endpoint": False,
        "manager_placed": False,
        "managers": ["mgr-01", "mgr-02", "mgr-03"],
        "kata_group": False,
        "kata_enabled": False,
        "update_parallelism": 1,
        "update_delay": "10s",
        "update_order": None,
        "restart_policy": "unless-stopped",
        "runtime": "host",
        "seed_wait_label": "infinito.seed_wait",
        "db_endpoint_label": "infinito.db_endpoint",
        "host_id_label": "infinito.host_id",
        "stack_host_label": "infinito.stack_host",
        "sandbox_label": "kata-capable",
        "defaults": {
            "cpus": "1.0",
            "host_cpus": 4,
            "mem_limit": "512m",
            "pids_limit": 512,
            "mem_reservation": "256m",
        },
    }
    return {**base, **overrides}


class TestReplicas(unittest.TestCase):
    def test_a_db_instance_always_runs_one_task(self):
        self.assertEqual(
            swarm_deploy_replicas(
                ctx(db_instance={"host": "mgr-02"}, replicas_forced=5)
            ),
            1,
        )

    def test_a_forced_count_beats_the_declared_one(self):
        self.assertEqual(swarm_deploy_replicas(ctx(replicas_forced=3)), 3)

    def test_the_declared_count_or_the_topology_default(self):
        self.assertEqual(swarm_deploy_replicas(ctx()), 2)
        self.assertEqual(swarm_deploy_replicas(ctx(service="worker")), 2)
        self.assertEqual(
            swarm_deploy_replicas(
                ctx(application_id="sys-svc-compose", service="haproxy")
            ),
            "",
        )


class TestBlock(unittest.TestCase):
    def test_a_plain_service_renders_resources_and_rolling_update(self):
        self.assertEqual(
            swarm_deploy(ctx(), "replicas: 2"),
            "\n".join(
                [
                    "    deploy:",
                    "      replicas: 2",
                    "      update_config:",
                    "        parallelism: 1",
                    "        delay: 10s",
                    "        failure_action: continue",
                    "      restart_policy:",
                    "        condition: any",
                    "      resources:",
                    "        limits:",
                    '          cpus: "2.0"',
                    "          memory: 1g",
                    "          pids: 512",
                    "        reservations:",
                    "          memory: 256m",
                ]
            ),
        )

    def test_a_single_replica_updates_without_delay(self):
        self.assertIn("        delay: 0s", swarm_deploy(ctx(), "replicas: 1"))

    def test_a_db_instance_is_pinned_to_its_host_and_waits_for_its_seed(self):
        block = swarm_deploy(
            ctx(db_instance={"host": "mgr-02"}, seeded_after_converge=True),
            "replicas: 1",
        )
        self.assertIn('        infinito.seed_wait: "true"', block)
        self.assertIn("          - node.labels.infinito.host_id == mgr-02", block)

    def test_the_write_endpoint_spreads_without_a_role_constraint(self):
        block = swarm_deploy(
            ctx(
                application_id="sys-svc-compose",
                sizing_application_id="sys-svc-compose",
                service="haproxy",
                db_endpoint=True,
                max_replicas_per_node=1,
                manager_placed=True,
            ),
            "replicas: 3",
        )
        self.assertIn('        infinito.db_endpoint: "true"', block)
        self.assertIn("        max_replicas_per_node: 1", block)
        self.assertNotIn("constraints:", block)
        self.assertIn("          memory: 128m", block)

    def test_a_placed_service_gets_its_role_stack_host_and_arch(self):
        block = swarm_deploy(ctx(service="worker"), "replicas: 2")
        for constraint in (
            "node.role == manager",
            "node.labels.infinito.stack_host == true",
            "node.platform.arch == amd64",
        ):
            self.assertIn(f"          - {constraint}", block)

    def test_a_kata_lab_keeps_plain_services_off_the_sandbox_node(self):
        self.assertIn(
            "          - node.labels.kata-capable != true",
            swarm_deploy(ctx(kata_group=True), "replicas: 2"),
        )
        self.assertIn(
            "          - node.labels.kata-capable == true",
            swarm_deploy(ctx(kata_group=True, kata_enabled=True), "replicas: 2"),
        )

    def test_github_runners_reserve_no_memory_and_one_shots_never_restart(self):
        block = swarm_deploy(
            ctx(runtime="github", restart_policy="no", update_order="stop-first"),
            "replicas: 2",
        )
        self.assertNotIn("reservations:", block)
        self.assertIn("        condition: none", block)
        self.assertIn("        order: stop-first", block)


if __name__ == "__main__":
    unittest.main()
