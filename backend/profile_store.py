import os
from pathlib import Path

PROFILE_PATH = Path(os.environ.get("JARVIS_PROFILE_PATH", "about_ben.md"))


def load_profile() -> str:
    if not PROFILE_PATH.exists():
        return ""
    return PROFILE_PATH.read_text()
