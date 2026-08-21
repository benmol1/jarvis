import base64
import json
from unittest.mock import patch

import email_poller
import gmail_tool


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _message(sender: str = "ben.molyneaux1@gmail.com") -> dict:
    return {
        "id": "m1",
        "thread_id": "t1",
        "sender": sender,
        "subject": "Fwd: Booking confirmed",
        "message_id": "<orig@mail.example>",
        "references": "<older@mail.example>",
        "body": "Table for 4 at 19:30 on Friday. Put this in the calendar.",
    }


def _fake_chat(reply: str):
    """Stand-in for run_chat: yields the same NDJSON lines the real one does."""

    def run_chat(req, connection="unknown"):
        yield json.dumps({"type": "tool", "name": "create_event"}) + "\n"
        yield json.dumps({"type": "final", "reply": reply, "pending": [], "is_draft": False}) + "\n"

    return run_chat


class _Req:
    def __init__(self, message: str):
        self.message = message


def test_whitelisted_sender_gets_the_reply():
    with patch.dict(
        "os.environ", {"JARVIS_EMAIL_ALLOWED": "Ben <ben.molyneaux1@gmail.com>, emma@example.com"}
    ):
        reply = email_poller.handle(_message(), _fake_chat("Booked, sir."), _Req)
    assert reply == "Booked, sir."


def test_unknown_sender_is_ignored_with_no_reply():
    with patch.dict("os.environ", {"JARVIS_EMAIL_ALLOWED": "ben.molyneaux1@gmail.com"}):
        reply = email_poller.handle(_message("spammer@evil.example"), _fake_chat("oops"), _Req)
    assert reply is None


def test_reply_threads_onto_the_original():
    reply = gmail_tool.build_reply(_message(), "Booked, sir.", "ben+jarvis@gmail.com")
    assert reply["To"] == "ben.molyneaux1@gmail.com"
    assert reply["Subject"] == "Re: Fwd: Booking confirmed"
    assert reply["In-Reply-To"] == "<orig@mail.example>"
    assert reply["References"] == "<older@mail.example> <orig@mail.example>"
    assert "Booked, sir." in reply.get_content()


def test_body_prefers_plain_text_and_falls_back_to_stripped_html():
    multipart = {
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>Hi <b>there</b></p>")}},
            {"mimeType": "text/plain", "body": {"data": _b64("Hi there")}},
        ]
    }
    assert gmail_tool._extract_body(multipart) == "Hi there"

    html_only = {"mimeType": "text/html", "body": {"data": _b64("<p>Table at <b>19:30</b></p>")}}
    assert "19:30" in gmail_tool._extract_body(html_only)
    assert "<" not in gmail_tool._extract_body(html_only)
