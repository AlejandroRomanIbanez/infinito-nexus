"""Print the distribution base image a distro's image builds FROM.

Usage:
  python -m cli.meta.ci.parent_image <distro> <owner> <tag>
"""

from __future__ import annotations

import sys

from utils.distros import base_image


def main(argv: list[str]) -> int:
    """Print the base image reference.

    Args:
        argv: distro id, registry owner and image tag, in that order.
    """
    print(base_image(argv[0], owner=argv[1], tag=argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
