import os
import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Visible marker stamped into the description of every event Jarvis creates.
# Jarvis may freely move/delete events carrying it; events without it belong to
# Ben (or others) and need his explicit approval before Jarvis touches them.
JARVIS_TAG = "🤖 [Jarvis]"

# Parses the metadata line Jarvis writes into descriptions, e.g.
# "🤖 [Jarvis] - created at: 15/07/26 09:00 - modified at: 16/07/26 11:30".
_META_RE = re.compile(
    r"created at:\s*(?P<created>\d{2}/\d{2}/\d{2} \d{2}:\d{2})"
    r"(?:\s*-\s*modified at:\s*(?P<modified>\d{2}/\d{2}/\d{2} \d{2}:\d{2}))?"
)


def _now_stamp() -> str:
    # Override with JARVIS_TIMEZONE (IANA name) if Ben isn't in the UK — mirrors
    # prompt.py's "now" so description stamps agree with what Jarvis is told.
    tz = ZoneInfo(os.environ.get("JARVIS_TIMEZONE", "Europe/London"))
    return datetime.now(tz).strftime("%d/%m/%y %H:%M")


def _compose_description(body: str | None, created_at: str, modified_at: str | None = None) -> str:
    """Build a Jarvis-owned event description: a metadata line carrying the tag
    and timestamps, with the human-readable body (if any) below it."""
    meta = f"{JARVIS_TAG} - created at: {created_at}"
    if modified_at:
        meta += f" - modified at: {modified_at}"
    body = (body or "").strip()
    return f"{meta}\n\n{body}" if body else meta


def _split_description(desc: str | None) -> tuple[str | None, str]:
    """Pull (created_at, body) back out of an existing Jarvis description so a
    modify can preserve the original creation time and any prior body."""
    lines = (desc or "").split("\n")
    created = None
    body_start = 0
    if lines and JARVIS_TAG in lines[0]:
        match = _META_RE.search(lines[0])
        if match:
            created = match.group("created")
        body_start = 1
        if body_start < len(lines) and lines[body_start].strip() == "":
            body_start += 1  # skip the blank separator line
    return created, "\n".join(lines[body_start:]).strip()


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
            _, body = _split_description(event.get("description"))
            events.append(
                {
                    "id": event.get("id"),
                    "calendar_id": cal["id"],
                    "calendar": cal.get("summary", cal["id"]),
                    "summary": event.get("summary", "(no title)"),
                    "start": event["start"].get("dateTime", event["start"].get("date")),
                    "end": event["end"].get("dateTime", event["end"].get("date")),
                    "location": event.get("location"),
                    "description": body,
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
    """Fetch one event, exposing whether Jarvis created it. `description` is the
    human-readable body with any Jarvis metadata line stripped, so callers can
    append to it without duplicating the tag/timestamps."""
    service = get_calendar_service()
    event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    _, body = _split_description(event.get("description"))
    return {
        "id": event["id"],
        "summary": event.get("summary", "(no title)"),
        "start": event["start"].get("dateTime", event["start"].get("date")),
        "location": event.get("location"),
        "description": body,
        "jarvis": _is_jarvis(event),
    }


def find_conflicts(start: str, end: str) -> list[dict]:
    """Events across all calendars overlapping [start, end). Google's list
    already returns events that intersect the window, so this is just a filtered
    lookup used to warn about double-booking far outside the prompt's 14-day
    context. Returns [] rather than raising if the lookup fails."""
    try:
        return get_events_in_range(start, end)
    except Exception:
        return []


def create_event(
    summary: str,
    start: str,
    end: str,
    calendar_id: str = "primary",
    location: str | None = None,
    description: str | None = None,
    attendees: list[str] | None = None,
) -> dict:
    """Create a Jarvis-owned event. start/end are ISO 8601 with offset. When
    attendees are given, invites are actually emailed (sendUpdates=all)."""
    service = get_calendar_service()
    body = {
        "summary": summary,
        "description": _compose_description(description, _now_stamp()),
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = [{"email": e} for e in attendees]
    kwargs = {"calendarId": calendar_id, "body": body}
    if attendees:
        kwargs["sendUpdates"] = "all"
    return service.events().insert(**kwargs).execute()


def modify_event(
    calendar_id: str,
    event_id: str,
    start: str | None = None,
    end: str | None = None,
    title: str | None = None,
    location: str | None = None,
    description: str | None = None,
    attendees: list[str] | None = None,
) -> dict:
    """Patch any subset of an event's fields. On a Jarvis-owned event the
    description keeps its original "created at" and gains a fresh "modified at"
    stamp. A foreign event (no tag) is never stamped — that would silently flip
    ownership and let Jarvis mutate it without approval afterwards."""
    service = get_calendar_service()
    existing = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    is_jarvis = _is_jarvis(existing)

    body: dict = {}
    if title is not None:
        body["summary"] = title
    if start is not None:
        body["start"] = {"dateTime": start}
    if end is not None:
        body["end"] = {"dateTime": end}
    if location is not None:
        body["location"] = location
    if attendees is not None:
        body["attendees"] = [{"email": e} for e in attendees]

    if is_jarvis:
        created, existing_body = _split_description(existing.get("description"))
        new_body = description if description is not None else existing_body
        body["description"] = _compose_description(new_body, created or _now_stamp(), _now_stamp())
    elif description is not None:
        body["description"] = description  # foreign event: leave it unstamped

    kwargs = {"calendarId": calendar_id, "eventId": event_id, "body": body}
    if attendees is not None:
        kwargs["sendUpdates"] = "all"
    return service.events().patch(**kwargs).execute()


def respond_to_event(calendar_id: str, event_id: str, response: str) -> dict:
    """RSVP on Ben's behalf. response is accepted/declined/tentative. This is
    Ben's own attendance status, not a mutation of someone else's event, so it
    applies immediately."""
    service = get_calendar_service()
    event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    attendees = event.get("attendees", [])
    me = next((a for a in attendees if a.get("self")), None)
    if me is None:
        raise ValueError("Ben is not an attendee of this event")
    me["responseStatus"] = response
    return (
        service.events()
        .patch(
            calendarId=calendar_id,
            eventId=event_id,
            body={"attendees": attendees},
            sendUpdates="all",
        )
        .execute()
    )


def delete_event(calendar_id: str, event_id: str) -> None:
    service = get_calendar_service()
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()


def move_event_to_calendar(calendar_id: str, event_id: str, destination_calendar_id: str) -> dict:
    """Move an event to a different calendar, keeping its time. Google's
    events.move — distinct from modify_event, which patches fields in place."""
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
    created_at = _now_stamp()
    body = {
        "summary": src.get("summary", "(no title)"),
        "description": f"{JARVIS_TAG} - created at: {created_at}",
        # Copy start/end verbatim so all-day vs timed and timezone are preserved.
        "start": src["start"],
        "end": src["end"],
    }
    return service.events().insert(calendarId=destination_calendar_id, body=body).execute()
