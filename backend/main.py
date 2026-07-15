import logging
import os

from anthropic import Anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import calendar_tool
from calendar_tool import get_upcoming_events
from profile_store import load_profile
from prompt import build_system_prompt
from state import load_state, save_state
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


class Turn(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    # Prior turns for session memory. The client (browser) holds the history
    # and replays it each call — the LLM API is stateless, so there's nothing
    # to store server-side. Absent (e.g. the iOS app) = single-turn as before.
    history: list[Turn] = []


class ChatResponse(BaseModel):
    reply: str
    # Foreign-event changes Jarvis proposed but did not apply — the browser
    # renders an Approve button per item that POSTs to /apply.
    pending: list = []


# Tools Claude may call. Jarvis freely mutates its own tagged events; moving or
# deleting anyone else's event is queued for Ben's approval instead of applied.
TOOLS = [
    {
        "name": "create_time_box",
        "description": "Create a time-box on Ben's calendar. Applies immediately.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "start": {"type": "string", "description": "ISO 8601 with offset"},
                "end": {"type": "string", "description": "ISO 8601 with offset"},
            },
            "required": ["summary", "start", "end"],
        },
    },
    {
        "name": "move_event",
        "description": (
            "Reschedule an event to new start/end. Applies immediately if Jarvis "
            "created it; otherwise queued for Ben's approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "calendar_id": {"type": "string"},
                "start": {"type": "string"},
                "end": {"type": "string"},
            },
            "required": ["event_id", "calendar_id", "start", "end"],
        },
    },
    {
        "name": "delete_event",
        "description": (
            "Delete an event. Applies immediately if Jarvis created it; "
            "otherwise queued for Ben's approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "calendar_id": {"type": "string"},
            },
            "required": ["event_id", "calendar_id"],
        },
    },
    {
        "name": "save_plan",
        "description": "Record the agreed day plan so tomorrow's Jarvis knows what was planned.",
        "input_schema": {
            "type": "object",
            "properties": {"plan": {"type": "string"}},
            "required": ["plan"],
        },
    },
]


def execute_tool(name: str, inp: dict, pending: list) -> str:
    """Run one tool call. Foreign-event edits are appended to `pending` and NOT
    applied — that's the approval gate; everything else applies immediately."""
    if name == "create_time_box":
        calendar_tool.create_event(inp["summary"], inp["start"], inp["end"])
        return f"Created '{inp['summary']}' ({inp['start']} to {inp['end']})."

    if name in ("move_event", "delete_event"):
        cal = inp.get("calendar_id", "primary")
        # Never trust the model about ownership — check the real event.
        event = calendar_tool.get_event(cal, inp["event_id"])
        if event["jarvis"]:
            if name == "move_event":
                calendar_tool.update_event(cal, inp["event_id"], inp["start"], inp["end"])
                return f"Moved '{event['summary']}'."
            calendar_tool.delete_event(cal, inp["event_id"])
            return f"Deleted '{event['summary']}'."
        label = (
            f"Move '{event['summary']}' to {inp['start']}"
            if name == "move_event"
            else f"Delete '{event['summary']}'"
        )
        pending.append(
            {
                "action": name,
                "calendar_id": cal,
                "event_id": inp["event_id"],
                "start": inp.get("start"),
                "end": inp.get("end"),
                "label": label,
            }
        )
        return f"Queued for Ben's approval: {label}. Not yet applied."

    if name == "save_plan":
        state = load_state()
        state["plan"] = inp["plan"]
        save_state(state)
        return "Saved the plan to rolling state."

    return f"Error: unknown tool {name}"


@app.post("/chat")
def chat(req: ChatRequest) -> ChatResponse:
    profile = load_profile()
    state = load_state()
    cards = fetch_context(get_cards, "trello")
    events = fetch_context(get_upcoming_events, "calendar")

    system_prompt = build_system_prompt(profile, state, events, cards)

    messages = [t.model_dump() for t in req.history]
    messages.append({"role": "user", "content": req.message})

    pending: list = []
    response = None
    # Bounded tool-use loop. ponytail: 8 rounds is plenty for a planning turn;
    # bump it if Claude legitimately chains more calls than that.
    for _ in range(8):
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
            tools=TOOLS,
        )
        if response.stop_reason != "tool_use":
            break
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                text = execute_tool(block.name, block.input, pending)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": text})
            except Exception as e:
                logger.warning("tool %s failed", block.name, exc_info=True)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Error: {e}",
                        "is_error": True,
                    }
                )
        messages.append({"role": "user", "content": results})

    reply = next((b.text for b in response.content if b.type == "text"), "")
    return ChatResponse(reply=reply, pending=pending)


class ApplyRequest(BaseModel):
    action: str  # "move_event" or "delete_event"
    calendar_id: str = "primary"
    event_id: str
    start: str | None = None
    end: str | None = None


@app.post("/apply")
def apply(req: ApplyRequest) -> dict:
    """Apply a foreign-event change Ben approved in the app."""
    if req.action == "move_event":
        calendar_tool.update_event(req.calendar_id, req.event_id, req.start, req.end)
    elif req.action == "delete_event":
        calendar_tool.delete_event(req.calendar_id, req.event_id)
    else:
        raise HTTPException(status_code=400, detail=f"unknown action {req.action}")
    return {"status": "applied"}


# Serve the web front-end. Mounted last so /chat and /health match first; the
# page fetches /chat same-origin, so no CORS is needed.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
