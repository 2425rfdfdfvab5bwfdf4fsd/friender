"""YouTube tools — wrappers for agent dispatch."""
from __future__ import annotations
from arix.integrations import youtube as _youtube


async def youtube_search(query: str, max_results: int = 10, dry_run: bool = False) -> dict:
    """Search YouTube for videos by keyword."""
    if not _youtube.is_configured():
        return {"ok": False, "error": "YouTube is not connected. Add credentials in the YouTube panel."}
    if dry_run:
        return {"dry_run": True, "action": "youtube_search", "query": query}
    import asyncio
    return await asyncio.to_thread(_youtube.search_videos, query=query, max_results=max_results)


async def youtube_get_video(video_id: str, dry_run: bool = False) -> dict:
    """Get detailed info about a YouTube video (views, likes, description, duration)."""
    if not _youtube.is_configured():
        return {"ok": False, "error": "YouTube is not connected. Add credentials in the YouTube panel."}
    if dry_run:
        return {"dry_run": True, "action": "youtube_get_video", "video_id": video_id}
    import asyncio
    return await asyncio.to_thread(_youtube.get_video_details, video_id=video_id)


async def youtube_search_channels(query: str, max_results: int = 5, dry_run: bool = False) -> dict:
    """Search YouTube for channels by name."""
    if not _youtube.is_configured():
        return {"ok": False, "error": "YouTube is not connected. Add credentials in the YouTube panel."}
    if dry_run:
        return {"dry_run": True, "action": "youtube_search_channels", "query": query}
    import asyncio
    return await asyncio.to_thread(_youtube.search_channels, query=query, max_results=max_results)
