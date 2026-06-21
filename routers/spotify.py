"""Spotify router — REST endpoints for the Spotify sidebar panel."""
from __future__ import annotations
from fastapi import APIRouter
from arix.integrations import spotify as _spotify

router = APIRouter(prefix="/api/spotify", tags=["spotify"])


@router.get("/status")
def spotify_status():
    return {"configured": _spotify.is_configured(), "setup": _spotify.get_setup_instructions(), "provider": "spotify"}


@router.get("/search")
def spotify_search(q: str, limit: int = 10):
    return _spotify.search_tracks(query=q, limit=limit)


@router.get("/current")
def spotify_current():
    return _spotify.get_current_track()


@router.post("/play")
def spotify_play():
    return _spotify.play_pause(play=True)


@router.post("/pause")
def spotify_pause():
    return _spotify.play_pause(play=False)
