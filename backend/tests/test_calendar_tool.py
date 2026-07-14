import os
from unittest.mock import MagicMock, patch

from calendar_tool import get_upcoming_events


def test_get_upcoming_events_merges_all_calendars():
    events_by_calendar = {
        "primary": {
            "items": [
                {
                    "summary": "Standup",
                    "start": {"dateTime": "2026-07-03T09:00:00Z"},
                    "end": {"dateTime": "2026-07-03T09:15:00Z"},
                },
            ]
        },
        "emma_shared": {
            "items": [
                {
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
            "calendar": "Personal",
            "summary": "Standup",
            "start": "2026-07-03T09:00:00Z",
            "end": "2026-07-03T09:15:00Z",
        },
        {
            "calendar": "Ben & Emma",
            "summary": "(no title)",
            "start": "2026-07-04",
            "end": "2026-07-05",
        },
    ]
