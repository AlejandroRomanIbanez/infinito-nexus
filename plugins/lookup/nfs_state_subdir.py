from __future__ import annotations

from ansible.plugins.lookup import LookupBase

from utils.storage.nfs import STATE_SUBDIR


class LookupModule(LookupBase):
    """Cluster-shared NFS state subdir name: {{ lookup('nfs_state_subdir') }}."""

    def run(self, terms, variables=None, **kwargs):
        return [STATE_SUBDIR]
