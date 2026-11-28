"""Print the architectures an image manifest must serve but does not.

Prints them space-separated, an empty line when the manifest serves all.

Env:
  MANIFEST             ``docker manifest inspect`` output; empty when the
                       reference could not be inspected
  IMAGE_ARCHITECTURES  narrows what the reference must serve; empty asks for
                       the whole architecture pool
"""

from __future__ import annotations

import json
import os
import sys

from utils.github.variant.pools import resolve_architectures


def main() -> int:
    raw = os.environ["MANIFEST"].strip()
    index = json.loads(raw) if raw else {}
    served = {
        entry.get("platform", {}).get("architecture")
        for entry in index.get("manifests", [])
    }
    required = resolve_architectures(os.environ["IMAGE_ARCHITECTURES"])
    print(" ".join(name for name in required if name not in served))
    return 0


if __name__ == "__main__":
    sys.exit(main())
