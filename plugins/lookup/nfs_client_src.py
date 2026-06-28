from __future__ import annotations

from ansible.plugins.lookup import LookupBase

from utils.cache.base import _render_with_templar
from utils.roles.applications.config import get
from utils.storage.nfs import client_src, state_path


class LookupModule(LookupBase):
    """NFS client mount src (server:path): {{ lookup('nfs_client_src') }}."""

    def run(self, terms, variables=None, **kwargs):
        templar = getattr(self, "_templar", None)
        variables = variables or getattr(self._templar, "available_variables", {}) or {}
        nfs = variables.get("storage", {}).get("nfs", {})
        applications = variables.get("applications") or {}
        flavor = get(
            applications=applications,
            application_id="svc-storage-nfs-server",
            config_path="services.nfs-server.flavor",
            strict=False,
            default="kernel",
            skip_missing_app=True,
        )
        flavor = _render_with_templar(
            flavor, templar=templar, variables=variables, raw_applications=applications
        )
        state = state_path(nfs.get("export_base"), variables.get("STORAGE_NFS_STATE_SUBDIR"))
        return [client_src(nfs.get("server"), nfs.get("version", 4), flavor, state)]
