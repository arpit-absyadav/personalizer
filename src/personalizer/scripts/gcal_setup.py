"""One-time Google Calendar OAuth setup.

Run via the `personalizer-setup` console script. Reads the user-supplied
credentials.json from ~/.personalizer/google/, runs the InstalledAppFlow
local-server consent flow, and writes token.json next to it.

Must run BEFORE the TUI — `run_local_server` would fight Textual for the screen.
"""

from __future__ import annotations

import sys

from .. import paths
from ..services.gcal import SCOPES


def main() -> None:
    paths.ensure_dirs()

    if not paths.GOOGLE_CREDENTIALS.exists():
        print(
            f"ERROR: missing {paths.GOOGLE_CREDENTIALS}\n"
            "Create an OAuth 2.0 Client ID (type: Desktop app) in Google Cloud "
            "Console, download the JSON, and save it to that path.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Lazy import so installing the package without the deps doesn't break
    # `personalizer --help`.
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(
        str(paths.GOOGLE_CREDENTIALS), SCOPES
    )
    creds = flow.run_local_server(port=0)
    paths.GOOGLE_TOKEN.write_text(creds.to_json(), encoding="utf-8")
    print(f"OK — wrote {paths.GOOGLE_TOKEN}")
    print("You can now run `personalizer`.")


if __name__ == "__main__":
    main()
