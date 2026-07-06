import os

from anthropic import Anthropic
from fastapi import FastAPI
from pydantic import BaseModel

from profile_store import load_profile
from prompt import build_system_prompt
from state import load_state
from trello_tool import get_cards
from calendar_tool import get_upcoming_events

app = FastAPI()
client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


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
    
    # Try to get Trello cards if credentials are configured
    try:
        cards = get_cards()
    except (KeyError, ImportError):
        # Missing Trello env vars or module issue - use empty list
        cards = []
    
    # Try to get calendar events if credentials are configured
    try:
        events = get_upcoming_events()
    except (KeyError, ImportError):
        # Missing Google Calendar env vars or module issue - use empty list
        events = []
    
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
