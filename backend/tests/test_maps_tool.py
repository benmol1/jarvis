from unittest.mock import MagicMock

import pytest

import maps_tool


def _response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


def test_find_place_returns_name_address_and_maps_link(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test_key")
    get = MagicMock(
        return_value=_response(
            {
                "status": "OK",
                "results": [
                    {
                        "name": "Nando's",
                        "formatted_address": "2 High St, Guildford GU1 3AA, UK",
                        "place_id": "pid123",
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(maps_tool.requests, "get", get)

    place = maps_tool.find_place("Nando's Guildford")

    assert place["name"] == "Nando's"
    assert place["address"] == "2 High St, Guildford GU1 3AA, UK"
    # Name is prepended because it isn't already in the address.
    assert place["location"] == "Nando's, 2 High St, Guildford GU1 3AA, UK"
    assert "query_place_id=pid123" in place["maps_url"]
    # Key travels as a query param, never logged.
    assert get.call_args.kwargs["params"]["key"] == "test_key"


def test_find_place_does_not_duplicate_name_already_in_address(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test_key")
    monkeypatch.setattr(
        maps_tool.requests,
        "get",
        MagicMock(
            return_value=_response(
                {
                    "status": "OK",
                    "results": [
                        {
                            "name": "10 Downing Street",
                            "formatted_address": "10 Downing Street, London SW1A 2AA, UK",
                            "place_id": "pid",
                        }
                    ],
                }
            )
        ),
    )

    place = maps_tool.find_place("10 Downing Street")

    assert place["location"] == "10 Downing Street, London SW1A 2AA, UK"


def test_find_place_returns_empty_on_zero_results(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test_key")
    monkeypatch.setattr(
        maps_tool.requests,
        "get",
        MagicMock(return_value=_response({"status": "ZERO_RESULTS", "results": []})),
    )

    assert maps_tool.find_place("asdkjfhaskjdfh") == {}


def test_find_place_raises_on_api_error(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test_key")
    monkeypatch.setattr(
        maps_tool.requests,
        "get",
        MagicMock(
            return_value=_response(
                {"status": "REQUEST_DENIED", "error_message": "API key not authorized"}
            )
        ),
    )

    with pytest.raises(maps_tool.MapsError, match="API key not authorized"):
        maps_tool.find_place("anywhere")


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)

    with pytest.raises(maps_tool.MapsError, match="GOOGLE_MAPS_API_KEY is not set"):
        maps_tool.find_place("anywhere")


def test_travel_time_prefers_traffic_aware_duration(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test_key")
    get = MagicMock(
        return_value=_response(
            {
                "status": "OK",
                "origin_addresses": ["Home, Guildford"],
                "destination_addresses": ["Office, London"],
                "rows": [
                    {
                        "elements": [
                            {
                                "status": "OK",
                                "distance": {"text": "45 km"},
                                "duration": {"text": "50 mins"},
                                "duration_in_traffic": {"text": "1 hour 10 mins"},
                            }
                        ]
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(maps_tool.requests, "get", get)

    trip = maps_tool.travel_time("Home", "Office")

    assert trip["duration_in_traffic"] == "1 hour 10 mins"
    assert trip["distance"] == "45 km"
    # driving defaults to a departure_time so traffic data comes back.
    assert get.call_args.kwargs["params"]["departure_time"] == "now"


def test_travel_time_rejects_unknown_mode(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test_key")

    with pytest.raises(maps_tool.MapsError, match="mode must be one of"):
        maps_tool.travel_time("A", "B", mode="teleport")


def test_travel_time_returns_empty_when_no_route(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test_key")
    monkeypatch.setattr(
        maps_tool.requests,
        "get",
        MagicMock(
            return_value=_response(
                {
                    "status": "OK",
                    "origin_addresses": ["A"],
                    "destination_addresses": ["B"],
                    "rows": [{"elements": [{"status": "ZERO_RESULTS"}]}],
                }
            )
        ),
    )

    assert maps_tool.travel_time("A", "B", mode="transit") == {}


def test_travel_time_walking_omits_departure_time_by_default(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test_key")
    get = MagicMock(
        return_value=_response(
            {
                "status": "OK",
                "origin_addresses": ["A"],
                "destination_addresses": ["B"],
                "rows": [
                    {
                        "elements": [
                            {
                                "status": "OK",
                                "distance": {"text": "1 km"},
                                "duration": {"text": "12 mins"},
                            }
                        ]
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(maps_tool.requests, "get", get)

    trip = maps_tool.travel_time("A", "B", mode="walking")

    assert trip["duration_in_traffic"] is None
    assert trip["duration"] == "12 mins"
    assert "departure_time" not in get.call_args.kwargs["params"]


def test_travel_time_exposes_numeric_seconds(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test_key")
    monkeypatch.setattr(
        maps_tool.requests,
        "get",
        MagicMock(
            return_value=_response(
                {
                    "status": "OK",
                    "origin_addresses": ["A"],
                    "destination_addresses": ["B"],
                    "rows": [
                        {
                            "elements": [
                                {
                                    "status": "OK",
                                    "distance": {"text": "45 km", "value": 45000},
                                    "duration": {"text": "50 mins", "value": 3000},
                                    "duration_in_traffic": {"text": "1 hour", "value": 3600},
                                }
                            ]
                        }
                    ],
                }
            )
        ),
    )

    trip = maps_tool.travel_time("A", "B")

    # Prefers the traffic-aware seconds so a "leave by" calc reflects traffic.
    assert trip["duration_seconds"] == 3600


def test_plan_route_adds_directions_link(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test_key")
    monkeypatch.setattr(
        maps_tool.requests,
        "get",
        MagicMock(
            return_value=_response(
                {
                    "status": "OK",
                    "origin_addresses": ["Home, Guildford"],
                    "destination_addresses": ["Office, London"],
                    "rows": [
                        {
                            "elements": [
                                {
                                    "status": "OK",
                                    "distance": {"text": "45 km", "value": 45000},
                                    "duration": {"text": "50 mins", "value": 3000},
                                    "duration_in_traffic": {"text": "1 hour", "value": 3600},
                                }
                            ]
                        }
                    ],
                }
            )
        ),
    )

    route = maps_tool.plan_route("Home", "Office")

    assert route["duration_in_traffic"] == "1 hour"
    # Deep link is built from the resolved addresses, not the raw query strings.
    assert route["directions_url"].startswith("https://www.google.com/maps/dir/?")
    assert "origin=Home%2C+Guildford" in route["directions_url"]
    assert "destination=Office%2C+London" in route["directions_url"]
    assert "travelmode=driving" in route["directions_url"]


def test_plan_route_returns_empty_when_no_route(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test_key")
    monkeypatch.setattr(
        maps_tool.requests,
        "get",
        MagicMock(
            return_value=_response(
                {
                    "status": "OK",
                    "origin_addresses": ["A"],
                    "destination_addresses": ["B"],
                    "rows": [{"elements": [{"status": "ZERO_RESULTS"}]}],
                }
            )
        ),
    )

    assert maps_tool.plan_route("A", "B", mode="transit") == {}


def test_resolve_location_expands_saved_aliases(monkeypatch):
    monkeypatch.setenv("JARVIS_HOME_ADDRESS", "1 Acacia Ave, Guildford")
    monkeypatch.setenv("JARVIS_WORK_ADDRESS", "10 Office Rd, London")

    assert maps_tool.resolve_location("home") == "1 Acacia Ave, Guildford"
    assert (
        maps_tool.resolve_location(" Work ") == "10 Office Rd, London"
    )  # trimmed, case-insensitive
    # Anything that isn't a saved alias passes straight through.
    assert maps_tool.resolve_location("Nando's Guildford") == "Nando's Guildford"


def test_resolve_location_passes_through_when_unset(monkeypatch):
    monkeypatch.delenv("JARVIS_HOME_ADDRESS", raising=False)
    monkeypatch.delenv("JARVIS_WORK_ADDRESS", raising=False)

    assert maps_tool.resolve_location("home") == "home"
    assert maps_tool.saved_locations() == {}


def test_travel_time_resolves_home_alias(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test_key")
    monkeypatch.setenv("JARVIS_HOME_ADDRESS", "1 Acacia Ave, Guildford")
    get = MagicMock(
        return_value=_response(
            {
                "status": "OK",
                "origin_addresses": ["1 Acacia Ave, Guildford"],
                "destination_addresses": ["Office"],
                "rows": [
                    {
                        "elements": [
                            {
                                "status": "OK",
                                "distance": {"text": "45 km"},
                                "duration": {"text": "50 mins", "value": 3000},
                            }
                        ]
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(maps_tool.requests, "get", get)

    maps_tool.travel_time("home", "Office")

    # The alias is expanded to the real address before hitting Google.
    assert get.call_args.kwargs["params"]["origins"] == "1 Acacia Ave, Guildford"


def test_past_departure_time_falls_back_to_now(monkeypatch):
    assert maps_tool._departure_epoch("2000-01-01T09:00:00+00:00") == "now"


def test_future_departure_time_becomes_epoch(monkeypatch):
    epoch = maps_tool._departure_epoch("2099-01-01T09:00:00+00:00")
    assert isinstance(epoch, int) and epoch > 0
