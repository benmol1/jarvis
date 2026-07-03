from prompt import build_system_prompt


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


def test_build_system_prompt_handles_empty_inputs():
    result = build_system_prompt(profile="", state={}, events=[], cards=[])

    assert "(no profile set)" in result
    assert "(none yet)" in result
    assert "(none)" in result
