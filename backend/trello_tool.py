import os
import requests

TRELLO_API = "https://api.trello.com/1"


def get_cards() -> list[dict]:
    api_key = os.environ["TRELLO_API_KEY"]
    token = os.environ["TRELLO_TOKEN"]
    board_id = os.environ["TRELLO_BOARD_ID"]
    
    response = requests.get(
        f"{TRELLO_API}/boards/{board_id}/cards",
        params={"key": api_key, "token": token, "fields": "name,due,idList"},
        timeout=10,
    )
    response.raise_for_status()
    return [
        {"name": card["name"], "due": card.get("due"), "list_id": card["idList"]}
        for card in response.json()
    ]
