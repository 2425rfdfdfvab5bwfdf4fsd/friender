"""Trello router — REST endpoints for the Trello sidebar panel."""
from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from arix.integrations import trello as _trello

router = APIRouter(prefix="/api/trello", tags=["trello"])


class CreateCardRequest(BaseModel):
    list_id: str
    name: str
    desc: str = ""
    due: str = ""


@router.get("/status")
def trello_status():
    return {"configured": _trello.is_configured(), "setup": _trello.get_setup_instructions(), "provider": "trello"}


@router.get("/boards")
def trello_boards():
    return _trello.list_boards()


@router.get("/boards/{board_id}/lists")
def trello_lists(board_id: str):
    return _trello.get_lists(board_id=board_id)


@router.get("/boards/{board_id}/cards")
def trello_cards(board_id: str):
    return _trello.list_cards(board_id=board_id)


@router.post("/cards")
def trello_create_card(req: CreateCardRequest):
    return _trello.create_card(list_id=req.list_id, name=req.name, desc=req.desc, due=req.due)
