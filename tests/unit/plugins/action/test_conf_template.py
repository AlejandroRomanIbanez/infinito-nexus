import unittest
from unittest.mock import patch

from plugins.action.conf_template import ActionModule


class _FakeTask:
    def __init__(self, *, args=None):
        self.args = {} if args is None else dict(args)


class _FakeTemplar:
    def __init__(self, *, loader=None, variables=None):
        self.loader = loader
        self.variables = variables or {}

    def template(self, raw):
        is_stack_host_val = self.variables.get("IS_STACK_HOST")
        if raw == "{{ IS_STACK_HOST | bool }}":
            if is_stack_host_val is None:
                return False
            return is_stack_host_val
        return raw


def _make_action(task):
    action = object.__new__(ActionModule)
    action._task = task
    action._loader = object()
    action._templar = object()
    return action


def _patch_templar(is_stack_host_value):
    def _factory(loader=None, variables=None):
        if variables is None:
            variables = {}
        if is_stack_host_value is not None:
            variables = {**variables, "IS_STACK_HOST": is_stack_host_value}
        return _FakeTemplar(loader=loader, variables=variables)

    return patch("plugins.action.conf_template.Templar", side_effect=_factory)


class TestConfTemplate(unittest.TestCase):
    def test_skips_silently_on_non_stack_host(self):
        task = _FakeTask(
            args={"src": "x.j2", "dest": "/etc/nginx/conf.d/global/x.conf"}
        )
        action = _make_action(task)

        with _patch_templar(False):
            result = action.run(task_vars={})

        self.assertTrue(result["skipped"])
        self.assertFalse(result["changed"])
        self.assertIn("IS_STACK_HOST", result["skip_reason"])

    def test_skips_when_templar_returns_string_false(self):
        task = _FakeTask(
            args={"src": "x.j2", "dest": "/etc/nginx/conf.d/global/x.conf"}
        )
        action = _make_action(task)

        with _patch_templar("False"):
            result = action.run(task_vars={})

        self.assertTrue(result["skipped"])

    def test_runs_when_templar_returns_string_true(self):
        task = _FakeTask(args={"src": "x.j2", "dest": "/etc/nginx/custom.conf"})
        action = _make_action(task)

        with (
            _patch_templar("True"),
            patch(
                "plugins.action.conf_template.TemplateActionModule.run",
                return_value={"changed": True},
            ) as super_run,
        ):
            action.run(task_vars={})

        super_run.assert_called_once()

    def test_delegates_to_template_on_stack_host(self):
        task = _FakeTask(args={"src": "x.j2", "dest": "/etc/nginx/custom.conf"})
        action = _make_action(task)

        with (
            _patch_templar(True),
            patch(
                "plugins.action.conf_template.TemplateActionModule.run",
                return_value={"changed": True},
            ) as super_run,
        ):
            action.run(task_vars={})

        self.assertEqual(task.args["dest"], "/etc/nginx/custom.conf")
        super_run.assert_called_once()

    def test_defaults_mode_to_0644_when_unset(self):
        task = _FakeTask(args={"src": "x.j2", "dest": "/etc/x.conf"})
        action = _make_action(task)

        with (
            _patch_templar(True),
            patch(
                "plugins.action.conf_template.TemplateActionModule.run",
                return_value={"changed": True},
            ),
        ):
            action.run(task_vars={})

        self.assertEqual(task.args["mode"], "0644")

    def test_keeps_caller_supplied_mode(self):
        task = _FakeTask(args={"src": "x.j2", "dest": "/etc/x.conf", "mode": "0600"})
        action = _make_action(task)

        with (
            _patch_templar(True),
            patch(
                "plugins.action.conf_template.TemplateActionModule.run",
                return_value={"changed": True},
            ),
        ):
            action.run(task_vars={})

        self.assertEqual(task.args["mode"], "0600")

    def test_constructs_fresh_templar_with_task_vars(self):
        task = _FakeTask(args={"src": "x.j2", "dest": "/etc/x.conf"})
        action = _make_action(task)

        captured_vars = {}

        def _factory(loader=None, variables=None):
            captured_vars.update(variables or {})
            return _FakeTemplar(
                loader=loader, variables={**(variables or {}), "IS_STACK_HOST": True}
            )

        with (
            patch("plugins.action.conf_template.Templar", side_effect=_factory),
            patch(
                "plugins.action.conf_template.TemplateActionModule.run",
                return_value={"changed": True},
            ),
        ):
            action.run(task_vars={"IS_STACK_HOST": True, "ANSIBLE_VERSION": "9.0"})

        self.assertEqual(captured_vars.get("IS_STACK_HOST"), True)
        self.assertEqual(captured_vars.get("ANSIBLE_VERSION"), "9.0")

    def test_passes_through_all_extra_template_args(self):
        task = _FakeTask(
            args={
                "src": "x.j2",
                "dest": "/etc/x.conf",
                "owner": "nginx",
                "group": "nginx",
                "backup": True,
                "validate": "nginx -t -c %s",
            }
        )
        action = _make_action(task)

        with (
            _patch_templar(True),
            patch(
                "plugins.action.conf_template.TemplateActionModule.run",
                return_value={"changed": True},
            ),
        ):
            action.run(task_vars={})

        self.assertEqual(task.args["owner"], "nginx")
        self.assertEqual(task.args["group"], "nginx")
        self.assertTrue(task.args["backup"])
        self.assertEqual(task.args["validate"], "nginx -t -c %s")


if __name__ == "__main__":
    unittest.main()
