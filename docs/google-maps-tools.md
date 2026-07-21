# Google Maps tools

## Summary

Integrates the Google Maps APIs so Jarvis can look up places, estimate travel times,
and plan routes with traffic-aware estimates. These tools let Jarvis answer "how long
to get there" questions and attach routing information to calendar events
automatically.

## Key changes

### New `maps_tool.py` module

Wraps the Google Maps Places and Distance Matrix APIs.

| Function | Does |
|---|---|
| `find_place()` | Resolve fuzzy place names/addresses to clean postal addresses and Maps links |
| `travel_time()` | Estimate distance and duration between two places (driving / walking / bicycling / transit), traffic-aware for driving |
| `plan_route()` | Combine a travel time with a directions link, for calendar integration |
| `resolve_location()` | Expand saved aliases (`"home"` / `"work"`) to real addresses |

Errors surface through a dedicated `MapsError` exception class.

### New tool handlers in `main.py`

- **`find_place`** — returns a location and Maps link for event setup.
- **`travel_time`** — supports multiple modes for comparison (e.g. driving vs transit).
- **`add_route_to_event`** — plans a route and writes it into an event's description:
  - sets the event location to the destination;
  - adds travel time and distance;
  - adds a "leave by" time, calculated from the event start and travel duration;
  - adds a Google Maps directions link.

  It handles both Jarvis-created events (applied immediately) and foreign events
  (queued for approval), and replaces stale route blocks on re-planning rather than
  duplicating them.

### Configuration

- `.env.example` — adds `GOOGLE_MAPS_API_KEY`, plus the optional
  `JARVIS_HOME_ADDRESS` / `JARVIS_WORK_ADDRESS`.
- `prompt.py` — adds the tool descriptions to the system prompt.

### Tests

Coverage lives in the new `test_maps_tool.py`, with additions to `test_main.py`:

- place lookup, with deduplication of names already present in the address;
- traffic-aware travel time estimates;
- multiple-mode comparison;
- route block replacement on re-planning;
- approval queuing for foreign events;
- leave-by time calculation;
- saved location alias resolution.

## Implementation notes

- The API key travels as a query parameter (never logged), per Google's security
  guidance.
- Traffic-aware duration is only available for driving mode with a departure time.
- Numeric seconds are exposed alongside human-readable durations, for "leave by"
  calculations.
- Route blocks are marked with a 🗺️ emoji, so they're easy to identify and replace.
- Missing routes are handled gracefully (return an empty dict); API errors raise
  `MapsError`.
