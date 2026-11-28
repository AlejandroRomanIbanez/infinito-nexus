# nocheck: mirrored-unit-test - imports oauth_dropins, which only the build stage of the Bridgy Fed image installs, and links a path that exists only inside that image
import contextlib
from pathlib import Path

import oauth_dropins


def main() -> int:
    target = Path(oauth_dropins.__file__).parent / "static"
    link = Path("/app/oauth_dropins_static")
    with contextlib.suppress(FileExistsError):
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(target)
    print("Symlinked oauth_dropins_static ->", target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
