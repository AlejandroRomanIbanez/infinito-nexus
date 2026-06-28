from __future__ import annotations

from ansible.plugins.lookup import LookupBase

from utils.storage.nfs import state_path


class LookupModule(LookupBase):
    """Cluster-shared NFS state dir: {{ lookup('nfs_state_path') }}."""

    def run(self, terms, variables=None, **kwargs):
        export_base = self._templar.template("{{ storage.nfs.export_base }}")
        subdir = self._templar.template("{{ STORAGE_NFS_STATE_SUBDIR }}")
        return [state_path(export_base, subdir)]
