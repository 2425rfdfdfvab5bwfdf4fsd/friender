"""Notion tools — wrappers for agent dispatch."""
from __future__ import annotations
from arix.integrations import notion as _notion


async def notion_search(query: str = "", max_results: int = 10, dry_run: bool = False) -> dict:
    """Search Notion pages and databases."""
    if dry_run:
        return {"dry_run": True, "action": "notion_search", "query": query}
    import asyncio
    return await asyncio.to_thread(_notion.search_pages, query=query, max_results=max_results)


async def notion_read_page(page_id: str, dry_run: bool = False) -> dict:
    """Read the content of a Notion page by ID."""
    if dry_run:
        return {"dry_run": True, "action": "notion_read_page", "page_id": page_id}
    import asyncio
    return await asyncio.to_thread(_notion.read_page, page_id=page_id)


async def notion_create_page(title: str, content: str = "", parent_page_id: str = "", dry_run: bool = False) -> dict:
    """Create a new Notion page with optional content."""
    if dry_run:
        return {"dry_run": True, "action": "notion_create_page", "title": title}
    import asyncio
    return await asyncio.to_thread(_notion.create_page, title=title, content=content, parent_page_id=parent_page_id)


async def notion_append_to_page(page_id: str, content: str, dry_run: bool = False) -> dict:
    """Append text content to an existing Notion page."""
    if dry_run:
        return {"dry_run": True, "action": "notion_append_to_page", "page_id": page_id}
    import asyncio
    return await asyncio.to_thread(_notion.append_to_page, page_id=page_id, content=content)
