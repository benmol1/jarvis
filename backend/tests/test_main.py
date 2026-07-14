import os
from unittest.mock import MagicMock

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_chat_returns_model_reply():
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="hello back")]
    main.client.messages.create = MagicMock(return_value=fake_response)

    res = client.post("/chat", json={"message": "hi"})

    assert res.status_code == 200
    assert res.json() == {"reply": "hello back"}


def test_chat_forwards_history_for_session_memory():
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="you said blue")]
    create = MagicMock(return_value=fake_response)
    main.client.messages.create = create

    res = client.post(
        "/chat",
        json={
            "message": "what did I say?",
            "history": [
                {"role": "user", "content": "my favourite colour is blue"},
                {"role": "assistant", "content": "noted"},
            ],
        },
    )

    assert res.status_code == 200
    # Prior turns are replayed, with the new message last.
    assert create.call_args.kwargs["messages"] == [
        {"role": "user", "content": "my favourite colour is blue"},
        {"role": "assistant", "content": "noted"},
        {"role": "user", "content": "what did I say?"},
    ]


def test_chat_survives_a_failing_integration(monkeypatch):
    """An expired calendar token must cost us the calendar, not the chat."""
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="still here")]
    main.client.messages.create = MagicMock(return_value=fake_response)

    def boom():
        raise RuntimeError("Token has been expired or revoked.")

    monkeypatch.setattr(main, "get_upcoming_events", boom)

    res = client.post("/chat", json={"message": "hi"})

    assert res.status_code == 200
    assert res.json() == {"reply": "still here"}
