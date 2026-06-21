"""Trello tools — wrappers for agent dispatch."""
from __future__ import annotations
from arix.integrations import trello as _trello


async def trello_list_boards(dry_run: bool = False) -> dict:
    """List all Trello boards for the authenticated user."""
    if not _trello.is_configured():
        return {"ok": False, "error": "Trello is not connected. Add credentials in the Trello panel."}
    if dry_run:
        return {"dry_run": True, "action": "trello_list_boards"}
    import asyncio
    return await asyncio.to_thread(_trello.list_boards)


async def trello_list_cards(board_id: str, dry_run: bool = False) -> dict:
    """List all cards on a Trello board."""
    if not _trello.is_configured():
        return {"ok": False, "error": "Trello is not connected. Add credentials in the Trello panel."}
    if dry_run:
        return {"dry_run": True, "action": "trello_list_cards", "board_id": board_id}
    import asyncio
    return await asyncio.to_thread(_trello.list_cards, board_id=board_id)


async def trello_create_card(list_id: str, name: str, desc: str = "", due: str = "", dry_run: bool = False) -> dict:
    """Create a new card on a Trello list."""
    if not _trello.is_configured():
        return {"ok": False, "error": "Trello is not connected. Add credentials in the Trello panel."}
    if dry_run:
        return {"dry_run": True, "action": "trello_create_card", "name": name, "list_id": list_id}
    import asyncio
    return await asyncio.to_thread(_trello.create_card, list_id=list_id, name=name, desc=desc, due=due)


async def trello_get_lists(board_id: str, dry_run: bool = False) -> dict:
    """Get all lists (columns) on a Trello board."""
    if not _trello.is_configured():
        return {"ok": False, "error": "Trello is not connected. Add credentials in the Trello panel."}
    if dry_run:
        return {"dry_run": True, "action": "trello_get_lists", "board_id": board_id}
    import asyncio
    return await asyncio.to_thread(_trello.get_lists, board_id=board_id)
