import logging
import os

from anthropic import Anthropic
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from calendar_tool import get_upcoming_events
from profile_store import load_profile
from prompt import build_system_prompt
from state import load_state
from trello_tool import get_cards

# Load backend/.env before reading os.environ below. No-op in Docker, which
# injects vars via compose's env_file instead.
load_dotenv()

app = FastAPI()
client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
logger = logging.getLogger(__name__)


def fetch_context(fetch, source: str) -> list[dict]:
    """Fetch context for the prompt, degrading to no data if the source fails.

    A missing credential or a dead upstream should cost us that section of the
    prompt, not the whole conversation.
    """
    try:
        return fetch()
    except Exception:
        logger.warning("%s unavailable; continuing without it", source, exc_info=True)
        return []


@app.get("/health")
def health():
    """Health check endpoint for Docker/Kubernetes."""
    return {"status": "healthy", "service": "jarvis-backend"}


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.post("/chat")
def chat(req: ChatRequest) -> ChatResponse:
    profile = load_profile()
    state = load_state()
    cards = fetch_context(get_cards, "trello")
    events = fetch_context(get_upcoming_events, "calendar")

    system_prompt = build_system_prompt(profile, state, events, cards)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=system_prompt,
        messages=[
            {"role": "user", "content": req.message},
        ],
    )
    return ChatResponse(reply=response.content[0].text)


# Serve the web front-end. Mounted last so /chat and /health match first; the
# page fetches /chat same-origin, so no CORS is needed.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
