"""Exit 0 once the engine answers its health URL, else the not-ready code.

Args (argv): the health URL, the request timeout in seconds, the exit code for "not ready yet".
"""

import sys
import urllib.request

try:
    urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        sys.argv[1], timeout=float(sys.argv[2])
    )
except OSError:
    sys.exit(int(sys.argv[3]))
