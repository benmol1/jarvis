import json
import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch):
    """Keep rolling state in memory so /chat's end-of-turn save_state never
    touches the repo's state.json. Individual tests may still override these."""
    store = {}
    monkeypatch.setattr(main, "load_state", lambda: json.loads(json.dumps(store)))

    def _save(state):
        store.clear()
        store.update(state)

    monkeypatch.setattr(main, "save_state", _save)
    return store


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


def _state():
    """A fresh rolling-state dict for execute_tool, with an empty approval queue."""
    return {"pending_approvals": []}


def test_create_event_applies_immediately(monkeypatch):
    created = {}
    monkeypatch.setattr(
        main.calendar_tool,
        "create_event",
        lambda summary, start, end, cal="primary", **kw: created.update(summary=summary, cal=cal),
    )
    state = _state()

    main.execute_tool(
        "create_event",
        {"summary": "Deep work", "start": "S", "end": "E"},
        state,
        {"draft": False},
    )

    assert created["summary"] == "Deep work"
    assert state["pending_approvals"] == []


def test_create_event_with_attendees_is_queued(monkeypatch):
    """Inviting other people is outward-facing, so it waits for Ben's approval
    rather than emailing invites straight away."""
    created = []
    monkeypatch.setattr(
        main.calendar_tool, "create_event", lambda *a, **kw: created.append((a, kw))
    )
    state = _state()

    main.execute_tool(
        "create_event",
        {"summary": "Lunch", "start": "S", "end": "E", "attendees": ["a@b.com"]},
        state,
        {"draft": False},
    )

    assert created == []  # not created until approved
    item = state["pending_approvals"][0]
    assert item["action"] == "create_event"
    assert item["attendees"] == ["a@b.com"]
    assert item["id"]


def test_create_event_warns_on_conflict_far_out(monkeypatch):
    """Beyond the 14-day context window Jarvis can't see clashes, so create_event
    checks and warns (but still creates)."""
    monkeypatch.setattr(main.calendar_tool, "create_event", lambda *a, **kw: None)
    monkeypatch.setattr(
        main.calendar_tool,
        "find_conflicts",
        lambda start, end: [{"summary": "Standup", "start": "2027-01-02T09:00:00+00:00"}],
    )
    state = _state()

    result = main.execute_tool(
        "create_event",
        {"summary": "Deep work", "start": "2027-01-02T09:00:00+00:00", "end": "2027-01-02T10:00"},
        state,
        {"draft": False},
    )

    assert "Warning" in result and "Standup" in result


def test_modify_jarvis_event_applies_immediately(monkeypatch):
    monkeypatch.setattr(
        main.calendar_tool, "get_event", lambda c, i: {"summary": "Focus", "jarvis": True}
    )
    modified = []
    monkeypatch.setattr(main.calendar_tool, "modify_event", lambda *a, **kw: modified.append(kw))
    state = _state()

    main.execute_tool(
        "modify_event",
        {"event_id": "x", "calendar_id": "primary", "start": "S", "end": "E"},
        state,
        {"draft": False},
    )

    assert modified == [{"start": "S", "end": "E"}]
    assert state["pending_approvals"] == []


def test_modify_foreign_event_is_queued_not_applied(monkeypatch):
    monkeypatch.setattr(
        main.calendar_tool, "get_event", lambda c, i: {"summary": "Dentist", "jarvis": False}
    )
    modified = []
    monkeypatch.setattr(main.calendar_tool, "modify_event", lambda *a, **kw: modified.append(kw))
    state = _state()

    main.execute_tool(
        "modify_event",
        {"event_id": "x", "calendar_id": "primary", "title": "New title"},
        state,
        {"draft": False},
    )

    assert modified == []  # foreign event must NOT be touched without approval
    item = state["pending_approvals"][0]
    assert item["action"] == "modify_event"
    assert item["event_id"] == "x"
    assert item["title"] == "New title"


def test_modify_jarvis_event_with_attendees_is_queued(monkeypatch):
    """Even on a Jarvis-owned event, adding attendees emails invites, so it
    still needs Ben's approval."""
    monkeypatch.setattr(
        main.calendar_tool, "get_event", lambda c, i: {"summary": "Focus", "jarvis": True}
    )
    modified = []
    monkeypatch.setattr(main.calendar_tool, "modify_event", lambda *a, **kw: modified.append(kw))
    state = _state()

    main.execute_tool(
        "modify_event",
        {"event_id": "x", "calendar_id": "primary", "attendees": ["a@b.com"]},
        state,
        {"draft": False},
    )

    assert modified == []
    assert state["pending_approvals"][0]["attendees"] == ["a@b.com"]


def test_create_event_targets_named_calendar(monkeypatch):
    calls = []
    monkeypatch.setattr(
        main.calendar_tool, "create_event", lambda summary, start, end, cal, **kw: calls.append(cal)
    )

    main.execute_tool(
        "create_event",
        {"summary": "Date night", "start": "S", "end": "E", "calendar_id": "joint@group"},
        _state(),
        {"draft": False},
    )

    assert calls == ["joint@group"]  # not silently dropped to primary


def test_move_to_calendar_jarvis_event_applies_immediately(monkeypatch):
    monkeypatch.setattr(
        main.calendar_tool, "get_event", lambda c, i: {"summary": "Focus", "jarvis": True}
    )
    moved = []
    monkeypatch.setattr(main.calendar_tool, "move_event_to_calendar", lambda *a: moved.append(a))
    state = _state()

    main.execute_tool(
        "move_to_calendar",
        {"event_id": "x", "calendar_id": "primary", "destination_calendar_id": "joint@group"},
        state,
        {"draft": False},
    )

    assert moved == [("primary", "x", "joint@group")]
    assert state["pending_approvals"] == []


def test_move_to_calendar_foreign_event_is_queued(monkeypatch):
    monkeypatch.setattr(
        main.calendar_tool, "get_event", lambda c, i: {"summary": "Dentist", "jarvis": False}
    )
    moved = []
    monkeypatch.setattr(main.calendar_tool, "move_event_to_calendar", lambda *a: moved.append(a))
    state = _state()

    main.execute_tool(
        "move_to_calendar",
        {"event_id": "x", "calendar_id": "primary", "destination_calendar_id": "joint@group"},
        state,
        {"draft": False},
    )

    assert moved == []  # foreign event must NOT be moved without approval
    item = state["pending_approvals"][0]
    assert item["action"] == "move_to_calendar"
    assert item["destination_calendar_id"] == "joint@group"


def test_copy_event_applies_immediately_even_for_foreign(monkeypatch):
    """Copy is non-destructive, so it never needs approval — it leaves the
    original alone. get_event is not even consulted."""
    copied = []
    monkeypatch.setattr(
        main.calendar_tool,
        "copy_event",
        lambda c, i, dest: copied.append((c, i, dest)) or {"summary": "Dentist"},
    )
    state = _state()

    main.execute_tool(
        "copy_event",
        {"event_id": "x", "calendar_id": "primary", "destination_calendar_id": "joint@group"},
        state,
        {"draft": False},
    )

    assert copied == [("primary", "x", "joint@group")]
    assert state["pending_approvals"] == []


def test_respond_to_event_applies_immediately(monkeypatch):
    calls = []
    monkeypatch.setattr(
        main.calendar_tool, "respond_to_event", lambda c, i, r: calls.append((c, i, r))
    )

    main.execute_tool(
        "respond_to_event",
        {"event_id": "x", "calendar_id": "primary", "response": "accepted"},
        _state(),
        {"draft": False},
    )

    assert calls == [("primary", "x", "accepted")]


def test_find_place_returns_location_and_maps_link(monkeypatch):
    monkeypatch.setattr(
        main.maps_tool,
        "find_place",
        lambda q: {
            "name": "Nando's",
            "address": "2 High St, Guildford",
            "location": "Nando's, 2 High St, Guildford",
            "place_id": "pid",
            "maps_url": "https://maps.example/pid",
        },
    )

    result = main.execute_tool(
        "find_place", {"query": "nandos guildford"}, _state(), {"draft": False}
    )

    assert "Nando's, 2 High St, Guildford" in result
    assert "https://maps.example/pid" in result


def test_find_place_reports_no_match(monkeypatch):
    monkeypatch.setattr(main.maps_tool, "find_place", lambda q: {})

    result = main.execute_tool("find_place", {"query": "zzz"}, _state(), {"draft": False})

    assert "No place found" in result


def test_travel_time_prefers_traffic_duration(monkeypatch):
    monkeypatch.setattr(
        main.maps_tool,
        "travel_time",
        lambda o, d, mode="driving", depart_at=None: {
            "origin": "Home",
            "destination": "Office",
            "mode": "driving",
            "distance": "45 km",
            "duration": "50 mins",
            "duration_in_traffic": "1 hour 10 mins",
        },
    )

    result = main.execute_tool(
        "travel_time", {"origin": "Home", "destination": "Office"}, _state(), {"draft": False}
    )

    assert "1 hour 10 mins" in result and "in current traffic" in result
    assert "45 km" in result


def test_travel_time_reports_no_route(monkeypatch):
    monkeypatch.setattr(
        main.maps_tool, "travel_time", lambda o, d, mode="driving", depart_at=None: {}
    )

    result = main.execute_tool(
        "travel_time",
        {"origin": "A", "destination": "B", "mode": "transit"},
        _state(),
        {"draft": False},
    )

    assert "No transit route" in result


def _route(**over):
    """A plan_route result stub."""
    base = {
        "origin": "Home, Guildford",
        "destination": "Office, London",
        "mode": "driving",
        "distance": "45 km",
        "duration": "50 mins",
        "duration_in_traffic": "1 hour 10 mins",
        "duration_seconds": 4200,
        "directions_url": "https://maps.example/dir",
    }
    base.update(over)
    return base


def test_add_route_to_jarvis_event_applies_and_writes_directions(monkeypatch):
    monkeypatch.setattr(
        main.calendar_tool,
        "get_event",
        lambda c, i: {
            "summary": "Client meeting",
            "start": "2026-07-20T09:00:00+01:00",
            "description": "Bring the deck.",
            "jarvis": True,
        },
    )
    monkeypatch.setattr(
        main.maps_tool, "plan_route", lambda o, d, mode="driving", depart_at=None: _route()
    )
    modified = []
    monkeypatch.setattr(main.calendar_tool, "modify_event", lambda *a, **kw: modified.append(kw))

    result = main.execute_tool(
        "add_route_to_event",
        {
            "event_id": "x",
            "calendar_id": "primary",
            "origin": "home",
            "destination": "office",
            "mode": "driving",
        },
        _state(),
        {"draft": False},
    )

    kw = modified[0]
    assert kw["location"] == "Office, London"
    # Existing note preserved, route block appended with link and leave-by time.
    assert kw["description"].startswith("Bring the deck.")
    assert "https://maps.example/dir" in kw["description"]
    assert "Leave by 07:50" in kw["description"]  # 09:00 minus 70 mins
    assert "Added the driving route" in result


def test_add_route_replaces_stale_route_block(monkeypatch):
    """Re-planning must swap the route block, not stack a second one."""
    monkeypatch.setattr(
        main.calendar_tool,
        "get_event",
        lambda c, i: {
            "summary": "Client meeting",
            "start": "2026-07-20T09:00:00+01:00",
            "description": "Bring the deck.\n\n🗺️ Route to Old place: 20 mins.\nDirections: old",
            "jarvis": True,
        },
    )
    monkeypatch.setattr(
        main.maps_tool, "plan_route", lambda o, d, mode="driving", depart_at=None: _route()
    )
    modified = []
    monkeypatch.setattr(main.calendar_tool, "modify_event", lambda *a, **kw: modified.append(kw))

    main.execute_tool(
        "add_route_to_event",
        {"event_id": "x", "calendar_id": "primary", "origin": "home", "destination": "office"},
        _state(),
        {"draft": False},
    )

    desc = modified[0]["description"]
    assert desc.count("🗺️ Route") == 1  # only the new block
    assert "Old place" not in desc
    assert desc.startswith("Bring the deck.")


def test_add_route_to_foreign_event_is_queued(monkeypatch):
    monkeypatch.setattr(
        main.calendar_tool,
        "get_event",
        lambda c, i: {
            "summary": "Dentist",
            "start": "2026-07-20T09:00:00+01:00",
            "description": "",
            "jarvis": False,
        },
    )
    monkeypatch.setattr(
        main.maps_tool, "plan_route", lambda o, d, mode="driving", depart_at=None: _route()
    )
    modified = []
    monkeypatch.setattr(main.calendar_tool, "modify_event", lambda *a, **kw: modified.append(kw))
    state = _state()

    main.execute_tool(
        "add_route_to_event",
        {"event_id": "x", "calendar_id": "primary", "origin": "home", "destination": "office"},
        state,
        {"draft": False},
    )

    assert modified == []  # foreign event untouched until approved
    item = state["pending_approvals"][0]
    assert item["action"] == "modify_event"  # applied via the standard modify path
    assert item["location"] == "Office, London"
    assert "https://maps.example/dir" in item["description"]


def test_add_route_reports_no_route(monkeypatch):
    monkeypatch.setattr(
        main.calendar_tool,
        "get_event",
        lambda c, i: {"summary": "X", "start": "2026-07-20T09:00:00+01:00", "jarvis": True},
    )
    monkeypatch.setattr(
        main.maps_tool, "plan_route", lambda o, d, mode="driving", depart_at=None: {}
    )

    result = main.execute_tool(
        "add_route_to_event",
        {
            "event_id": "x",
            "calendar_id": "primary",
            "origin": "A",
            "destination": "B",
            "mode": "transit",
        },
        _state(),
        {"draft": False},
    )

    assert "No transit route" in result


def test_add_route_saves_the_chosen_mode(monkeypatch):
    """Route planning takes one mode as a parameter — transit here writes a
    single transit block, not a driving+transit comparison."""
    monkeypatch.setattr(
        main.calendar_tool,
        "get_event",
        lambda c, i: {
            "summary": "Client meeting",
            "start": "2026-07-20T09:00:00+01:00",
            "description": "",
            "jarvis": True,
        },
    )
    captured = {}

    def fake_plan(o, d, mode="driving", depart_at=None):
        captured["mode"] = mode
        return _route(
            mode="transit",
            duration="1 hour 30 mins",
            duration_in_traffic=None,
            duration_seconds=5400,
            directions_url="https://maps.example/train",
        )

    monkeypatch.setattr(main.maps_tool, "plan_route", fake_plan)
    modified = []
    monkeypatch.setattr(main.calendar_tool, "modify_event", lambda *a, **kw: modified.append(kw))

    result = main.execute_tool(
        "add_route_to_event",
        {
            "event_id": "x",
            "calendar_id": "primary",
            "origin": "home",
            "destination": "office",
            "mode": "transit",
        },
        _state(),
        {"draft": False},
    )

    assert captured["mode"] == "transit"  # the parameter is honoured
    desc = modified[0]["description"]
    assert desc.count("🗺️ Route") == 1  # a single block for the chosen mode
    assert "https://maps.example/train" in desc
    assert "by transit" in desc
    assert "Added the transit route" in result


def test_cancel_approval_removes_queued_item():
    state = {"pending_approvals": [{"id": "abc", "label": "Delete 'Dentist'"}]}

    result = main.execute_tool("cancel_approval", {"approval_id": "abc"}, state, {"draft": False})

    assert "Cancelled" in result
    assert state["pending_approvals"] == []


def test_cancel_approval_unknown_id_is_a_noop():
    state = {"pending_approvals": [{"id": "abc", "label": "Delete 'Dentist'"}]}

    result = main.execute_tool("cancel_approval", {"approval_id": "nope"}, state, {"draft": False})

    assert "No pending approval" in result
    assert len(state["pending_approvals"]) == 1


# --- cross-turn approval persistence (through the HTTP layer) -------------------


def test_queued_approval_persists_across_turns_and_apply_clears_it(monkeypatch, _isolate_state):
    """A foreign-event edit queues to persisted state, is returned again on a
    later turn (so a fresh client re-renders it), and /apply drops it by id."""
    monkeypatch.setattr(
        main.calendar_tool, "get_event", lambda c, i: {"summary": "Dentist", "jarvis": False}
    )
    main.client.messages.create = MagicMock(
        side_effect=[
            _tool_use_response("delete_event", {"event_id": "x", "calendar_id": "primary"}),
            _text_response("queued for your approval"),
        ]
    )

    _, events = _chat(json={"message": "cancel my dentist appointment"})
    pending = events[-1]["pending"]
    assert len(pending) == 1 and pending[0]["action"] == "delete_event"
    approval_id = pending[0]["id"]
    assert _isolate_state["pending_approvals"][0]["id"] == approval_id  # persisted

    # A later turn that touches nothing still surfaces the outstanding approval.
    main.client.messages.create = MagicMock(return_value=_text_response("anything else?"))
    _, events = _chat(json={"message": "thanks"})
    assert [p["id"] for p in events[-1]["pending"]] == [approval_id]

    # Approving it applies the delete and clears it from the queue.
    deleted = []
    monkeypatch.setattr(main.calendar_tool, "delete_event", lambda c, i: deleted.append((c, i)))
    res = client.post("/apply", json=pending[0])
    assert res.status_code == 200
    assert deleted == [("primary", "x")]
    assert _isolate_state["pending_approvals"] == []
