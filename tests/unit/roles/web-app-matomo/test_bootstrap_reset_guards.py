"""Guards around the destructive Matomo bootstrap reset.

``roles/web-app-matomo/tasks/utils/reset_state.yml`` drops and recreates the
application database. These tests evaluate the conditions that gate it rather
than trusting a reading of them.

The conditions are Jinja; they compile with a plain Jinja environment plus a
``bool`` filter shim, since ``bool`` is an Ansible filter.
"""

import unittest

from jinja2 import Environment

from utils.cache.yaml import load_yaml_any

from . import PROJECT_ROOT

ROLE = PROJECT_ROOT / "roles" / "web-app-matomo"
RESET_STATE = ROLE / "tasks" / "utils" / "reset_state.yml"
FLAVORS = ROLE / "tasks" / "04_bootstrap" / "flavors"
ATTEMPT_FILES = {
    "compose": FLAVORS / "compose_attempt.yml",
    "swarm": FLAVORS / "swarm_attempt.yml",
}
RESULT_VAR = {
    "compose": "matomo_bootstrap_compose",
    "swarm": "matomo_bootstrap_swarm",
}

_TRUTHY = frozenset({"1", "true", "yes", "y", "on"})


def _to_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _TRUTHY


def _env() -> Environment:
    env = Environment(autoescape=True)
    env.filters["bool"] = _to_bool
    return env


def _eval(expressions, context) -> bool:
    env = _env()
    return all(bool(env.compile_expression(expr)(**context)) for expr in expressions)


def _tasks(path):
    return load_yaml_any(str(path)) or []


def _find(tasks, predicate):
    for task in tasks:
        if predicate(task):
            return task
    return None


def _reset_include(flavor):
    tasks = _tasks(ATTEMPT_FILES[flavor])
    return _find(
        tasks,
        lambda t: (
            "reset_state.yml" in str(t.get("ansible.builtin.include_tasks") or {})
        ),
    )


def _reset_guard(flavor):
    include = _reset_include(flavor)
    when = include["when"]
    return when if isinstance(when, list) else [when]


def _state(flavor, *, attempt, previous_rc, config_rc, stack_host=True):
    context = {
        "IS_STACK_HOST": stack_host,
        "matomo_attempt_index": attempt,
        "matomo_config_exists": {"rc": config_rc},
    }
    if previous_rc is not None:
        context[RESULT_VAR[flavor]] = {"rc": previous_rc}
    return context


class TestResetGateReachability(unittest.TestCase):
    def test_first_attempt_never_resets(self):
        for flavor in ATTEMPT_FILES:
            with self.subTest(flavor=flavor):
                state = _state(flavor, attempt=0, previous_rc=None, config_rc=1)
                self.assertFalse(_eval(_reset_guard(flavor), state))

    def test_retry_after_failure_on_fresh_install_resets(self):
        for flavor in ATTEMPT_FILES:
            with self.subTest(flavor=flavor):
                state = _state(flavor, attempt=1, previous_rc=3, config_rc=1)
                self.assertTrue(_eval(_reset_guard(flavor), state))

    def test_existing_installation_is_never_reset(self):
        for flavor in ATTEMPT_FILES:
            with self.subTest(flavor=flavor):
                state = _state(flavor, attempt=1, previous_rc=3, config_rc=0)
                self.assertFalse(_eval(_reset_guard(flavor), state))

    def test_retry_after_success_does_not_reset(self):
        for flavor in ATTEMPT_FILES:
            with self.subTest(flavor=flavor):
                state = _state(flavor, attempt=1, previous_rc=0, config_rc=1)
                self.assertFalse(_eval(_reset_guard(flavor), state))

    def test_the_installed_check_is_what_holds_the_gate_shut(self):
        for flavor in ATTEMPT_FILES:
            with self.subTest(flavor=flavor):
                state = _state(flavor, attempt=1, previous_rc=3, config_rc=0)
                without = [
                    expr
                    for expr in _reset_guard(flavor)
                    if "matomo_config_exists" not in expr
                ]
                self.assertEqual(len(without), len(_reset_guard(flavor)) - 1)
                self.assertTrue(_eval(without, state))

    def test_non_stack_host_does_not_reset(self):
        for flavor in ATTEMPT_FILES:
            with self.subTest(flavor=flavor):
                state = _state(
                    flavor, attempt=1, previous_rc=3, config_rc=1, stack_host=False
                )
                self.assertFalse(_eval(_reset_guard(flavor), state))


class TestAttemptLoopWiring(unittest.TestCase):
    def test_bootstrap_run_is_skipped_once_an_attempt_succeeded(self):
        for flavor, path in ATTEMPT_FILES.items():
            with self.subTest(flavor=flavor):
                runner = _find(
                    _tasks(path),
                    lambda t: "register" in t and t["register"].endswith("_attempt"),
                )
                guard = runner["when"]
                guard = guard if isinstance(guard, list) else [guard]
                context = {RESULT_VAR[flavor]: {"rc": 0}}
                self.assertFalse(_eval(guard, context))
                self.assertTrue(_eval(guard, {RESULT_VAR[flavor]: {"rc": 3}}))

    def test_attempt_result_is_promoted_to_the_flavor_result_var(self):
        for flavor, path in ATTEMPT_FILES.items():
            with self.subTest(flavor=flavor):
                promote = _find(_tasks(path), lambda t: "ansible.builtin.set_fact" in t)
                self.assertEqual(
                    promote["ansible.builtin.set_fact"][RESULT_VAR[flavor]],
                    "{{ matomo_bootstrap_attempt }}",
                )


class TestResetStateSafety(unittest.TestCase):
    def setUp(self):
        self.tasks = _tasks(RESET_STATE)
        self.probe = self.tasks[0]
        self.destructive = _find(self.tasks, lambda t: "block" in t)

    def test_probe_failure_is_fatal_rather_than_treated_as_fresh(self):
        self.assertNotIn("failed_when", self.probe)
        self.assertEqual(self.probe["register"], "matomo_reset_probe")

    def test_database_is_only_dropped_when_the_live_probe_reports_fresh(self):
        self.assertIsNotNone(self.destructive)
        self.assertEqual(
            self.destructive["when"], "(matomo_reset_probe.stdout | trim) == 'fresh'"
        )
        env = _env()
        guard = env.compile_expression(self.destructive["when"])
        self.assertTrue(guard(matomo_reset_probe={"stdout": "fresh\n"}))
        self.assertFalse(guard(matomo_reset_probe={"stdout": "installed\n"}))
        self.assertFalse(guard(matomo_reset_probe={"stdout": ""}))

    def test_the_drop_lives_behind_that_guard_and_nowhere_else(self):
        guarded = self.destructive["block"]
        self.assertTrue(any("reset_database.php" in str(task) for task in guarded))
        for task in guarded:
            self.assertNotIn("when", task)
        for task in (t for t in self.tasks if t is not self.destructive):
            self.assertNotIn("reset_database.php", str(task))


if __name__ == "__main__":
    unittest.main()
