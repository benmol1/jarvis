"""Gmail read/reply for the inbound email address Ben forwards things to.

Same OAuth credentials as calendar_tool — one Google client, one refresh token,
widened scopes. Nothing here is exposed as a Claude tool: the poller drives it.
"""

import base64
import os
import re
from email.message import EmailMessage
from email.utils import parseaddr

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Max characters of email body handed to Claude. A forwarded booking confirmation
# is a few hundred; the rest is signatures, legal boilerplate and quoted threads.
_MAX_BODY = 8000

_TAG_RE = re.compile(r"<[^>]+>")


def get_gmail_service():
    """Build and return an authenticated Gmail service."""
    creds = Credentials(
        None,  # No initial access token - we'll refresh
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        # gmail.modify covers reading messages and clearing the UNREAD label;
        # sending needs gmail.send on top. Re-mint the refresh token with
        # scripts/reauth_google.py after widening this, or the calls 403.
        scopes=[
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.send",
        ],
    )
    return build("gmail", "v1", credentials=creds)


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")


def _extract_body(payload: dict) -> str:
    """Pull the best text out of a MIME tree: text/plain if there is one,
    otherwise text/html with the tags stripped."""
    plain, html = "", ""

    def walk(part: dict) -> None:
        nonlocal plain, html
        data = part.get("body", {}).get("data")
        mime = part.get("mimeType", "")
        if data and mime == "text/plain" and not plain:
            plain = _decode(data)
        elif data and mime == "text/html" and not html:
            html = _decode(data)
        for sub in part.get("parts", []):
            walk(sub)

    walk(payload)
    # ponytail: regex de-tagging, not a real HTML parser. Fine for reading dates
    # and addresses off a confirmation; reach for a parser if that stops holding.
    text = plain or _TAG_RE.sub(" ", html)
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:_MAX_BODY]


def _headers(payload: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in payload.get("headers", [])}


def fetch_new(service, address: str) -> list[dict]:
    """Unread messages sent to the Jarvis address, oldest first.

    -in:spam matters: Gmail's own filtering is the real defence behind the
    sender whitelist, which trusts a spoofable From header.
    """
    query = f"is:unread to:{address} -in:spam"
    listing = service.users().messages().list(userId="me", q=query, maxResults=10).execute()
    messages = []
    for stub in reversed(listing.get("messages", [])):
        raw = service.users().messages().get(userId="me", id=stub["id"], format="full").execute()
        payload = raw.get("payload", {})
        head = _headers(payload)
        messages.append(
            {
                "id": raw["id"],
                "thread_id": raw.get("threadId"),
                "sender": parseaddr(head.get("from", ""))[1].lower(),
                "subject": head.get("subject", "(no subject)"),
                "message_id": head.get("message-id", ""),
                "references": head.get("references", ""),
                "body": _extract_body(payload),
            }
        )
    return messages


def mark_read(service, message_id: str) -> None:
    service.users().messages().modify(
        userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
    ).execute()


def build_reply(message: dict, text: str, sender: str) -> EmailMessage:
    """A plain-text reply threaded onto the original."""
    reply = EmailMessage()
    reply["To"] = message["sender"]
    reply["From"] = sender
    subject = message["subject"]
    reply["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if message.get("message_id"):
        reply["In-Reply-To"] = message["message_id"]
        # References carries the whole chain, so append rather than replace.
        reply["References"] = f"{message.get('references', '')} {message['message_id']}".strip()
    reply.set_content(text)
    return reply


def send_reply(service, message: dict, text: str, sender: str) -> None:
    reply = build_reply(message, text, sender)
    service.users().messages().send(
        userId="me",
        body={
            "raw": base64.urlsafe_b64encode(reply.as_bytes()).decode(),
            "threadId": message.get("thread_id"),
        },
    ).execute()
