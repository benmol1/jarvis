from datetime import datetime, timedelta, timezone

# `service` is a googleapiclient Calendar resource, e.g.
# googleapiclient.discovery.build("calendar", "v3", credentials=creds).
# OAuth credential setup is a separate step (needs the browser consent flow).


def get_upcoming_events(service, days: int = 7) -> list[dict]:
    now = datetime.now(timezone.utc)
    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=(now + timedelta(days=days)).isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return [
        {
            "summary": event.get("summary", "(no title)"),
            "start": event["start"].get("dateTime", event["start"].get("date")),
            "end": event["end"].get("dateTime", event["end"].get("date")),
        }
        for event in result.get("items", [])
    ]
