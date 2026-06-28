from __future__ import annotations

from ansible.plugins.lookup import LookupBase

from utils.storage.nfs import fstype


class LookupModule(LookupBase):
    """NFS mount fstype (nfs4/nfs): {{ lookup('nfs_fstype') }}."""

    def run(self, terms, variables=None, **kwargs):
        version = self._templar.template("{{ storage.nfs.version | default(4) }}")
        return [fstype(version)]
