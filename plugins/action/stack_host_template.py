#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

from ansible.module_utils.parsing.convert_bool import boolean as _to_bool
from ansible.plugins.action.template import ActionModule as TemplateActionModule
from ansible.template import trust_as_template

# trust_as_template required: Ansible 2.19+ refuses to render Python-constructed
# strings unless they carry the TrustedAsTemplate tag, returning the literal otherwise.
_IS_STACK_HOST_EXPR = trust_as_template("{{ IS_STACK_HOST | bool }}")


class ActionModule(TemplateActionModule):
    """Drop-in `template:` replacement that skips delivery on non-stack hosts.

    Inherits every `template:` argument. Adds:
      * `mode` default of "0644" when the caller omits it.
      * `IS_STACK_HOST` gate: returns `skipped: true` on hosts where
        `IS_STACK_HOST` evaluates to false, so the underlying `template:`
        never tries to write into a destination only the stack host owns
        (compose tree, nginx tree, keycloak admin volumes, ...).
    """

    def run(
        self, tmp: Any = None, task_vars: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if task_vars is None:
            task_vars = {}

        self._templar.available_variables = task_vars
        if not _to_bool(self._templar.template(_IS_STACK_HOST_EXPR)):
            return {
                "changed": False,
                "skipped": True,
                "skip_reason": "IS_STACK_HOST is false; this host does not own the destination",
            }

        self._task.args.setdefault("mode", "0644")
        return super().run(tmp=tmp, task_vars=task_vars)
