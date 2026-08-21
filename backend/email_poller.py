"""Polls the Jarvis inbox and answers forwarded email through the normal chat loop.

Ben forwards a booking confirmation with an instruction ("put this in the
calendar"); Jarvis reads it, calls the same tools it would in the app, and
replies in one line. Approval rules are unchanged — anything that would queue in
chat still queues, and the reply says so.

The Pi has nothing port-forwarded, so this polls rather than taking a webhook.
"""

import asyncio
import json
import logging
import os
from email.utils import parseaddr

import gmail_tool

logger = logging.getLogger(__name__)

POLL_SECONDS = 60


def allowed_senders() -> set[str]:
    raw = os.environ.get("JARVIS_EMAIL_ALLOWED", "")
    return {parseaddr(a)[1].lower() for a in raw.split(",") if a.strip()}


def _prompt(message: dict) -> str:
    return (
        "The following email was forwarded to you by Ben. Act on any instruction "
        "in it, then reply with a single line: the action you took, or the one "
        "question you need answered to take it.\n\n"
        f"From: {message['sender']}\n"
        f"Subject: {message['subject']}\n\n"
        f"{message['body']}"
    )


def handle(message: dict, run_chat, chat_request) -> str | None:
    """Run one email through the chat loop. Returns the reply text, or None if
    the sender isn't whitelisted."""
    if message["sender"] not in allowed_senders():
        logger.warning("ignoring email from non-whitelisted sender %s", message["sender"])
        # No bounce, no error reply: answering an unknown (possibly spoofed)
        # sender just tells them the address is live.
        return None

    reply = ""
    for line in run_chat(chat_request(message=_prompt(message)), connection="email"):
        event = json.loads(line)
        if event.get("type") == "final":
            reply = event.get("reply", "")
    return reply or "No reply generated."


def poll_once(run_chat, chat_request) -> None:
    address = os.environ["JARVIS_EMAIL_ADDRESS"]
    service = gmail_tool.get_gmail_service()
    for message in gmail_tool.fetch_new(service, address):
        # Mark read BEFORE handling: a message that crashes the loop must not be
        # picked up again on every tick forever.
        gmail_tool.mark_read(service, message["id"])
        try:
            reply = handle(message, run_chat, chat_request)
            if reply:
                gmail_tool.send_reply(service, message, reply, address)
                logger.info("replied to %s: %s", message["sender"], reply[:80])
        except Exception:
            logger.exception("failed handling email %s from %s", message["id"], message["sender"])


async def poll_loop(run_chat, chat_request) -> None:
    """Tick forever. Gmail being down costs us a tick, not the task."""
    while True:
        try:
            # run_chat and the Google client are both blocking.
            await asyncio.to_thread(poll_once, run_chat, chat_request)
        except Exception:
            logger.warning("email poll failed; retrying next tick", exc_info=True)
        await asyncio.sleep(POLL_SECONDS)


def start(run_chat, chat_request) -> None:
    """Start polling, unless the address or whitelist is unset (feature off)."""
    if not os.environ.get("JARVIS_EMAIL_ADDRESS") or not allowed_senders():
        logger.info("inbound email disabled (JARVIS_EMAIL_ADDRESS/ALLOWED unset)")
        return
    asyncio.create_task(poll_loop(run_chat, chat_request))
    logger.info("inbound email polling every %ss", POLL_SECONDS)
