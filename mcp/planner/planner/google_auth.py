"""One-time Google OAuth login for the planner (run on the desktop, not the server).

    uv run --extra auth python -m planner.google_auth \\
        --client-secret ~/.config/assistant/client_secret.json \\
        --out ~/.config/assistant/google_token.json

Opens a browser, asks for the calendar.events scope only, and writes a token
file (mode 600) holding the refresh token. Copy that file to the server at
~/assistant-data/planner/google_token.json. The token is never printed.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client-secret", required=True, type=Path, help="OAuth client JSON (Desktop app) from Google Cloud")
    ap.add_argument("--out", required=True, type=Path, help="where to write the token JSON")
    args = ap.parse_args(argv)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("google-auth-oauthlib is missing; run with: uv run --extra auth python -m planner.google_auth ...", file=sys.stderr)
        return 2

    client_secret = args.client_secret.expanduser()
    out = args.out.expanduser()
    if not client_secret.is_file():
        print(f"client secret file not found: {client_secret}", file=sys.stderr)
        return 2

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), scopes=SCOPES)
    # prompt=consent makes Google return a refresh token even on a repeat login.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent", open_browser=True)
    if not creds.refresh_token:
        print("Google returned no refresh token; remove the app's access at myaccount.google.com/permissions and retry.", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    os.chmod(out, 0o600)
    print(f"wrote {out} (scopes: {', '.join(SCOPES)})")
    print("next: scp it to the server as ~/assistant-data/planner/google_token.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
