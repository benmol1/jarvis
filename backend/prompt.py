import os
from datetime import datetime
from zoneinfo import ZoneInfo


def build_system_prompt(
    profile: str, state: dict, events: list[dict], cards: list[dict], now: datetime | None = None
) -> str:
    if now is None:
        # Override with JARVIS_TIMEZONE (IANA name) if Ben isn't in the UK.
        now = datetime.now(ZoneInfo(os.environ.get("JARVIS_TIMEZONE", "Europe/London")))
    now_line = now.strftime("%A, %d %B %Y, %H:%M %Z")

    state_lines = "\n".join(f"- {key}: {value}" for key, value in state.items()) or "(none yet)"
    event_lines = (
        "\n".join(
            f"- {e['start']}: {e['summary']}" + (f" [{e['calendar']}]" if e.get("calendar") else "")
            for e in events
        )
        or "(none)"
    )
    card_lines = (
        "\n".join(f"- {c['name']}" + (f" (due {c['due']})" if c.get("due") else "") for c in cards)
        or "(none)"
    )

    return f"""You are Jarvis, Ben's daily-planning assistant.

Current date and time: {now_line}

## About Ben
{profile or "(no profile set)"}

## Rolling state
{state_lines}

## Upcoming calendar events
{event_lines}

## Trello cards
{card_lines}
"""
