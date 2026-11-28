"""Ask an instance's own primary check over HTTP, from inside the instance container.

Args (argv): the check port, the check path.
Exits 0 on a 2xx answer, 1 on an error status, 2 when the check cannot be asked.
"""

import sys
import urllib.error
import urllib.request

try:
    urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}{sys.argv[2]}", timeout=5)
except urllib.error.HTTPError:
    sys.exit(1)
except Exception:
    sys.exit(2)
