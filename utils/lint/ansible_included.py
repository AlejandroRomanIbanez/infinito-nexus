"""Pass on the stdin paths that lie outside the exclude_paths of .ansible-lint.

Reads one path per line on stdin and reads ``.ansible-lint`` from the working
directory.
"""

from __future__ import annotations

import sys

from utils.cache.yaml import load_yaml_any


def main() -> int:
    prefixes = [
        entry.strip("/") + "/"
        for entry in load_yaml_any(".ansible-lint")["exclude_paths"]
    ]
    for line in sys.stdin:
        path = line.rstrip("\n")
        if not any((path + "/").startswith(prefix) for prefix in prefixes):
            print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
