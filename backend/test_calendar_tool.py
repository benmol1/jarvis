from unittest.mock import MagicMock

from calendar_tool import get_upcoming_events


def test_get_upcoming_events_parses_items():
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "summary": "Standup",
                "start": {"dateTime": "2026-07-03T09:00:00Z"},
                "end": {"dateTime": "2026-07-03T09:15:00Z"},
            },
            {
                "start": {"date": "2026-07-04"},
                "end": {"date": "2026-07-05"},
            },
        ]
    }

    events = get_upcoming_events(service)

    assert events == [
        {"summary": "Standup", "start": "2026-07-03T09:00:00Z", "end": "2026-07-03T09:15:00Z"},
        {"summary": "(no title)", "start": "2026-07-04", "end": "2026-07-05"},
    ]
