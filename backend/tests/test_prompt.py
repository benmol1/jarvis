from datetime import datetime
from zoneinfo import ZoneInfo

from prompt import build_system_prompt


def test_build_system_prompt_includes_current_datetime():
    now = datetime(2026, 7, 14, 8, 30, tzinfo=ZoneInfo("Europe/London"))
    result = build_system_prompt(profile="", state={}, events=[], now=now)

    assert "Current date and time: Tuesday, 14 July 2026, 08:30 BST" in result


def test_build_system_prompt_includes_all_sections():
    result = build_system_prompt(
        profile="Sacred family time: 5-7pm",
        state={"yesterday_plan": "wrote tests"},
        events=[{"start": "2026-07-03T09:00:00Z", "summary": "Standup"}],
    )

    assert "Sacred family time: 5-7pm" in result
    assert "yesterday_plan: wrote tests" in result
    assert "2026-07-03T09:00:00Z: Standup" in result


def test_build_system_prompt_handles_empty_inputs():
    result = build_system_prompt(profile="", state={}, events=[])

    assert "(no profile set)" in result
    assert "(none yet)" in result
    assert "(none)" in result


def test_build_system_prompt_includes_trello_tools_section():
    result = build_system_prompt(profile="", state={}, events=[])

    assert "## Trello tools" in result
    assert "list_trello_cards" in result
    assert "create_trello_card" in result
    assert "update_trello_card" in result
    assert "archive_trello_card" in result
