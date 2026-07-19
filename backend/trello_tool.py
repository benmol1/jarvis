import os

import requests

TRELLO_API = "https://api.trello.com/1"


def _auth() -> dict:
    return {"key": os.environ["TRELLO_API_KEY"], "token": os.environ["TRELLO_TOKEN"]}


def _board_id() -> str:
    return os.environ["TRELLO_BOARD_ID"]


def get_lists() -> list[dict]:
    resp = requests.get(
        f"{TRELLO_API}/boards/{_board_id()}/lists",
        params={**_auth(), "fields": "name"},
        timeout=10,
    )
    resp.raise_for_status()
    return [{"id": lst["id"], "name": lst["name"]} for lst in resp.json()]


def _list_name_to_id(lists: list[dict], name: str) -> str:
    for lst in lists:
        if lst["name"].lower() == name.lower():
            return lst["id"]
    available = ", ".join(lst["name"] for lst in lists)
    raise ValueError(f"No list named '{name}'. Available lists: {available}")


def _list_id_to_name(lists: list[dict], list_id: str) -> str:
    for lst in lists:
        if lst["id"] == list_id:
            return lst["name"]
    return "Unknown"


def get_cards(exclude_done: bool = True) -> list[dict]:
    lists = get_lists()
    done_ids = {lst["id"] for lst in lists if lst["name"].lower() == "done"}

    resp = requests.get(
        f"{TRELLO_API}/boards/{_board_id()}/cards",
        params={**_auth(), "fields": "name,due,desc,idList,labels,closed"},
        timeout=10,
    )
    resp.raise_for_status()

    cards = []
    for card in resp.json():
        if card.get("closed"):
            continue
        if exclude_done and card["idList"] in done_ids:
            continue
        cards.append(
            {
                "id": card["id"],
                "name": card["name"],
                "list": _list_id_to_name(lists, card["idList"]),
                "due": card.get("due"),
                "description": card.get("desc") or None,
                "labels": [lb["name"] for lb in card.get("labels", []) if lb.get("name")],
            }
        )
    return cards


def create_card(
    name: str,
    list_name: str,
    description: str | None = None,
    due: str | None = None,
) -> dict:
    lists = get_lists()
    list_id = _list_name_to_id(lists, list_name)

    params = {**_auth(), "name": name, "idList": list_id}
    if description:
        params["desc"] = description
    if due:
        params["due"] = due

    resp = requests.post(f"{TRELLO_API}/cards", params=params, timeout=10)
    resp.raise_for_status()
    card = resp.json()
    return {
        "id": card["id"],
        "name": card["name"],
        "list": list_name,
        "due": card.get("due"),
        "description": card.get("desc") or None,
    }


def update_card(
    card_id: str,
    name: str | None = None,
    description: str | None = None,
    due: str | None = None,
    list_name: str | None = None,
) -> dict:
    params = {**_auth()}
    if name is not None:
        params["name"] = name
    if description is not None:
        params["desc"] = description
    if due is not None:
        params["due"] = due
    if list_name is not None:
        lists = get_lists()
        params["idList"] = _list_name_to_id(lists, list_name)

    resp = requests.put(f"{TRELLO_API}/cards/{card_id}", params=params, timeout=10)
    resp.raise_for_status()
    card = resp.json()

    all_lists = get_lists() if list_name is None else lists
    return {
        "id": card["id"],
        "name": card["name"],
        "list": _list_id_to_name(all_lists, card["idList"]),
        "due": card.get("due"),
        "description": card.get("desc") or None,
    }


def archive_card(card_id: str) -> dict:
    resp = requests.put(
        f"{TRELLO_API}/cards/{card_id}",
        params={**_auth(), "closed": "true"},
        timeout=10,
    )
    resp.raise_for_status()
    card = resp.json()
    return {"id": card["id"], "name": card["name"], "archived": True}
