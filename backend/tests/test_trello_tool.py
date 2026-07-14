from unittest.mock import MagicMock

import trello_tool


def test_get_cards_parses_response(monkeypatch):
    fake_response = MagicMock()
    fake_response.json.return_value = [
        {"name": "Write TODO", "due": "2026-07-03T00:00:00Z", "idList": "list1"},
        {"name": "No due date", "due": None, "idList": "list2"},
    ]
    monkeypatch.setattr(trello_tool.requests, "get", MagicMock(return_value=fake_response))
    monkeypatch.setenv("TRELLO_API_KEY", "test_key")
    monkeypatch.setenv("TRELLO_TOKEN", "test_token")
    monkeypatch.setenv("TRELLO_BOARD_ID", "board1")

    cards = trello_tool.get_cards()

    assert cards == [
        {"name": "Write TODO", "due": "2026-07-03T00:00:00Z", "list_id": "list1"},
        {"name": "No due date", "due": None, "list_id": "list2"},
    ]
    fake_response.raise_for_status.assert_called_once()
