"""One-shot script to mint a fresh GOOGLE_REFRESH_TOKEN.

Run this when the calendar starts failing with:
    RefreshError: invalid_grant: Token has been expired or revoked.

Usage (from backend/):
    GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... uv run python reauth_google.py

It opens a browser, asks you to grant read-only calendar access, and prints a
refresh token to paste into the Pi's .env. It writes nothing itself.

NOTE: if the OAuth consent screen is still in "Testing" status, Google expires
the refresh token after 7 days and you will be back here. Publish the app to
Production in the Google Cloud Console to make the token durable.
"""

import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

# Must match the scope requested in calendar_tool.py, or the minted token will
# not be accepted for the calls we actually make.
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def main() -> int:
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    if not client_id or not client_secret:
        print(
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set.\n"
            "Copy them from the Pi's .env, or from the Google Cloud Console\n"
            "(APIs & Services -> Credentials).",
            file=sys.stderr,
        )
        return 1

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
    )

    # access_type=offline is what makes Google issue a refresh token at all;
    # prompt=consent forces a new one even if this account was authorised before
    # (otherwise a re-auth silently returns an access token with no refresh token).
    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
    )

    if not creds.refresh_token:
        print(
            "Google returned no refresh token. This usually means the consent\n"
            "screen was skipped — revoke the app at "
            "https://myaccount.google.com/permissions and retry.",
            file=sys.stderr,
        )
        return 1

    print("\nPaste this into the Pi's .env, then redeploy:\n")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
