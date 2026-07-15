import os
from datetime import UTC, datetime, timedelta

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Visible marker stamped into the description of every event Jarvis creates.
# Jarvis may freely move/delete events carrying it; events without it belong to
# Ben (or others) and need his explicit approval before Jarvis touches them.
JARVIS_TAG = "🤖 [Jarvis]"


def get_calendar_service():
    """Build and return an authenticated Google Calendar service."""
    creds = Credentials(
        None,  # No initial access token - we'll refresh
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        # calendar.events covers both read and write of events. Re-mint the
        # refresh token after widening this — the old calendar.readonly token
        # will 403 on writes.
        scopes=["https://www.googleapis.com/auth/calendar.events"],
    )
    return build("calendar", "v3", credentials=creds)


def _is_jarvis(event: dict) -> bool:
    return JARVIS_TAG in (event.get("description") or "")


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
                    "id": event.get("id"),
                    "calendar_id": cal["id"],
                    "calendar": cal.get("summary", cal["id"]),
                    "summary": event.get("summary", "(no title)"),
                    "start": event["start"].get("dateTime", event["start"].get("date")),
                    "end": event["end"].get("dateTime", event["end"].get("date")),
                    "jarvis": _is_jarvis(event),
                }
            )

    # ponytail: lexical sort on ISO strings — all-day ("2026-07-15") sorts
    # before timed ("2026-07-15T09:00") on the same day, which is what we want.
    events.sort(key=lambda e: e["start"])
    return events


def get_event(calendar_id: str, event_id: str) -> dict:
    """Fetch one event, exposing whether Jarvis created it."""
    service = get_calendar_service()
    event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    return {
        "id": event["id"],
        "summary": event.get("summary", "(no title)"),
        "jarvis": _is_jarvis(event),
    }


def create_event(summary: str, start: str, end: str, calendar_id: str = "primary") -> dict:
    """Create a Jarvis-owned time-box. start/end are ISO 8601 with offset."""
    service = get_calendar_service()
    created_at = datetime.now().strftime("%d/%m/%y %H:%M")
    body = {
        "summary": summary,
        "description": f"{JARVIS_TAG} {created_at}",
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }
    return service.events().insert(calendarId=calendar_id, body=body).execute()


def update_event(calendar_id: str, event_id: str, start: str, end: str) -> dict:
    """Reschedule an event to new start/end (ISO 8601 with offset)."""
    service = get_calendar_service()
    body = {"start": {"dateTime": start}, "end": {"dateTime": end}}
    return service.events().patch(calendarId=calendar_id, eventId=event_id, body=body).execute()


def delete_event(calendar_id: str, event_id: str) -> None:
    service = get_calendar_service()
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
