import os
import re
from unittest.mock import MagicMock, patch

from calendar_tool import JARVIS_TAG, create_event, get_upcoming_events


def test_get_upcoming_events_merges_all_calendars():
    events_by_calendar = {
        "primary": {
            "items": [
                {
                    "id": "evt1",
                    "summary": "Standup",
                    "description": "🤖 [Jarvis]",
                    "start": {"dateTime": "2026-07-03T09:00:00Z"},
                    "end": {"dateTime": "2026-07-03T09:15:00Z"},
                },
            ]
        },
        "emma_shared": {
            "items": [
                {
                    "id": "evt2",
                    "start": {"date": "2026-07-04"},
                    "end": {"date": "2026-07-05"},
                },
            ]
        },
    }

    mock_service = MagicMock()
    mock_service.calendarList.return_value.list.return_value.execute.return_value = {
        "items": [
            {"id": "primary", "summary": "Personal"},
            {"id": "emma_shared", "summary": "Ben & Emma"},
        ]
    }
    mock_service.events.return_value.list.side_effect = lambda calendarId, **_: MagicMock(
        execute=lambda: events_by_calendar[calendarId]
    )

    with patch.dict(
        os.environ,
        {
            "GOOGLE_CLIENT_ID": "test_id",
            "GOOGLE_CLIENT_SECRET": "test_secret",
            "GOOGLE_REFRESH_TOKEN": "test_refresh_token",
        },
    ):
        with patch("calendar_tool.build", return_value=mock_service):
            events = get_upcoming_events()

    # Both calendars present, sorted by start, tagged with calendar name.
    assert events == [
        {
            "id": "evt1",
            "calendar_id": "primary",
            "calendar": "Personal",
            "summary": "Standup",
            "start": "2026-07-03T09:00:00Z",
            "end": "2026-07-03T09:15:00Z",
            "jarvis": True,
        },
        {
            "id": "evt2",
            "calendar_id": "emma_shared",
            "calendar": "Ben & Emma",
            "summary": "(no title)",
            "start": "2026-07-04",
            "end": "2026-07-05",
            "jarvis": False,
        },
    ]


def test_create_event_stamps_tag_with_created_at_timestamp():
    mock_service = MagicMock()
    mock_service.events.return_value.insert.return_value.execute.return_value = {}

    with patch.dict(
        os.environ,
        {
            "GOOGLE_CLIENT_ID": "test_id",
            "GOOGLE_CLIENT_SECRET": "test_secret",
            "GOOGLE_REFRESH_TOKEN": "test_refresh_token",
        },
    ):
        with patch("calendar_tool.build", return_value=mock_service):
            create_event("Focus block", "2026-07-15T09:00:00+01:00", "2026-07-15T10:00:00+01:00")

    body = mock_service.events.return_value.insert.call_args.kwargs["body"]
    prefix = f"{JARVIS_TAG} - created at: "
    assert body["description"].startswith(prefix)
    timestamp = body["description"].removeprefix(prefix)
    assert re.fullmatch(r"\d{2}/\d{2}/\d{2} \d{2}:\d{2}", timestamp)
