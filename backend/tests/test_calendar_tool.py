import os
import re
from unittest.mock import MagicMock, patch

from calendar_tool import JARVIS_TAG, create_event, get_upcoming_events, modify_event

_GOOGLE_ENV = {
    "GOOGLE_CLIENT_ID": "test_id",
    "GOOGLE_CLIENT_SECRET": "test_secret",
    "GOOGLE_REFRESH_TOKEN": "test_refresh_token",
}


def test_get_upcoming_events_merges_all_calendars():
    events_by_calendar = {
        "primary": {
            "items": [
                {
                    "id": "evt1",
                    "summary": "Standup",
                    "description": "🤖 [Jarvis]\n\nDaily sync",
                    "location": "Meeting Room 2",
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
    # location/description are surfaced too (Jarvis metadata line stripped
    # from the description), so Jarvis can answer questions about an event
    # already in view without a separate lookup.
    assert events == [
        {
            "id": "evt1",
            "calendar_id": "primary",
            "calendar": "Personal",
            "summary": "Standup",
            "start": "2026-07-03T09:00:00Z",
            "end": "2026-07-03T09:15:00Z",
            "location": "Meeting Room 2",
            "description": "Daily sync",
            "jarvis": True,
        },
        {
            "id": "evt2",
            "calendar_id": "emma_shared",
            "calendar": "Ben & Emma",
            "summary": "(no title)",
            "start": "2026-07-04",
            "end": "2026-07-05",
            "location": None,
            "description": "",
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


def test_create_event_with_location_stamps_location_added_at():
    mock_service = MagicMock()
    mock_service.events.return_value.insert.return_value.execute.return_value = {}

    with patch.dict(os.environ, _GOOGLE_ENV):
        with patch("calendar_tool.build", return_value=mock_service):
            create_event(
                "Dentist",
                "2026-07-15T09:00:00+01:00",
                "2026-07-15T10:00:00+01:00",
                location="123 High St",
            )

    description = mock_service.events.return_value.insert.call_args.kwargs["body"]["description"]
    assert re.search(r"Location added by JARVIS at: \d{2}/\d{2}/\d{2} \d{2}:\d{2}", description)


def test_create_event_without_location_has_no_location_stamp():
    mock_service = MagicMock()
    mock_service.events.return_value.insert.return_value.execute.return_value = {}

    with patch.dict(os.environ, _GOOGLE_ENV):
        with patch("calendar_tool.build", return_value=mock_service):
            create_event("Focus block", "2026-07-15T09:00:00+01:00", "2026-07-15T10:00:00+01:00")

    description = mock_service.events.return_value.insert.call_args.kwargs["body"]["description"]
    assert "Location added by JARVIS at:" not in description


def test_modify_event_jarvis_owned_stamps_location_when_location_changes():
    mock_service = MagicMock()
    mock_service.events.return_value.get.return_value.execute.return_value = {
        "description": f"{JARVIS_TAG} - created at: 01/01/26 09:00\n\nOriginal notes"
    }
    mock_service.events.return_value.patch.return_value.execute.return_value = {}

    with patch.dict(os.environ, _GOOGLE_ENV):
        with patch("calendar_tool.build", return_value=mock_service):
            modify_event("primary", "evt1", location="123 High St")

    body = mock_service.events.return_value.patch.call_args.kwargs["body"]
    assert "Original notes" in body["description"]
    assert re.search(
        r"Location added by JARVIS at: \d{2}/\d{2}/\d{2} \d{2}:\d{2}", body["description"]
    )


def test_modify_event_foreign_stamps_location_without_flipping_ownership():
    """Foreign events get the location stamp too (Ben approved the change),
    but never the JARVIS_TAG line — that would silently flip ownership."""
    mock_service = MagicMock()
    mock_service.events.return_value.get.return_value.execute.return_value = {
        "description": "Ben's own notes"
    }
    mock_service.events.return_value.patch.return_value.execute.return_value = {}

    with patch.dict(os.environ, _GOOGLE_ENV):
        with patch("calendar_tool.build", return_value=mock_service):
            modify_event("primary", "evt1", location="123 High St")

    body = mock_service.events.return_value.patch.call_args.kwargs["body"]
    assert JARVIS_TAG not in body["description"]
    assert "Ben's own notes" in body["description"]
    assert re.search(
        r"Location added by JARVIS at: \d{2}/\d{2}/\d{2} \d{2}:\d{2}", body["description"]
    )


def test_modify_event_restamping_location_replaces_previous_stamp():
    mock_service = MagicMock()
    mock_service.events.return_value.get.return_value.execute.return_value = {
        "description": "Ben's own notes\n\nLocation added by JARVIS at: 01/01/26 09:00"
    }
    mock_service.events.return_value.patch.return_value.execute.return_value = {}

    with patch.dict(os.environ, _GOOGLE_ENV):
        with patch("calendar_tool.build", return_value=mock_service):
            modify_event("primary", "evt1", location="456 Low St")

    description = mock_service.events.return_value.patch.call_args.kwargs["body"]["description"]
    assert description.count("Location added by JARVIS at:") == 1
    assert "01/01/26 09:00" not in description


def test_modify_event_without_location_does_not_touch_foreign_description():
    mock_service = MagicMock()
    mock_service.events.return_value.get.return_value.execute.return_value = {
        "description": "Ben's own notes"
    }
    mock_service.events.return_value.patch.return_value.execute.return_value = {}

    with patch.dict(os.environ, _GOOGLE_ENV):
        with patch("calendar_tool.build", return_value=mock_service):
            modify_event("primary", "evt1", start="2026-07-15T09:00:00+01:00")

    assert "description" not in mock_service.events.return_value.patch.call_args.kwargs["body"]
