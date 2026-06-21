"""Spotify tools — wrappers for agent dispatch."""
from __future__ import annotations
from arix.integrations import spotify as _spotify


async def spotify_search(query: str, limit: int = 10, dry_run: bool = False) -> dict:
    """Search Spotify for tracks by name, artist, or album."""
    if not _spotify.is_configured():
        return {"ok": False, "error": "Spotify is not connected. Add credentials in the Spotify panel."}
    if dry_run:
        return {"dry_run": True, "action": "spotify_search", "query": query}
    import asyncio
    return await asyncio.to_thread(_spotify.search_tracks, query=query, limit=limit)


async def spotify_current_track(dry_run: bool = False) -> dict:
    """Get the currently playing Spotify track."""
    if not _spotify.is_configured():
        return {"ok": False, "error": "Spotify is not connected. Add credentials in the Spotify panel."}
    if dry_run:
        return {"dry_run": True, "action": "spotify_current_track"}
    import asyncio
    return await asyncio.to_thread(_spotify.get_current_track)


async def spotify_play_pause(play: bool = True, dry_run: bool = False) -> dict:
    """Play or pause Spotify playback (requires SPOTIFY_ACCESS_TOKEN)."""
    if not _spotify.is_configured():
        return {"ok": False, "error": "Spotify is not connected. Add credentials in the Spotify panel."}
    if dry_run:
        return {"dry_run": True, "action": "spotify_play_pause", "play": play}
    import asyncio
    return await asyncio.to_thread(_spotify.play_pause, play=play)
