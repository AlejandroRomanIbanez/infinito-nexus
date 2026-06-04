"""Lookup `compose_container_name`: emit `container_name: "<name>"` only in
compose mode. Swarm mode rejects container_name alongside replicas > 1 with
`services.deploy.replicas: can't set container_name and X as container name
must be unique`.

The lookup reads DEPLOYMENT_MODE from the templating context, so the call
site is just:

    {{ lookup('compose_container_name', MY_CONTAINER) }}

No explicit DEPLOYMENT_MODE pass-through required.
"""

from __future__ import annotations

import contextlib
from typing import Any

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase


class LookupModule(LookupBase):
    def run(
        self,
        terms: list[Any] | None,
        variables: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[str]:
        if not terms or len(terms) != 1:
            raise AnsibleError(
                "compose_container_name lookup requires exactly one term: the container name"
            )
        name = str(terms[0])

        vars_ = variables or getattr(self._templar, "available_variables", {}) or {}
        raw_mode = vars_.get("DEPLOYMENT_MODE", "compose")
        templar = getattr(self, "_templar", None)
        if templar is not None:
            with contextlib.suppress(Exception):
                raw_mode = templar.template(raw_mode)

        if str(raw_mode).strip() == "swarm":
            return [""]
        return [f'container_name: "{name}"']
