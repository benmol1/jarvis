import state as state_module


def test_save_then_load_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(state_module, "STATE_PATH", tmp_path / "state.json")

    state_module.save_state({"yesterday_plan": "wrote tests", "slipped": ["gym"]})

    assert state_module.load_state() == {"yesterday_plan": "wrote tests", "slipped": ["gym"]}


def test_load_missing_file_returns_empty_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(state_module, "STATE_PATH", tmp_path / "missing.json")

    assert state_module.load_state() == {}
