# nocheck: mirrored-unit-test - runs inside the Friendica container on stdin of container exec and rewrites the image-baked ldapauth addon; the ldapauth Playwright spec exercises the first-login path it repairs
"""Make the ldapauth autocreate path return the user row the hook expects.

Upstream ``ldap_createaccount`` returns the bare ``User::create()`` result,
``['user' => UserRow, 'password' => '']``, so the ``authenticate`` hook's
``!empty($user['uid'])`` check fails and first-login users never get a
session. The addon tree is image-baked, so every re-pulled image needs the
patch again.

Prints ``ALREADY`` when the file is patched, ``PATCHED`` after patching it,
and ``NO-MATCH ...`` with exit code 1 when the upstream return line changed.

Args:
    argv[1]: absolute path of ldapauth.php inside the container.
"""

import sys
from pathlib import Path

ORIGINAL = "\t\treturn $user;"
PATCHED = "\t\treturn $user['user'] ?? $user;"


def main(path: Path) -> int:
    try:
        source = path.read_text()
    except OSError as error:
        print(error, file=sys.stderr)
        source = ""
    if PATCHED in source:
        print("ALREADY")
        return 0
    if ORIGINAL not in source:
        print("NO-MATCH ldap_createaccount return-line shape changed upstream")
        return 1
    path.write_text(source.replace(ORIGINAL, PATCHED, 1))
    print("PATCHED")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
