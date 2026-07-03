import json
import os
from pathlib import Path

STATE_PATH = Path(os.environ.get("JARVIS_STATE_PATH", "state.json"))


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text())


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))
