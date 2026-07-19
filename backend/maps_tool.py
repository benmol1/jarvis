import os
from datetime import datetime
from urllib.parse import urlencode

import requests

# Google Maps Platform web services. Unlike Calendar these use a plain API key
# (GOOGLE_MAPS_API_KEY), not OAuth — there is no refresh token to mint. The key
# needs the "Distance Matrix API" and "Places API" enabled in the same Google
# Cloud project.
MAPS_API = "https://maps.googleapis.com"

# Travel modes Distance Matrix accepts. driving is the only one that reports a
# traffic-aware duration (and only when a departure_time is supplied).
VALID_MODES = ("driving", "walking", "bicycling", "transit")


class MapsError(RuntimeError):
    """A Maps request came back with a non-OK status. Surfaced to Jarvis as a
    tool error rather than crashing the chat turn."""


def _api_key() -> str:
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        raise MapsError("GOOGLE_MAPS_API_KEY is not set")
    return key


def _maps_url(query: str, place_id: str | None) -> str:
    """A shareable Google Maps deep link. Pinning query_place_id makes it resolve
    to the exact place rather than a fresh search, so it survives in an event."""
    params = {"api": 1, "query": query}
    if place_id:
        params["query_place_id"] = place_id
    return f"https://www.google.com/maps/search/?{urlencode(params)}"


def find_place(query: str) -> dict:
    """Resolve a fuzzy query ("Nando's Guildford", "10 Downing St") to a clean
    name, postal address, and Maps link — what you attach to an event's location.

    Returns {} when nothing matches, so the caller can say so rather than guess.
    """
    resp = requests.get(
        f"{MAPS_API}/maps/api/place/textsearch/json",
        params={"query": query, "key": _api_key()},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    status = data.get("status")
    if status == "ZERO_RESULTS":
        return {}
    if status != "OK":
        raise MapsError(f"Places lookup failed: {status} {data.get('error_message', '')}".strip())

    top = data["results"][0]
    place_id = top.get("place_id")
    name = top.get("name", "")
    address = top.get("formatted_address", "")
    # A calendar location reads best as "Name, Address", but don't repeat the
    # name when Places already folded it into the formatted address.
    if name and name not in address:
        location = f"{name}, {address}" if address else name
    else:
        location = address or name
    return {
        "name": name,
        "address": address,
        "location": location,
        "place_id": place_id,
        "maps_url": _maps_url(location, place_id),
    }


def _departure_epoch(depart_at: str | None) -> int | str:
    """Distance Matrix wants departure_time as a Unix second or the literal
    "now"; it rejects times in the past. Convert an ISO 8601 string, falling
    back to "now" when it's absent, unparseable, or already behind us."""
    if not depart_at:
        return "now"
    try:
        dt = datetime.fromisoformat(depart_at)
    except ValueError:
        return "now"
    epoch = int(dt.timestamp())
    return epoch if epoch > int(datetime.now().timestamp()) else "now"


def travel_time(
    origin: str,
    destination: str,
    mode: str = "driving",
    depart_at: str | None = None,
) -> dict:
    """Estimate distance and duration between two places. For driving this asks
    for a traffic-aware estimate at depart_at (default: leaving now), so Jarvis
    can work out when Ben needs to set off for an event.

    Returns {} when there's no route (e.g. no transit connection).
    """
    if mode not in VALID_MODES:
        raise MapsError(f"mode must be one of {', '.join(VALID_MODES)}, got {mode!r}")

    params = {
        "origins": origin,
        "destinations": destination,
        "mode": mode,
        "key": _api_key(),
    }
    # duration_in_traffic only comes back for driving, and only with a
    # departure_time; harmless to send for the other modes when Ben names a time.
    if mode == "driving":
        params["departure_time"] = _departure_epoch(depart_at)
    elif depart_at:
        params["departure_time"] = _departure_epoch(depart_at)

    resp = requests.get(f"{MAPS_API}/maps/api/distancematrix/json", params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "OK":
        raise MapsError(
            f"Travel lookup failed: {data.get('status')} {data.get('error_message', '')}".strip()
        )

    element = data["rows"][0]["elements"][0]
    if element.get("status") != "OK":
        return {}  # e.g. ZERO_RESULTS / NOT_FOUND — no usable route

    in_traffic = element.get("duration_in_traffic", {}).get("text")
    return {
        "origin": data["origin_addresses"][0],
        "destination": data["destination_addresses"][0],
        "mode": mode,
        "distance": element["distance"]["text"],
        "duration": element["duration"]["text"],
        # Present only for driving with a departure_time; None otherwise.
        "duration_in_traffic": in_traffic,
    }
