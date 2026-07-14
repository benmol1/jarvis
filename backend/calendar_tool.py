import os
from datetime import UTC, datetime, timedelta

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def get_calendar_service():
    """Build and return an authenticated Google Calendar service."""
    creds = Credentials(
        None,  # No initial access token - we'll refresh
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
    )
    return build("calendar", "v3", credentials=creds)


def get_upcoming_events(days: int = 7) -> list[dict]:
    service = get_calendar_service()
    now = datetime.now(UTC)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days)).isoformat()

    # Every calendar the account can see (primary + shared, e.g. the one with
    # Emma), not just "primary".
    # ponytail: pulls all calendars; add `if cal.get("selected")` here if
    # subscribed/holiday calendars start adding noise.
    calendars = service.calendarList().list().execute().get("items", [])

    events = []
    for cal in calendars:
        result = (
            service.events()
            .list(
                calendarId=cal["id"],
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        for event in result.get("items", []):
            events.append(
                {
                    "calendar": cal.get("summary", cal["id"]),
                    "summary": event.get("summary", "(no title)"),
                    "start": event["start"].get("dateTime", event["start"].get("date")),
                    "end": event["end"].get("dateTime", event["end"].get("date")),
                }
            )

    # ponytail: lexical sort on ISO strings — all-day ("2026-07-15") sorts
    # before timed ("2026-07-15T09:00") on the same day, which is what we want.
    events.sort(key=lambda e: e["start"])
    return events
