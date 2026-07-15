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
        # calendar.events covers read/write of events but NOT calendarList.list
        # (listing the user's calendars) — that needs its own scope, or the
        # calendar-list call 403s with "insufficient scopes". Re-mint the
        # refresh token after widening this.
        scopes=[
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
        ],
    )
    return build("calendar", "v3", credentials=creds)


def _is_jarvis(event: dict) -> bool:
    return JARVIS_TAG in (event.get("description") or "")


def get_upcoming_events(days: int = 14) -> list[dict]:
    now = datetime.now(UTC)
    return get_events_in_range(now.isoformat(), (now + timedelta(days=days)).isoformat())


def get_events_in_range(time_min: str, time_max: str) -> list[dict]:
    """Events across all calendars in an arbitrary ISO 8601 window. Backs both
    the default prompt-context lookahead and the on-demand list_events tool."""
    service = get_calendar_service()

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


def list_calendars() -> list[dict]:
    """All calendars the account can see, as {id, name}. Lets Jarvis target a
    calendar by name (e.g. "Joint") even when it has no upcoming events to
    reveal its id."""
    service = get_calendar_service()
    return [
        {"id": c["id"], "name": c.get("summary", c["id"])}
        for c in service.calendarList().list().execute().get("items", [])
    ]


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
        "description": f"{JARVIS_TAG} - created at: {created_at}",
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


def move_event_to_calendar(calendar_id: str, event_id: str, destination_calendar_id: str) -> dict:
    """Move an event to a different calendar, keeping its time. Google's
    events.move — distinct from update_event, which only patches start/end."""
    service = get_calendar_service()
    return (
        service.events()
        .move(calendarId=calendar_id, eventId=event_id, destination=destination_calendar_id)
        .execute()
    )


def copy_event(calendar_id: str, event_id: str, destination_calendar_id: str) -> dict:
    """Duplicate an event into another calendar, leaving the original untouched.
    The copy is stamped Jarvis-owned so Jarvis can manage it later."""
    service = get_calendar_service()
    src = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    created_at = datetime.now().strftime("%d/%m/%y %H:%M")
    body = {
        "summary": src.get("summary", "(no title)"),
        "description": f"{JARVIS_TAG} - created at: {created_at}",
        # Copy start/end verbatim so all-day vs timed and timezone are preserved.
        "start": src["start"],
        "end": src["end"],
    }
    return service.events().insert(calendarId=destination_calendar_id, body=body).execute()
