import os

from anthropic import Anthropic
from fastapi import FastAPI
from pydantic import BaseModel

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
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": req.message}],
    )
    return ChatResponse(reply=response.content[0].text)
