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
