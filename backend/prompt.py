def build_system_prompt(profile: str, state: dict, events: list[dict], cards: list[dict]) -> str:
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

## About Ben
{profile or "(no profile set)"}

## Rolling state
{state_lines}

## Upcoming calendar events
{event_lines}

## Trello cards
{card_lines}
"""
