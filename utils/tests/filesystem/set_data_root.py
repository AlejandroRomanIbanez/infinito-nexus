"""Set ``data-root`` in a docker daemon.json, keeping every other key.

Args (argv): the daemon.json path, the data root directory.
"""

import json
import pathlib
import sys


def set_data_root(path: pathlib.Path, root: str) -> None:
    """Args: the daemon.json path and the data root directory to write into it."""
    text = path.read_text() if path.is_file() else ""  # nocheck: cache-read  host file
    config = json.loads(text) if text.strip() else {}
    config["data-root"] = root
    path.write_text(json.dumps(config, indent=2) + "\n")


if __name__ == "__main__":
    set_data_root(pathlib.Path(sys.argv[1]), sys.argv[2])
