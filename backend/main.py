import os

from anthropic import Anthropic
from fastapi import FastAPI
from pydantic import BaseModel

from profile_store import load_profile
from prompt import build_system_prompt
from state import load_state
from trello_tool import get_cards

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
    
    system_prompt = build_system_prompt(profile, state, [], cards)
    
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": req.message},
        ],
    )
    return ChatResponse(reply=response.content[0].text)
