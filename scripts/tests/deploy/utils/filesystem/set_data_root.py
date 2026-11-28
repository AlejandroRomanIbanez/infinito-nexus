"""Set ``data-root`` in a docker daemon.json, keeping every other key.

Args (argv): the daemon.json path, the data root directory.
"""

import json
import pathlib
import sys

path, root = pathlib.Path(sys.argv[1]), sys.argv[2]
config = (
    json.loads(path.read_text()) if path.is_file() and path.read_text().strip() else {}
)
config["data-root"] = root
path.write_text(json.dumps(config, indent=2) + "\n")
