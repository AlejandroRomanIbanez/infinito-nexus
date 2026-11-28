"""Fill the per-instance cn=config template and write it readable by its owner only.

Args (argv): the template path, the target path.
Env: ROOT_PW_HASH, OPENLDAP_UID, OPENLDAP_GID and LDAP_ROOT_PW replace
``@ROOT_PW_HASH@``, ``@OPENLDAP_UID@``, ``@OPENLDAP_GID@`` and ``@ROOT_PW@``.
"""

import os
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
for token in ("ROOT_PW_HASH", "OPENLDAP_UID", "OPENLDAP_GID"):
    text = text.replace(f"@{token}@", os.environ[token])
text = text.replace("@ROOT_PW@", os.environ["LDAP_ROOT_PW"])
fd = os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    handle.write(text)
