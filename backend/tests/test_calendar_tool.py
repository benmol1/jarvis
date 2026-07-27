import os
import re
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from calendar_tool import JARVIS_TAG, create_event, get_events_in_range, get_upcoming_events


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
            "busy": True,
            "color": None,
        },
        {
            "id": "evt2",
            "calendar_id": "emma_shared",
            "calendar": "Ben & Emma",
            "summary": "(no title)",
            "start": "2026-07-04",
            "end": "2026-07-05",
            "jarvis": False,
            "busy": True,
            "color": None,
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


def test_create_event_busy_false_and_color_id_set_transparency_and_colour():
    mock_service = MagicMock()
    # The real Calendar API echoes back the event resource it was given,
    # including transparency/colorId — mimic that instead of returning {}.
    mock_service.events.return_value.insert.side_effect = lambda calendarId, body, **_: MagicMock(
        execute=lambda: body
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
            result = create_event(
                "Emma's reminder",
                "2026-07-15T09:00:00+01:00",
                "2026-07-15T10:00:00+01:00",
                busy=False,
                color_id="11",
            )

    body = mock_service.events.return_value.insert.call_args.kwargs["body"]
    assert body["transparency"] == "transparent"
    assert body["colorId"] == "11"
    # The returned dict is enriched with the derived, UI-facing fields too.
    assert result["busy"] is False
    assert result["color"] == "Tomato"


def test_get_events_in_range_surfaces_busy_and_colour():
    mock_service = MagicMock()
    mock_service.calendarList.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "primary", "summary": "Personal"}]
    }
    mock_service.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "evt1",
                "summary": "Emma's reminder",
                "transparency": "transparent",
                "colorId": "11",
                "start": {"dateTime": "2026-07-03T09:00:00Z"},
                "end": {"dateTime": "2026-07-03T09:15:00Z"},
            },
        ]
    }

    with patch.dict(
        os.environ,
        {
            "GOOGLE_CLIENT_ID": "test_id",
            "GOOGLE_CLIENT_SECRET": "test_secret",
            "GOOGLE_REFRESH_TOKEN": "test_refresh_token",
        },
    ):
        with patch("calendar_tool.build", return_value=mock_service):
            events = get_events_in_range("2026-07-01T00:00:00Z", "2026-07-10T00:00:00Z")

    assert events[0]["busy"] is False
    assert events[0]["color"] == "Tomato"


def test_get_upcoming_events_looks_back_3_days_by_default():
    mock_service = MagicMock()
    mock_service.calendarList.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "primary", "summary": "Personal"}]
    }
    mock_service.events.return_value.list.return_value.execute.return_value = {"items": []}

    with patch.dict(
        os.environ,
        {
            "GOOGLE_CLIENT_ID": "test_id",
            "GOOGLE_CLIENT_SECRET": "test_secret",
            "GOOGLE_REFRESH_TOKEN": "test_refresh_token",
        },
    ):
        with patch("calendar_tool.build", return_value=mock_service):
            get_upcoming_events()

    kwargs = mock_service.events.return_value.list.call_args.kwargs
    time_min = datetime.fromisoformat(kwargs["timeMin"])
    time_max = datetime.fromisoformat(kwargs["timeMax"])
    assert time_max - time_min > timedelta(days=16)  # 3 back + 14 ahead, roughly
    assert time_min < datetime.now(UTC)
