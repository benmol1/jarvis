from unittest.mock import MagicMock

import trello_tool


def _mock_auth(monkeypatch):
    monkeypatch.setenv("TRELLO_API_KEY", "test_key")
    monkeypatch.setenv("TRELLO_TOKEN", "test_token")
    monkeypatch.setenv("TRELLO_BOARD_ID", "board1")


FAKE_LISTS = [
    {"id": "list1", "name": "To Do"},
    {"id": "list2", "name": "Doing"},
    {"id": "list3", "name": "Done"},
]

FAKE_CARDS = [
    {
        "id": "c1",
        "name": "Write TODO",
        "due": "2026-07-03T00:00:00Z",
        "idList": "list1",
        "desc": "Some notes",
        "labels": [{"name": "urgent"}],
        "closed": False,
    },
    {
        "id": "c2",
        "name": "Finished task",
        "due": None,
        "idList": "list3",
        "desc": "",
        "labels": [],
        "closed": False,
    },
    {
        "id": "c3",
        "name": "In progress",
        "due": None,
        "idList": "list2",
        "desc": "",
        "labels": [],
        "closed": False,
    },
    {
        "id": "c4",
        "name": "Archived card",
        "due": None,
        "idList": "list1",
        "desc": "",
        "labels": [],
        "closed": True,
    },
]


def _mock_get(monkeypatch, lists=FAKE_LISTS, cards=FAKE_CARDS):
    """Mock requests.get to return lists for the first call and cards for the second."""
    list_resp = MagicMock()
    list_resp.json.return_value = lists

    card_resp = MagicMock()
    card_resp.json.return_value = cards

    mock = MagicMock(side_effect=[list_resp, card_resp])
    monkeypatch.setattr(trello_tool.requests, "get", mock)
    return mock


def test_get_cards_excludes_done_by_default(monkeypatch):
    _mock_auth(monkeypatch)
    _mock_get(monkeypatch)

    cards = trello_tool.get_cards()

    names = [c["name"] for c in cards]
    assert "Write TODO" in names
    assert "In progress" in names
    assert "Finished task" not in names
    assert "Archived card" not in names


def test_get_cards_includes_done_when_requested(monkeypatch):
    _mock_auth(monkeypatch)
    _mock_get(monkeypatch)

    cards = trello_tool.get_cards(exclude_done=False)

    names = [c["name"] for c in cards]
    assert "Finished task" in names
    assert "Archived card" not in names


def test_get_cards_returns_resolved_fields(monkeypatch):
    _mock_auth(monkeypatch)
    _mock_get(monkeypatch)

    cards = trello_tool.get_cards()

    todo_card = next(c for c in cards if c["name"] == "Write TODO")
    assert todo_card["list"] == "To Do"
    assert todo_card["due"] == "2026-07-03T00:00:00Z"
    assert todo_card["description"] == "Some notes"
    assert todo_card["labels"] == ["urgent"]
    assert "id" in todo_card


def test_get_lists(monkeypatch):
    _mock_auth(monkeypatch)
    resp = MagicMock()
    resp.json.return_value = FAKE_LISTS
    monkeypatch.setattr(trello_tool.requests, "get", MagicMock(return_value=resp))

    lists = trello_tool.get_lists()

    assert len(lists) == 3
    assert lists[0] == {"id": "list1", "name": "To Do"}


def test_create_card(monkeypatch):
    _mock_auth(monkeypatch)

    list_resp = MagicMock()
    list_resp.json.return_value = FAKE_LISTS

    card_resp = MagicMock()
    card_resp.json.return_value = {
        "id": "new1",
        "name": "New task",
        "due": None,
        "desc": "",
        "idList": "list1",
    }

    monkeypatch.setattr(trello_tool.requests, "get", MagicMock(return_value=list_resp))
    monkeypatch.setattr(trello_tool.requests, "post", MagicMock(return_value=card_resp))

    card = trello_tool.create_card("New task", "To Do")

    assert card["id"] == "new1"
    assert card["name"] == "New task"
    assert card["list"] == "To Do"


def test_update_card(monkeypatch):
    _mock_auth(monkeypatch)

    list_resp = MagicMock()
    list_resp.json.return_value = FAKE_LISTS

    card_resp = MagicMock()
    card_resp.json.return_value = {
        "id": "c1",
        "name": "Renamed",
        "due": None,
        "desc": "",
        "idList": "list2",
    }

    monkeypatch.setattr(trello_tool.requests, "get", MagicMock(return_value=list_resp))
    monkeypatch.setattr(trello_tool.requests, "put", MagicMock(return_value=card_resp))

    card = trello_tool.update_card("c1", name="Renamed", list_name="Doing")

    assert card["name"] == "Renamed"
    assert card["list"] == "Doing"


def test_archive_card(monkeypatch):
    _mock_auth(monkeypatch)

    card_resp = MagicMock()
    card_resp.json.return_value = {"id": "c1", "name": "Write TODO"}

    monkeypatch.setattr(trello_tool.requests, "put", MagicMock(return_value=card_resp))

    result = trello_tool.archive_card("c1")

    assert result["archived"] is True
    assert result["name"] == "Write TODO"
