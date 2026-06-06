#!/usr/bin/env python3
#
# Local action plugin: drop-in replacement for `template:` that skips
# delivery on non-stack hosts. Wrapped in trust_as_template because
# Ansible 2.19+ refuses to render strings constructed in Python unless
# they carry the TrustedAsTemplate tag.

from __future__ import annotations

from typing import Any

from ansible.module_utils.parsing.convert_bool import boolean as _to_bool
from ansible.plugins.action.template import ActionModule as TemplateActionModule
from ansible.template import trust_as_template

_IS_STACK_HOST_EXPR = trust_as_template("{{ IS_STACK_HOST | bool }}")


class ActionModule(TemplateActionModule):
    """Drop-in `template:` replacement that skips on non-stack hosts.

    Inherits every `template:` argument. Adds:
      * `mode` default of "0644" when omitted.
      * `IS_STACK_HOST` gate: returns `skipped: true` on workers, so the
        underlying `template:` never tries to write into the
        stack-host-only nginx tree.
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
                "skip_reason": "IS_STACK_HOST is false; worker hosts do not own the destination",
            }

        self._task.args.setdefault("mode", "0644")
        return super().run(tmp=tmp, task_vars=task_vars)
