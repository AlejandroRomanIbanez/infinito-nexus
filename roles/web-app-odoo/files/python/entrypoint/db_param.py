# nocheck: mirrored-unit-test - the whole module is one configparser lookup the Odoo entrypoint runs inside the image against the odoo.conf that ODOO_RC names
"""Print one ``[options]`` value of the Odoo config, empty when it is unset.

Args:
    argv[1]: path of the Odoo config file.
    argv[2]: option name.
"""

import configparser
import sys


def main(rc: str, key: str) -> int:
    config = configparser.ConfigParser()
    config.read(rc)
    print(config["options"].get(key, ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
