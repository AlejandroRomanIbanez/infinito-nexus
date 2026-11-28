"""Count the online runners in a GitHub ``actions/runners`` response.

Reads the response JSON on stdin and prints the count on stdout.
"""

import json
import sys


def main() -> int:
    data = json.load(sys.stdin)
    print(sum(1 for r in data.get("runners", []) if r.get("status") == "online"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
