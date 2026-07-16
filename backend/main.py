import json
import logging
import os
from datetime import datetime, timedelta
from uuid import uuid4

from anthropic import Anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
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


# Tools Claude may call. Jarvis freely mutates its own tagged events; moving or
# deleting anyone else's event is queued for Ben's approval instead of applied.
TOOLS = [
    {
        "name": "create_event",
        "description": (
            "Create an event on Ben's calendar. Applies immediately UNLESS it has "
            "attendees, which sends real invites and is queued for Ben's approval. "
            "Warns if it overlaps an existing event more than 14 days out."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "start": {"type": "string", "description": "ISO 8601 with offset"},
                "end": {"type": "string", "description": "ISO 8601 with offset"},
                "calendar_id": {
                    "type": "string",
                    "description": (
                        "Target calendar id from the calendar list. Omit to use "
                        "Ben's primary/Personal calendar."
                    ),
                },
                "location": {"type": "string"},
                "description": {"type": "string", "description": "Human-readable notes/agenda."},
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Email addresses to invite. Adding any queues for approval.",
                },
            },
            "required": ["summary", "start", "end"],
        },
    },
    {
        "name": "modify_event",
        "description": (
            "Change any subset of an event's fields (start, end, title, location, "
            "description, attendees). Applies immediately if Jarvis created it and "
            "no attendees are being set; otherwise queued for Ben's approval. "
            "Replaces the old move_event tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "calendar_id": {"type": "string"},
                "start": {"type": "string", "description": "ISO 8601 with offset"},
                "end": {"type": "string", "description": "ISO 8601 with offset"},
                "title": {"type": "string"},
                "location": {"type": "string"},
                "description": {"type": "string"},
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Email addresses to invite. Setting any queues for approval.",
                },
            },
            "required": ["event_id", "calendar_id"],
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
        "name": "move_to_calendar",
        "description": (
            "Move an event to a different calendar (keeps its time). Applies "
            "immediately if Jarvis created it; otherwise queued for Ben's approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "calendar_id": {"type": "string", "description": "The event's current calendar"},
                "destination_calendar_id": {"type": "string", "description": "Calendar to move to"},
            },
            "required": ["event_id", "calendar_id", "destination_calendar_id"],
        },
    },
    {
        "name": "copy_event",
        "description": (
            "Copy an event into another calendar, leaving the original in place. "
            "Non-destructive, so applies immediately; the copy is Jarvis-owned."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "calendar_id": {"type": "string", "description": "The event's current calendar"},
                "destination_calendar_id": {"type": "string", "description": "Calendar to copy to"},
            },
            "required": ["event_id", "calendar_id", "destination_calendar_id"],
        },
    },
    {
        "name": "list_events",
        "description": (
            "Look up events in a specific date range, e.g. when Ben asks about a "
            "week or month outside the events already listed in context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "ISO 8601 with offset"},
                "end": {"type": "string", "description": "ISO 8601 with offset"},
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "list_calendars",
        "description": (
            "List all of Ben's calendars as name/id pairs. The calendar list is "
            "already in context; use this only to re-fetch it if it looks stale or "
            "missing."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "respond_to_event",
        "description": (
            "RSVP to an event Ben was invited to, on his behalf. Notifies the organiser."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "calendar_id": {"type": "string"},
                "response": {"type": "string", "enum": ["accepted", "declined", "tentative"]},
            },
            "required": ["event_id", "calendar_id", "response"],
        },
    },
    {
        "name": "cancel_approval",
        "description": (
            "Retract a change still awaiting Ben's approval, by its approval_id "
            "(shown in the 'Pending approvals' context). Use when Ben changes his "
            "mind before approving."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"approval_id": {"type": "string"}},
            "required": ["approval_id"],
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
    {
        "name": "flag_draft_message",
        "description": (
            "Call this whenever your reply includes a message drafted for Ben to "
            "copy and send himself to another person (per the guardrail on changes "
            "affecting other people). Lets the client show a Copy button."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _far_out(start: str) -> bool:
    """True if `start` is more than 14 days away — i.e. beyond the window the
    prompt already shows Jarvis, so a conflict check is worth running."""
    try:
        start_dt = datetime.fromisoformat(start)
    except ValueError:
        return False
    now = datetime.now(start_dt.tzinfo) if start_dt.tzinfo else datetime.now()
    return start_dt > now + timedelta(days=14)


# Fields modify_event may carry through to calendar_tool.modify_event / an
# approval payload. Kept in one place so the tool, the queue item and /apply
# stay in sync.
_MODIFY_FIELDS = ("start", "end", "title", "location", "description", "attendees")


def execute_tool(name: str, inp: dict, state: dict, flags: dict) -> str:
    """Run one tool call. Foreign-event edits (and any change that invites other
    people) are appended to state["pending_approvals"] and NOT applied — that's
    the approval gate; everything else applies immediately."""
    pending: list = state.setdefault("pending_approvals", [])

    if name == "create_event":
        if inp.get("attendees"):
            # Inviting others is outward-facing — queue rather than apply.
            label = f"Create '{inp['summary']}' and invite {', '.join(inp['attendees'])}"
            pending.append(
                {
                    "id": uuid4().hex,
                    "action": "create_event",
                    "summary": inp["summary"],
                    "start": inp["start"],
                    "end": inp["end"],
                    "calendar_id": inp.get("calendar_id", "primary"),
                    "location": inp.get("location"),
                    "description": inp.get("description"),
                    "attendees": inp["attendees"],
                    "label": label,
                }
            )
            return f"Queued for Ben's approval: {label}. Not yet applied."
        warning = ""
        if _far_out(inp["start"]):
            conflicts = calendar_tool.find_conflicts(inp["start"], inp["end"])
            if conflicts:
                names = ", ".join(f"{c['summary']} ({c['start']})" for c in conflicts)
                warning = f" Warning: overlaps existing event(s): {names}."
        calendar_tool.create_event(
            inp["summary"],
            inp["start"],
            inp["end"],
            inp.get("calendar_id", "primary"),
            location=inp.get("location"),
            description=inp.get("description"),
        )
        return f"Created '{inp['summary']}' ({inp['start']} to {inp['end']}).{warning}"

    if name == "copy_event":
        # Non-destructive — leaves the original — so it applies immediately
        # regardless of who owns the source. The copy is Jarvis-owned.
        copied = calendar_tool.copy_event(
            inp["calendar_id"], inp["event_id"], inp["destination_calendar_id"]
        )
        return f"Copied '{copied.get('summary', '(no title)')}' into the target calendar."

    if name == "move_to_calendar":
        cal = inp["calendar_id"]
        dest = inp["destination_calendar_id"]
        # Never trust the model about ownership — check the real event.
        event = calendar_tool.get_event(cal, inp["event_id"])
        if event["jarvis"]:
            calendar_tool.move_event_to_calendar(cal, inp["event_id"], dest)
            return f"Moved '{event['summary']}' to the target calendar."
        label = f"Move '{event['summary']}' to another calendar"
        pending.append(
            {
                "id": uuid4().hex,
                "action": "move_to_calendar",
                "calendar_id": cal,
                "event_id": inp["event_id"],
                "destination_calendar_id": dest,
                "label": label,
            }
        )
        return f"Queued for Ben's approval: {label}. Not yet applied."

    if name == "modify_event":
        cal = inp["calendar_id"]
        fields = {k: inp[k] for k in _MODIFY_FIELDS if k in inp}
        # Never trust the model about ownership — check the real event.
        event = calendar_tool.get_event(cal, inp["event_id"])
        # Adding attendees emails real invites, so it needs approval even on a
        # Jarvis-owned event.
        if event["jarvis"] and not inp.get("attendees"):
            calendar_tool.modify_event(cal, inp["event_id"], **fields)
            return f"Updated '{event['summary']}'."
        changed = ", ".join(fields) or "no fields"
        label = f"Update '{event['summary']}' ({changed})"
        pending.append(
            {
                "id": uuid4().hex,
                "action": "modify_event",
                "calendar_id": cal,
                "event_id": inp["event_id"],
                "label": label,
                **{k: inp.get(k) for k in _MODIFY_FIELDS},
            }
        )
        return f"Queued for Ben's approval: {label}. Not yet applied."

    if name == "delete_event":
        cal = inp.get("calendar_id", "primary")
        # Never trust the model about ownership — check the real event.
        event = calendar_tool.get_event(cal, inp["event_id"])
        if event["jarvis"]:
            calendar_tool.delete_event(cal, inp["event_id"])
            return f"Deleted '{event['summary']}'."
        label = f"Delete '{event['summary']}'"
        pending.append(
            {
                "id": uuid4().hex,
                "action": "delete_event",
                "calendar_id": cal,
                "event_id": inp["event_id"],
                "label": label,
            }
        )
        return f"Queued for Ben's approval: {label}. Not yet applied."

    if name == "list_events":
        events = calendar_tool.get_events_in_range(inp["start"], inp["end"])
        if not events:
            return "No events found in that range."
        return "\n".join(
            f"{e['start']} to {e['end']}: {e['summary']} ({e['calendar']}) "
            f"(event_id={e['id']}, calendar_id={e['calendar_id']})"
            for e in events
        )

    if name == "list_calendars":
        calendars = calendar_tool.list_calendars()
        if not calendars:
            return "No calendars found."
        return "\n".join(f"{c['name']} (calendar_id={c['id']})" for c in calendars)

    if name == "respond_to_event":
        calendar_tool.respond_to_event(inp["calendar_id"], inp["event_id"], inp["response"])
        return f"Responded '{inp['response']}' to the event."

    if name == "cancel_approval":
        aid = inp["approval_id"]
        before = len(pending)
        pending[:] = [p for p in pending if p.get("id") != aid]
        if len(pending) < before:
            return "Cancelled the pending approval."
        return "No pending approval with that id."

    if name == "save_plan":
        state["plan"] = inp["plan"]
        return "Saved the plan to rolling state."

    if name == "flag_draft_message":
        flags["draft"] = True
        return "Noted — the client will show a Copy button."

    return f"Error: unknown tool {name}"


def run_chat(req: ChatRequest):
    """Runs the tool-use loop, yielding one NDJSON line per tool call so the
    client can show interim progress, then a final line with the reply."""
    profile = load_profile()
    state = load_state()
    cards = fetch_context(get_cards, "trello")
    events = fetch_context(get_upcoming_events, "calendar")
    calendars = fetch_context(calendar_tool.list_calendars, "calendar list")

    system_prompt = build_system_prompt(profile, state, events, cards, calendars=calendars)

    messages = [t.model_dump() for t in req.history]
    messages.append({"role": "user", "content": req.message})

    # Approvals persist in state so a later turn (or Ben changing his mind) can
    # see and cancel them; execute_tool mutates state["pending_approvals"].
    state.setdefault("pending_approvals", [])
    flags = {"draft": False}
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
            yield json.dumps({"type": "tool", "name": block.name}) + "\n"
            try:
                text = execute_tool(block.name, block.input, state, flags)
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

    # Persist any approvals queued or cancelled this turn (and any saved plan).
    save_state(state)

    reply = next((b.text for b in response.content if b.type == "text"), "")
    yield (
        json.dumps(
            {
                "type": "final",
                "reply": reply,
                "pending": state["pending_approvals"],
                "is_draft": flags["draft"],
            }
        )
        + "\n"
    )


@app.post("/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    return StreamingResponse(run_chat(req), media_type="application/x-ndjson")


class ApplyRequest(BaseModel):
    # id ties the approval back to state["pending_approvals"] so it can be
    # cleared once applied. event_id is absent for a queued create_event.
    id: str | None = None
    action: str  # create_event, modify_event, delete_event, move_to_calendar
    calendar_id: str = "primary"
    event_id: str | None = None
    summary: str | None = None
    start: str | None = None
    end: str | None = None
    title: str | None = None
    location: str | None = None
    description: str | None = None
    attendees: list[str] | None = None
    destination_calendar_id: str | None = None


@app.post("/apply")
def apply(req: ApplyRequest) -> dict:
    """Apply a change Ben approved in the app, then drop it from the queue."""
    if req.action == "create_event":
        calendar_tool.create_event(
            req.summary,
            req.start,
            req.end,
            req.calendar_id,
            location=req.location,
            description=req.description,
            attendees=req.attendees,
        )
    elif req.action == "modify_event":
        calendar_tool.modify_event(
            req.calendar_id,
            req.event_id,
            start=req.start,
            end=req.end,
            title=req.title,
            location=req.location,
            description=req.description,
            attendees=req.attendees,
        )
    elif req.action == "delete_event":
        calendar_tool.delete_event(req.calendar_id, req.event_id)
    elif req.action == "move_to_calendar":
        calendar_tool.move_event_to_calendar(
            req.calendar_id, req.event_id, req.destination_calendar_id
        )
    else:
        raise HTTPException(status_code=400, detail=f"unknown action {req.action}")

    # Clear the approved item from the persisted queue so it stops re-rendering.
    if req.id:
        state = load_state()
        approvals = state.get("pending_approvals", [])
        state["pending_approvals"] = [p for p in approvals if p.get("id") != req.id]
        save_state(state)
    return {"status": "applied"}


# Serve the web front-end. Mounted last so /chat and /health match first; the
# page fetches /chat same-origin, so no CORS is needed.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
