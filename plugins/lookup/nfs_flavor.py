from __future__ import annotations

from ansible.plugins.lookup import LookupBase

from utils.cache.base import _render_with_templar
from utils.roles.applications.config import get


class LookupModule(LookupBase):
    """Resolved svc-storage-nfs-server flavor (kernel/ganesha): {{ lookup('nfs_flavor') }}.

    Reads the `applications` variable (the variant-baked config in scope), not a
    re-merge of the role files; the dev/act->ganesha rule lives in meta/variants.yml.
    """

    def run(self, terms, variables=None, **kwargs):
        templar = getattr(self, "_templar", None)
        variables = variables or getattr(self._templar, "available_variables", {}) or {}
        applications = variables.get("applications") or {}
        flavor = get(
            applications=applications,
            application_id="svc-storage-nfs-server",
            config_path="services.nfs-server.flavor",
            strict=False,
            default="kernel",
            skip_missing_app=True,
        )
        return [
            _render_with_templar(
                flavor,
                templar=templar,
                variables=variables,
                raw_applications=applications,
            )
        ]
