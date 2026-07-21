from datetime import datetime
from zoneinfo import ZoneInfo

from prompt import build_system_prompt


def test_build_system_prompt_includes_current_datetime():
    now = datetime(2026, 7, 14, 8, 30, tzinfo=ZoneInfo("Europe/London"))
    result = build_system_prompt(profile="", state={}, events=[], cards=[], now=now)

    assert "Current date and time: Tuesday, 14 July 2026, 08:30 BST" in result


def test_build_system_prompt_includes_all_sections():
    result = build_system_prompt(
        profile="Sacred family time: 5-7pm",
        state={"yesterday_plan": "wrote tests"},
        events=[{"start": "2026-07-03T09:00:00Z", "summary": "Standup"}],
        cards=[{"name": "Write TODO", "due": "2026-07-03T00:00:00Z"}],
    )

    assert "Sacred family time: 5-7pm" in result
    assert "yesterday_plan: wrote tests" in result
    assert "2026-07-03T09:00:00Z: Standup" in result
    assert "Write TODO (due 2026-07-03T00:00:00Z)" in result


def test_persona_toggle():
    assert 'Address him as "sir"' in build_system_prompt("", {}, [], [])
    assert 'Address him as "sir"' not in build_system_prompt("", {}, [], [], persona="off")


def test_persona_env_var(monkeypatch):
    monkeypatch.setenv("JARVIS_PERSONA", "OFF")
    assert "## Voice" not in build_system_prompt("", {}, [], [])


def test_build_system_prompt_handles_empty_inputs():
    result = build_system_prompt(profile="", state={}, events=[], cards=[])

    assert "(no profile set)" in result
    assert "(none yet)" in result
    assert "(none)" in result
