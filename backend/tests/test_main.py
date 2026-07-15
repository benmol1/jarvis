import json
import os
from unittest.mock import MagicMock

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def _chat(**kwargs):
    """POST /chat and parse the NDJSON stream into its event dicts."""
    res = client.post("/chat", **kwargs)
    lines = [line for line in res.text.splitlines() if line]
    return res.status_code, [json.loads(line) for line in lines]


def _text_response(text):
    """A model response with no tool calls — one text block, end_turn."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [block]
    return response


def _tool_use_response(name, tool_input):
    """A model response requesting one tool call."""
    block = MagicMock()
    block.type = "tool_use"
    block.id = "toolu_1"
    block.name = name
    block.input = tool_input
    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [block]
    return response


def test_chat_returns_model_reply():
    main.client.messages.create = MagicMock(return_value=_text_response("hello back"))

    status, events = _chat(json={"message": "hi"})

    assert status == 200
    assert events == [{"type": "final", "reply": "hello back", "pending": [], "is_draft": False}]


def test_chat_streams_a_tool_event_before_the_final_reply(monkeypatch):
    """The client needs to see which tool ran while it's running, not just
    the end result — that's the whole point of the streaming response."""
    monkeypatch.setattr(main, "load_state", lambda: {"plan": None})
    monkeypatch.setattr(main, "save_state", lambda state: None)
    main.client.messages.create = MagicMock(
        side_effect=[
            _tool_use_response("save_plan", {"plan": "gym then focus block"}),
            _text_response("done"),
        ]
    )

    status, events = _chat(json={"message": "save today's plan"})

    assert status == 200
    assert events == [
        {"type": "tool", "name": "save_plan"},
        {"type": "final", "reply": "done", "pending": [], "is_draft": False},
    ]


def test_chat_flags_draft_messages_for_the_client(monkeypatch):
    """flag_draft_message is how Jarvis tells the client 'this reply has a
    message for Ben to copy and send' — only then should Copy show up."""
    main.client.messages.create = MagicMock(
        side_effect=[
            _tool_use_response("flag_draft_message", {}),
            _text_response("Hi Alex, can we push our 3pm to 4pm?"),
        ]
    )

    status, events = _chat(json={"message": "draft a message to Alex about rescheduling"})

    assert status == 200
    assert events[-1]["is_draft"] is True


def test_chat_forwards_history_for_session_memory():
    create = MagicMock(return_value=_text_response("you said blue"))
    main.client.messages.create = create

    status, events = _chat(
        json={
            "message": "what did I say?",
            "history": [
                {"role": "user", "content": "my favourite colour is blue"},
                {"role": "assistant", "content": "noted"},
            ],
        },
    )

    assert status == 200
    # Prior turns are replayed, with the new message last.
    assert create.call_args.kwargs["messages"] == [
        {"role": "user", "content": "my favourite colour is blue"},
        {"role": "assistant", "content": "noted"},
        {"role": "user", "content": "what did I say?"},
    ]


def test_chat_survives_a_failing_integration(monkeypatch):
    """An expired calendar token must cost us the calendar, not the chat."""
    main.client.messages.create = MagicMock(return_value=_text_response("still here"))

    def boom():
        raise RuntimeError("Token has been expired or revoked.")

    monkeypatch.setattr(main, "get_upcoming_events", boom)

    status, events = _chat(json={"message": "hi"})

    assert status == 200
    assert events == [{"type": "final", "reply": "still here", "pending": [], "is_draft": False}]


# --- write / approval branches -------------------------------------------------


def test_create_time_box_applies_immediately(monkeypatch):
    created = {}
    monkeypatch.setattr(
        main.calendar_tool,
        "create_event",
        lambda summary, start, end, cal="primary": created.update(summary=summary, cal=cal),
    )
    pending = []

    main.execute_tool(
        "create_time_box",
        {"summary": "Deep work", "start": "S", "end": "E"},
        pending,
        {"draft": False},
    )

    assert created["summary"] == "Deep work"
    assert pending == []


def test_move_jarvis_event_applies_immediately(monkeypatch):
    monkeypatch.setattr(
        main.calendar_tool, "get_event", lambda c, i: {"summary": "Focus", "jarvis": True}
    )
    moved = []
    monkeypatch.setattr(main.calendar_tool, "update_event", lambda *a: moved.append(a))
    pending = []

    main.execute_tool(
        "move_event",
        {"event_id": "x", "calendar_id": "primary", "start": "S", "end": "E"},
        pending,
        {"draft": False},
    )

    assert len(moved) == 1
    assert pending == []


def test_move_foreign_event_is_queued_not_applied(monkeypatch):
    monkeypatch.setattr(
        main.calendar_tool, "get_event", lambda c, i: {"summary": "Dentist", "jarvis": False}
    )
    moved = []
    monkeypatch.setattr(main.calendar_tool, "update_event", lambda *a: moved.append(a))
    pending = []

    main.execute_tool(
        "move_event",
        {"event_id": "x", "calendar_id": "primary", "start": "S", "end": "E"},
        pending,
        {"draft": False},
    )

    assert moved == []  # foreign event must NOT be touched without approval
    assert len(pending) == 1
    assert pending[0]["action"] == "move_event"
    assert pending[0]["event_id"] == "x"


def test_create_time_box_targets_named_calendar(monkeypatch):
    calls = []
    monkeypatch.setattr(
        main.calendar_tool, "create_event", lambda summary, start, end, cal: calls.append(cal)
    )

    main.execute_tool(
        "create_time_box",
        {"summary": "Date night", "start": "S", "end": "E", "calendar_id": "joint@group"},
        [],
        {"draft": False},
    )

    assert calls == ["joint@group"]  # not silently dropped to primary


def test_move_to_calendar_jarvis_event_applies_immediately(monkeypatch):
    monkeypatch.setattr(
        main.calendar_tool, "get_event", lambda c, i: {"summary": "Focus", "jarvis": True}
    )
    moved = []
    monkeypatch.setattr(main.calendar_tool, "move_event_to_calendar", lambda *a: moved.append(a))
    pending = []

    main.execute_tool(
        "move_to_calendar",
        {"event_id": "x", "calendar_id": "primary", "destination_calendar_id": "joint@group"},
        pending,
        {"draft": False},
    )

    assert moved == [("primary", "x", "joint@group")]
    assert pending == []


def test_move_to_calendar_foreign_event_is_queued(monkeypatch):
    monkeypatch.setattr(
        main.calendar_tool, "get_event", lambda c, i: {"summary": "Dentist", "jarvis": False}
    )
    moved = []
    monkeypatch.setattr(main.calendar_tool, "move_event_to_calendar", lambda *a: moved.append(a))
    pending = []

    main.execute_tool(
        "move_to_calendar",
        {"event_id": "x", "calendar_id": "primary", "destination_calendar_id": "joint@group"},
        pending,
        {"draft": False},
    )

    assert moved == []  # foreign event must NOT be moved without approval
    assert pending[0]["action"] == "move_to_calendar"
    assert pending[0]["destination_calendar_id"] == "joint@group"


def test_copy_event_applies_immediately_even_for_foreign(monkeypatch):
    """Copy is non-destructive, so it never needs approval — it leaves the
    original alone. get_event is not even consulted."""
    copied = []
    monkeypatch.setattr(
        main.calendar_tool,
        "copy_event",
        lambda c, i, dest: copied.append((c, i, dest)) or {"summary": "Dentist"},
    )
    pending = []

    main.execute_tool(
        "copy_event",
        {"event_id": "x", "calendar_id": "primary", "destination_calendar_id": "joint@group"},
        pending,
        {"draft": False},
    )

    assert copied == [("primary", "x", "joint@group")]
    assert pending == []
