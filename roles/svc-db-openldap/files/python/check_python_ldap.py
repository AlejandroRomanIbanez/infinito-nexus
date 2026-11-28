"""Import python-ldap and print its version and location, with a traceback when the import fails."""

# nocheck: mirrored-unit-test - runs on the target with the Ansible interpreter only to show whether python-ldap imports there

import traceback

try:
    import ldap

    print("python-ldap version:", ldap.__version__)
    print("ldap module:", ldap.__file__)
except Exception:
    traceback.print_exc()
    raise
