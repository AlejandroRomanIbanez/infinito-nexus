from __future__ import annotations

from ansible.plugins.lookup import LookupBase

from utils.storage.nfs import mount_opts


class LookupModule(LookupBase):
    """NFS mount options: {{ lookup('nfs_mount_opts') }}."""

    def run(self, terms, variables=None, **kwargs):
        version = self._templar.template("{{ storage.nfs.version | default(4) }}")
        runtime = self._templar.template("{{ RUNTIME | default('host') }}")
        return [mount_opts(version, runtime)]
