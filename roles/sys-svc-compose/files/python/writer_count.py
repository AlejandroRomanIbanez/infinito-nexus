"""Count the electors whose writer URL answers 2xx, from inside an instance container.

Args (argv): the ``http://`` writer URL of every elector.
Prints ``writers=<count> <urls>`` and exits 0 when exactly one answers.
"""

import sys
import urllib.request


def answers(url):
    """Args: url, an ``http://`` writer URL. Returns whether it answered 2xx within 2 s."""
    try:
        urllib.request.urlopen(url, timeout=2)  # noqa: S310 - callers pass http:// only
    except Exception:
        return False
    return True


up = [url for url in sys.argv[1:] if url.startswith("http://") and answers(url)]
print(f"writers={len(up)} {up}")
sys.exit(0 if len(up) == 1 else 1)
