"""Print the id of the first smoke workflow run created since the dispatch.

Reads the GitHub ``workflows/<id>/runs`` response JSON on stdin and prints an
empty line when no run was created at or after the dispatch time.

Args:
    argv[1]: dispatch time, UTC, formatted ``%Y-%m-%dT%H:%M:%SZ``.
"""

import json
import sys


def main(dispatch_time: str) -> int:
    data = json.load(sys.stdin)
    runs = [
        r
        for r in data.get("workflow_runs", [])
        if r.get("created_at", "") >= dispatch_time
    ]
    print(runs[0]["id"] if runs else "")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
