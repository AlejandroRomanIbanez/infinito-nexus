from __future__ import annotations

from ansible.plugins.lookup import LookupBase

from utils.cache.applications import get_merged_applications
from utils.cache.base import _render_with_templar
from utils.roles.applications.config import get


class LookupModule(LookupBase):
    """Resolved svc-storage-nfs-server flavor (kernel/ganesha): {{ lookup('nfs_flavor') }}.

    Reads the same variant-merged config the server uses, so the client picks the
    mount style without re-deriving the RUNTIME rule (that lives in meta/variants.yml).
    """

    def run(self, terms, variables=None, **kwargs):
        templar = getattr(self, "_templar", None)
        variables = variables or getattr(self._templar, "available_variables", {}) or {}
        applications = get_merged_applications(
            variables=variables,
            roles_dir=kwargs.get("roles_dir"),
            templar=templar,
        )
        value = get(
            applications=applications,
            application_id="svc-storage-nfs-server",
            config_path="services.nfs-server.flavor",
            strict=False,
            default="kernel",
            skip_missing_app=True,
        )
        return [
            _render_with_templar(
                value,
                templar=templar,
                variables=variables,
                raw_applications=applications,
            )
        ]
