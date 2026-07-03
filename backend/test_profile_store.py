import profile_store


def test_load_profile_returns_file_contents(tmp_path, monkeypatch):
    path = tmp_path / "about_ben.md"
    path.write_text("priorities: ship Jarvis")
    monkeypatch.setattr(profile_store, "PROFILE_PATH", path)

    assert profile_store.load_profile() == "priorities: ship Jarvis"


def test_load_profile_missing_file_returns_empty_string(tmp_path, monkeypatch):
    monkeypatch.setattr(profile_store, "PROFILE_PATH", tmp_path / "missing.md")

    assert profile_store.load_profile() == ""
