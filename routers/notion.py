"""Notion router — REST endpoints for the Notion sidebar panel."""
from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from arix.integrations import notion as _notion

router = APIRouter(prefix="/api/notion", tags=["notion"])


class CreatePageRequest(BaseModel):
    title: str
    content: str = ""
    parent_page_id: str = ""


class AppendRequest(BaseModel):
    content: str


@router.get("/status")
def notion_status():
    return {"configured": _notion.is_configured(), "setup": _notion.get_setup_instructions()}


@router.get("/search")
def notion_search(q: str = "", limit: int = 10):
    return _notion.search_pages(query=q, max_results=limit)


@router.get("/page/{page_id}")
def notion_read_page(page_id: str):
    return _notion.read_page(page_id=page_id)


@router.post("/page")
def notion_create_page(req: CreatePageRequest):
    return _notion.create_page(title=req.title, content=req.content, parent_page_id=req.parent_page_id)


@router.patch("/page/{page_id}/append")
def notion_append(page_id: str, req: AppendRequest):
    return _notion.append_to_page(page_id=page_id, content=req.content)
