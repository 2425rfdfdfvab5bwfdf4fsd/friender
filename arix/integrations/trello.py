"""Trello integration — manage boards, lists, and cards via Trello API."""
from __future__ import annotations
import os
from typing import Any


def is_configured() -> bool:
    return bool(os.environ.get("TRELLO_API_KEY") and os.environ.get("TRELLO_API_TOKEN"))


def _params() -> dict:
    return {
        "key": os.environ.get("TRELLO_API_KEY", ""),
        "token": os.environ.get("TRELLO_API_TOKEN", ""),
    }


def _not_configured_error() -> dict:
    return {
        "ok": False,
        "error": "Trello not configured. Add TRELLO_API_KEY and TRELLO_API_TOKEN to Secrets (from trello.com/app-key).",
    }


def list_boards() -> dict:
    if not is_configured():
        return _not_configured_error()
    try:
        import httpx
        resp = httpx.get(
            "https://api.trello.com/1/members/me/boards",
            params={**_params(), "fields": "id,name,desc,url,closed"},
            timeout=15,
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"Trello API {resp.status_code}: {resp.text[:300]}"}
        boards = [
            {"id": b["id"], "name": b["name"], "desc": b.get("desc", ""), "url": b.get("url", "")}
            for b in resp.json() if not b.get("closed")
        ]
        return {"ok": True, "boards": boards, "count": len(boards)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_cards(board_id: str) -> dict:
    if not is_configured():
        return _not_configured_error()
    try:
        import httpx
        resp = httpx.get(
            f"https://api.trello.com/1/boards/{board_id}/cards",
            params={**_params(), "fields": "id,name,desc,due,idList,labels,url"},
            timeout=15,
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"Trello API {resp.status_code}: {resp.text[:300]}"}
        cards = [
            {
                "id": c["id"],
                "name": c["name"],
                "desc": c.get("desc", "")[:200],
                "due": c.get("due", ""),
                "list_id": c.get("idList", ""),
                "labels": [l["name"] for l in c.get("labels", [])],
                "url": c.get("url", ""),
            }
            for c in resp.json()
        ]
        return {"ok": True, "cards": cards, "count": len(cards)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def create_card(list_id: str, name: str, desc: str = "", due: str = "") -> dict:
    if not is_configured():
        return _not_configured_error()
    try:
        import httpx
        payload: dict[str, Any] = {**_params(), "idList": list_id, "name": name}
        if desc:
            payload["desc"] = desc
        if due:
            payload["due"] = due
        resp = httpx.post("https://api.trello.com/1/cards", params=payload, timeout=15)
        if resp.status_code in (200, 201):
            d = resp.json()
            return {"ok": True, "id": d["id"], "name": d["name"], "url": d.get("url", "")}
        return {"ok": False, "error": f"Create card failed {resp.status_code}: {resp.text[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_lists(board_id: str) -> dict:
    if not is_configured():
        return _not_configured_error()
    try:
        import httpx
        resp = httpx.get(
            f"https://api.trello.com/1/boards/{board_id}/lists",
            params={**_params(), "fields": "id,name"},
            timeout=10,
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"Trello API {resp.status_code}"}
        lists = [{"id": l["id"], "name": l["name"]} for l in resp.json()]
        return {"ok": True, "lists": lists}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_setup_instructions() -> str:
    return (
        "To connect Trello:\n"
        "1. Go to trello.com/app-key → copy your API key\n"
        "2. Click 'Generate a Token' on the same page\n"
        "3. Add TRELLO_API_KEY and TRELLO_API_TOKEN to Secrets"
    )
