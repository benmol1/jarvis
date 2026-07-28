import ipaddress
import json
import logging
import os
from datetime import datetime, timedelta
from uuid import uuid4

from anthropic import Anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import calendar_tool
import maps_tool
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


# Tailscale's carrier-grade-NAT ranges — not RFC1918, so Python's
# ipaddress.is_private doesn't flag them, but they're exactly how a tailnet
# peer's source IP looks from here.
_TAILSCALE_RANGES = (
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("fd7a:115c:a1e0::/48"),
)


def classify_connection(client_host: str | None) -> str:
    """Classify how a request reached us from its source IP: over Ben's home
    LAN, over the Tailscale tailnet, or something else (shouldn't normally
    happen — nothing is port-forwarded to the internet)."""
    if not client_host:
        return "unknown"
    try:
        addr = ipaddress.ip_address(client_host)
    except ValueError:
        return "unknown"
    if any(addr in net for net in _TAILSCALE_RANGES):
        return "tailnet"
    if addr.is_private:
        return "local"
    return "unknown"


@app.get("/health")
def health(request: Request):
    """Health check endpoint for Docker/Kubernetes, and the connection-status
    read the iOS/web headers poll to show local vs tailnet vs offline."""
    client_host = request.client.host if request.client else None
    return {
        "status": "healthy",
        "service": "jarvis-backend",
        "connection": classify_connection(client_host),
    }


class Turn(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    # Prior turns for session memory. The client (browser) holds the history
    # and replays it each call — the LLM API is stateless, so there's nothing
    # to store server-side. Absent (e.g. the iOS app) = single-turn as before.
    history: list[Turn] = []
    # Live GPS from the iOS app, for the current_location tool. Omitted by the
    # web client and whenever iOS has no location permission/fix — the home-LAN
    # fallback in _current_location() covers the common case where this is absent.
    lat: float | None = None
    lon: float | None = None


def _current_location(req: ChatRequest, connection: str) -> str | None:
    """Where Ben is right now, for the current_location tool. Live GPS from the
    request wins when present (accurate anywhere); otherwise, if the request
    reached us over the home LAN, he's home. No other way to tell — the tailnet
    case without GPS stays unknown rather than guessing."""
    if req.lat is not None and req.lon is not None:
        return f"{req.lat},{req.lon}"
    if connection == "local":
        return maps_tool.saved_locations().get("home")
    return None


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
                "busy": {
                    "type": "boolean",
                    "description": (
                        "Whether this shows as busy in the Calendar UI. Default true. Set "
                        "false for an informational/FYI event (e.g. someone else's "
                        "reminder) that should never count as a diary clash."
                    ),
                },
                "color_id": {
                    "type": "string",
                    "description": (
                        "Event colour override, by id: "
                        + ", ".join(f"{k}={v}" for k, v in calendar_tool.EVENT_COLOR_NAMES.items())
                        + ". Omit to use the calendar's default colour."
                    ),
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
                "busy": {
                    "type": "boolean",
                    "description": (
                        "Whether this shows as busy in the Calendar UI. Set false to mark it "
                        "informational/FYI so it never counts as a diary clash."
                    ),
                },
                "color_id": {
                    "type": "string",
                    "description": (
                        "Event colour override, by id: "
                        + ", ".join(f"{k}={v}" for k, v in calendar_tool.EVENT_COLOR_NAMES.items())
                        + "."
                    ),
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
        "name": "find_place",
        "description": (
            'Look up a place from a fuzzy name or address (e.g. "Nando\'s Guildford", '
            '"Kings Cross station") and get its clean postal address and a Google '
            "Maps link. Read-only. Use this to turn a vague place into the location "
            "you then pass to create_event/modify_event, and put the maps_url in the "
            "event description so Ben can tap through."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Place name or address to resolve."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "current_location",
        "description": (
            "Ben's current physical location, as an origin you can pass straight to "
            "travel_time/add_route_to_event. Use this for 'from here'/'how long to "
            "get home from where I am' style questions, instead of guessing an "
            "origin. Read-only, no input. Returns nothing if his location can't be "
            "determined right now — ask him directly rather than assuming home/work."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "travel_time",
        "description": (
            "Estimate distance and travel time between two places. For driving it "
            "accounts for traffic at the departure time, so you can tell Ben when to "
            'leave for an event. Read-only. You can use "home" or "work" for origin/'
            "destination — they resolve to Ben's saved addresses. If you only know a "
            "rough place name, resolve it with find_place first. Pass several modes "
            "to compare them (e.g. driving vs the train)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {
                    "type": "string",
                    "description": 'Start address, place name, or "home"/"work".',
                },
                "destination": {
                    "type": "string",
                    "description": 'End address, place name, or "home"/"work".',
                },
                "modes": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["driving", "walking", "bicycling", "transit"],
                    },
                    "description": (
                        "Travel modes to estimate. Usually one; give several to "
                        'compare (e.g. ["driving", "transit"]). Defaults to '
                        '["driving"] — but if Ben hasn\'t said and a long trip could '
                        "plausibly be by train, ask him rather than assuming."
                    ),
                },
                "depart_at": {
                    "type": "string",
                    "description": (
                        "ISO 8601 departure time for a traffic-aware driving estimate "
                        "(e.g. before an event). Omit to leave now."
                    ),
                },
            },
            "required": ["origin", "destination"],
        },
    },
    {
        "name": "add_route_to_event",
        "description": (
            "Plan a route to a place and attach it to an existing event: sets the "
            "event's location and adds a Google Maps directions link, the travel "
            "time and a 'leave by' time to its description. Usually one mode; pass "
            "several to save both (e.g. driving and transit) so Ben can choose. "
            'Driving is traffic-aware. You can use "home"/"work" for origin/'
            "destination. Applies immediately if Jarvis created the event; otherwise "
            "queued for Ben's approval. Resolve a vague destination with find_place "
            "first if you want an exact address."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "calendar_id": {"type": "string"},
                "origin": {
                    "type": "string",
                    "description": 'Where Ben sets off from (e.g. "home").',
                },
                "destination": {"type": "string", "description": "Where the event is."},
                "modes": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["driving", "walking", "bicycling", "transit"],
                    },
                    "description": (
                        "Travel modes to save on the event. Usually one; give several "
                        'to compare (e.g. ["driving", "transit"]). If Ben hasn\'t said '
                        "how he's travelling and you can't infer it, ask him before "
                        "planning rather than guessing."
                    ),
                },
                "depart_at": {
                    "type": "string",
                    "description": (
                        "ISO 8601. Pass the event's start for a traffic-aware estimate "
                        "around that time; omit to base it on leaving now."
                    ),
                },
            },
            "required": ["event_id", "calendar_id", "origin", "destination", "modes"],
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
_MODIFY_FIELDS = (
    "start",
    "end",
    "title",
    "location",
    "description",
    "attendees",
    "busy",
    "color_id",
)

# Prefix of the route block add_route_to_event writes into an event description.
# Used to strip a stale block before re-writing, so re-planning replaces the
# route rather than stacking duplicates.
_ROUTE_MARKER = "🗺️ Route"


def _modes(inp: dict) -> list[str]:
    """Travel modes for a maps tool. Accepts a `modes` list (one or several, so
    Ben can compare) or a single `mode`, defaulting to driving."""
    if inp.get("modes"):
        return inp["modes"]
    return [inp["mode"]] if inp.get("mode") else ["driving"]


def _strip_route_block(body: str) -> str:
    """Drop a previously-added route block (it's always appended last) so a
    re-plan replaces it instead of piling on."""
    idx = body.find(_ROUTE_MARKER)
    return body[:idx].strip() if idx != -1 else body.strip()


def _leave_by(start: str | None, duration_seconds: int | None) -> str | None:
    """HH:MM Ben should leave to reach a timed event on time, when both the
    start and a travel duration are known. All-day events (date only) get none."""
    if not start or "T" not in start or not duration_seconds:
        return None
    try:
        start_dt = datetime.fromisoformat(start)
    except ValueError:
        return None
    return (start_dt - timedelta(seconds=duration_seconds)).strftime("%H:%M")


def _route_block(route: dict, start: str | None) -> str:
    """The description snippet describing a planned route: travel time (in
    traffic where known), distance, a leave-by time, and a directions link."""
    duration = route["duration_in_traffic"] or route["duration"]
    traffic = " in traffic" if route["duration_in_traffic"] else ""
    leave = _leave_by(start, route.get("duration_seconds"))
    leave_txt = f" Leave by {leave}." if leave else ""
    return (
        f"{_ROUTE_MARKER} to {route['destination']}: {duration}{traffic} "
        f"by {route['mode']} ({route['distance']}).{leave_txt}\n"
        f"Directions: {route['directions_url']}"
    )


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
                    "busy": inp.get("busy", True),
                    "color_id": inp.get("color_id"),
                    "label": label,
                }
            )
            return f"Queued for Ben's approval: {label}. Not yet applied."
        warning = ""
        if _far_out(inp["start"]):
            # Events marked "free" (busy=False) are informational only and
            # never count as a diary clash.
            conflicts = [
                c
                for c in calendar_tool.find_conflicts(inp["start"], inp["end"])
                if c.get("busy", True)
            ]
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
            busy=inp.get("busy", True),
            color_id=inp.get("color_id"),
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
            + (f"\n  location: {e['location']}" if e.get("location") else "")
            + (f"\n  description: {e['description']}" if e.get("description") else "")
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

    if name == "current_location":
        location = flags.get("current_location")
        if not location:
            return "Ben's current location isn't known right now — ask him if you need it."
        return location

    if name == "find_place":
        place = maps_tool.find_place(inp["query"])
        if not place:
            return f"No place found matching '{inp['query']}'."
        return (
            f"{place['location']}\n"
            f"location (for event): {place['location']}\n"
            f"maps link: {place['maps_url']}"
        )

    if name == "travel_time":
        modes = _modes(inp)
        results = [
            (m, maps_tool.travel_time(inp["origin"], inp["destination"], m, inp.get("depart_at")))
            for m in modes
        ]
        known = [t for _, t in results if t]
        if not known:
            return (
                f"No route found from '{inp['origin']}' to '{inp['destination']}' "
                f"by {', '.join(modes)}."
            )
        lines = [f"{known[0]['origin']} → {known[0]['destination']}:"]
        for m, trip in results:
            if not trip:
                lines.append(f"- {m}: no route")
                continue
            duration = trip["duration_in_traffic"] or trip["duration"]
            traffic = " in current traffic" if trip["duration_in_traffic"] else ""
            lines.append(f"- {trip['mode']}: {duration}{traffic}, {trip['distance']}")
        return "\n".join(lines)

    if name == "add_route_to_event":
        cal = inp["calendar_id"]
        modes = _modes(inp)
        # Never trust the model about ownership — check the real event.
        event = calendar_tool.get_event(cal, inp["event_id"])
        routes = [
            maps_tool.plan_route(inp["origin"], inp["destination"], m, inp.get("depart_at"))
            for m in modes
        ]
        found = [r for r in routes if r]
        if not found:
            return (
                f"No route found from '{inp['origin']}' to '{inp['destination']}' "
                f"by {', '.join(modes)}."
            )
        missing = [m for m, r in zip(modes, routes, strict=True) if not r]
        note = f" (no {', '.join(missing)} route)" if missing else ""
        blocks = "\n\n".join(_route_block(r, event.get("start")) for r in found)
        body = _strip_route_block(event.get("description") or "")
        new_description = f"{body}\n\n{blocks}".strip() if body else blocks
        location = found[0]["destination"]
        label_modes = ", ".join(r["mode"] for r in found)
        word = "route" if len(found) == 1 else "routes"
        if event["jarvis"]:
            calendar_tool.modify_event(
                cal, inp["event_id"], location=location, description=new_description
            )
            return f"Added the {label_modes} {word} to '{event['summary']}'.{note}\n\n{blocks}"
        label = f"Add {label_modes} {word} to '{event['summary']}' ({location})"
        pending.append(
            {
                "id": uuid4().hex,
                "action": "modify_event",
                "calendar_id": cal,
                "event_id": inp["event_id"],
                "label": label,
                "location": location,
                "description": new_description,
                "start": None,
                "end": None,
                "title": None,
                "attendees": None,
            }
        )
        return f"Queued for Ben's approval: {label}. Not yet applied.{note}"

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


def run_chat(req: ChatRequest, connection: str = "unknown"):
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
    flags = {"draft": False, "current_location": _current_location(req, connection)}
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
def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    client_host = request.client.host if request.client else None
    connection = classify_connection(client_host)
    return StreamingResponse(run_chat(req, connection), media_type="application/x-ndjson")


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
    # None = unspecified: create_event treats that as busy (its own default);
    # modify_event treats it as "leave unchanged".
    busy: bool | None = None
    color_id: str | None = None


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
            busy=req.busy if req.busy is not None else True,
            color_id=req.color_id,
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
            busy=req.busy,
            color_id=req.color_id,
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
